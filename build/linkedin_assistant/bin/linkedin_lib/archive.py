"""Bounded ZIP reader. Never extracts user-controlled paths onto the filesystem."""
import hashlib
import re
import stat
import zipfile
import zlib
from pathlib import PurePosixPath

MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_EXPANDED_BYTES = 256 * 1024 * 1024
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_ENTRIES = 2000


def read_archive(path):
    if path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError('ZIP exceeds 128 MiB compressed size limit')
    entries = []
    total = 0
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_ENTRIES:
            raise ValueError('ZIP has more than 2000 entries')
        seen = set()
        for info in infos:
            name = info.filename.replace('\\', '/')
            parts = PurePosixPath(name).parts
            if not parts or name.startswith('/') or '..' in parts or re.match(r'^[A-Za-z]:', name) or '\x00' in name:
                raise ValueError('Unsafe ZIP path')
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError('ZIP symlinks are unsupported')
            if info.flag_bits & 1:
                raise ValueError('Encrypted ZIPs are unsupported; supply an unencrypted LinkedIn export')
            if name.casefold() in seen:
                raise ValueError('Duplicate ZIP entry path')
            seen.add(name.casefold())
            total += info.file_size
            if total > MAX_EXPANDED_BYTES or info.file_size > MAX_FILE_BYTES:
                raise ValueError('ZIP exceeds expanded size limit')
            if info.file_size > 1024 * 1024 and info.file_size / max(1, info.compress_size) > 1000:
                raise ValueError('ZIP exceeds compression-ratio limit')
            if info.is_dir():
                continue
            if info.compress_type not in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED):
                raise ValueError('Unsupported ZIP compression; use stored or DEFLATE entries')
            # Normalize decompressor failures so one damaged ZIP cannot starve the inbox.
            try:
                data = archive.read(info)
            except (zlib.error,EOFError) as error:
                raise zipfile.BadZipFile('Corrupt ZIP payload') from error
            if name.lower().endswith('.csv') and '__MACOSX' not in parts and not PurePosixPath(name).name.startswith('._'):
                entries.append((name, data))
    if not entries:
        raise ValueError('No CSV datasets found in ZIP')
    # Ignore a single enclosing folder for identity and schema matching.
    split = [PurePosixPath(name).parts for name, _ in entries]
    if all(len(parts) > 1 for parts in split) and len({parts[0] for parts in split}) == 1:
        from .schema import resolve_schema
        stripped = [('/'.join(PurePosixPath(name).parts[1:]), data) for name, data in entries]
        # Jobs/ and Verifications/ are real dataset paths, not outer wrappers.
        if sum(resolve_schema(name) is not None for name, _ in stripped) > sum(resolve_schema(name) is not None for name, _ in entries):
            entries = stripped
    digest = hashlib.sha256()
    for name, data in sorted(entries):
        digest.update(name.encode('utf-8') + b'\0' + hashlib.sha256(data).digest())
    return entries, digest.hexdigest()
