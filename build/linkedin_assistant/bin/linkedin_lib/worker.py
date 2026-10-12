"""Durable single-writer ZIP inbox processing and immutable JSON publication."""
import hashlib
import json
import os
import time
import zipfile
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .parser import parse_archive, encode, MAX_EVENT_BYTES
from .archive import read_archive


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w', encoding='utf-8', newline='\n') as stream:
        stream.write(encode(value) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def read_json(path, default):
    if not path.exists(): return default
    # Corrupt state must stop ingestion rather than reset duplicate protection.
    with path.open(encoding='utf-8') as stream: return json.load(stream)


def timestamp(now):
    return datetime.fromtimestamp(now, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def publish(root, dataset, identifier, events):
    target = root / 'spool' / dataset / (identifier + '.json')
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    lines = [encode(e) for e in events]
    if any(len(line.encode('utf-8')) > MAX_EVENT_BYTES for line in lines):
        raise ValueError('Indexed event exceeds 128 KiB limit')
    body = ''.join(line + '\n' for line in lines).encode('utf-8')
    if target.exists():
        if target.read_bytes() != body:
            raise ValueError('Immutable spool differs from existing content; inspect state before retry')
        return
    # Staging and spool are in the same runtime root/filesystem.
    temporary = root / 'state' / (dataset + '-' + identifier + '.pending')
    with temporary.open('wb') as stream:
        stream.write(body)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary,0o600)
    os.replace(temporary,target)


@contextmanager
def worker_lock(root):
    import fcntl
    with (root / 'state' / 'worker.lock').open('a') as stream:
        try: fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try: yield True
        finally: fcntl.flock(stream, fcntl.LOCK_UN)


def run_once(config, now=None):
    now = time.time() if now is None else now
    root = Path(config['runtime_root']).expanduser()
    member = config.get('member_id','personal')
    for sub in ('inbox','processing','spool','archive','failed','quarantine','state'):
        folder = root / sub
        if folder.is_symlink(): raise ValueError('Runtime subdirectories must not be symlinks')
        folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    with worker_lock(root) as acquired:
        if not acquired: return []
        statefile = root / 'state' / 'imports.json'
        state = read_json(statefile, {'observed':{}, 'jobs':{}, 'completed':{}})
        statuses = []

        def status(value, **fields):
            event = dict(event_time=timestamp(now), event_kind='status', status=value,
                         member_id=member, inbox_path=str(root/'inbox'))
            event.update(fields)
            statuses.append(event)
            # One immutable file per status event. IDs do not depend on random names.
            identifier = hashlib.sha256(encode(event).encode()).hexdigest()
            publish(root, 'import', identifier, [event])

        def save(): atomic_json(statefile,state)

        # Reclaim processing files left by a crash after rename and before state save.
        for path in sorted((root/'processing').glob('*.zip')):
            if path.is_symlink() or not path.is_file(): continue
            if path.name not in state['jobs']:
                state['jobs'][path.name] = dict(claimed_time=timestamp(now), phase='claimed')
        save()
        for path in sorted((root/'inbox').glob('*.zip')):
            if path.is_symlink():
                status('failed',reason='Inbox symlinks are unsupported', archive_name=path.name)
                continue
            if not path.is_file():
                status('failed',reason='Inbox entries must be regular ZIP files',archive_name=path.name)
                continue
            stat = path.stat()
            signature = [stat.st_size, stat.st_mtime_ns]
            previous = state['observed'].get(path.name)
            if not previous or previous['signature'] != signature:
                state['observed'][path.name] = dict(signature=signature, first_seen=now)
                status('waiting',archive_name=path.name,reason='Waiting for a stable completed copy')
                save()
                continue
            try:
                # Integrity check before claim; do not extract anything here.
                if stat.st_size > 128*1024*1024: raise ValueError('ZIP exceeds 128 MiB compressed size limit')
                read_archive(path)  # Bounded full CRC check before claiming a possibly slow copy.
            except (zipfile.BadZipFile,EOFError):
                if now - previous['first_seen'] < int(config.get('copy_grace_seconds',300)):
                    status('waiting',archive_name=path.name,reason='ZIP copy incomplete; retrying')
                    continue
                target = root/'failed'/(hashlib.sha256(path.name.encode()).hexdigest()[:16]+'.zip')
                os.replace(path,target)
                del state['observed'][path.name]
                status('failed',archive_name=path.name,reason='Invalid or incomplete ZIP after copy grace period')
                save()
                continue
            except ValueError as error:
                target=root/'failed'/(hashlib.sha256(path.name.encode()).hexdigest()[:16]+'.zip')
                os.replace(path,target)
                del state['observed'][path.name]
                status('failed',archive_name=path.name,reason=str(error)); save(); continue
            # Name includes a content digest to avoid overwriting other queued imports.
            archive_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            claimed = root/'processing'/(archive_hash+'.zip')
            os.replace(path,claimed)
            state['jobs'].setdefault(claimed.name,dict(claimed_time=timestamp(now),phase='claimed'))
            state['observed'].pop(path.name,None)
            save()
        for path in sorted((root/'processing').glob('*.zip')):
            if path.is_symlink() or not path.is_file(): continue
            job = state['jobs'][path.name]
            status('processing',archive_name=path.name)
            try:
                result = parse_archive(path,member,job['claimed_time'],config.get('timezone','UTC'))
                export = result['export_id']
                if export in state['completed']:
                    os.replace(path,root/'archive'/(export+'.zip'))
                    state['jobs'].pop(path.name,None)
                    status('duplicate_skipped',export_id=export)
                    save()
                    continue
                # Full schema provenance stays local; indexed metadata is bounded.
                atomic_json(root/'state'/(export+'-manifest.json'),result['manifests'])
                warning_count=sum(m['quarantined_rows']+m['date_issues'] for m in result['manifests'])
                manifests=[]
                for m in result['manifests']:
                    event=dict(event_time=job['claimed_time'],event_kind='manifest',member_id=member,
                        export_id=export,snapshot_time=job['claimed_time'],snapshot_time_basis='import_observed',
                        import_epoch=datetime.fromisoformat(job['claimed_time'].replace('Z','+00:00')).timestamp(),
                        warning_count=warning_count,expected_dataset_count=len(result['manifests']))
                    event.update({k:v for k,v in m.items() if k not in ('files','original_headers')})
                    event['source_file_count']=len(m['files'])
                    event['source_files']=[name[:512] for name in m['files'][:20]]
                    manifests.append(event)
                if any(len(encode(event).encode('utf-8')) > MAX_EVENT_BYTES for event in manifests):
                    raise ValueError('Indexed manifest exceeds 128 KiB limit')
                groups=defaultdict(list)
                for row in result['records']: groups[row['dataset']].append(row)
                for dataset,rows in groups.items(): publish(root,dataset,export,rows)
                publish(root,'manifest',export,manifests)
                if result['issues']:
                    atomic_json(root/'quarantine'/(export+'.json'), result['issues'])
                state['completed'][export] = dict(claimed_time=job['claimed_time'],phase='published')
                job['phase']='published'
                save()
                os.replace(path,root/'archive'/(export+'.zip'))
                state['jobs'].pop(path.name,None)
                save()
                status('indexing',export_id=export,expected_records=len(result['records']),warning_count=warning_count)
            except (ValueError,UnicodeError,zipfile.BadZipFile,RuntimeError) as error:
                # Error text contains schema paths or fixed diagnostics, never CSV values.
                os.replace(path,root/'failed'/path.name)
                state['jobs'].pop(path.name,None)
                save()
                status('failed',archive_name=path.name,reason=str(error))
        # No automatic spool cleanup: indexed-data reconciliation is outside this process.
        retention=int(config.get('archive_retention_days',30))
        if retention > 0:
            for folder in ('archive','failed'):
                for path in (root/folder).glob('*.zip'):
                    if not path.is_symlink() and path.is_file() and now-path.stat().st_mtime > retention*86400:
                        path.unlink()
        status('watching',reason='ZIP inbox watcher is active')
        return statuses
