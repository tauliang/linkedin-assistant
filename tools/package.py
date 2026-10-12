#!/usr/bin/env python3
"""Build a reproducible .spl (gzip-compressed tar) with a single app root."""
import argparse
import gzip
import hashlib
import io
import tarfile
from pathlib import Path

ALLOWED_ROOTS={'bin','default','metadata','README','appserver','static'}
ALLOWED_ROOT_FILES={'README.md','LICENSE','CHANGELOG.md'}


def package(source, destination):
    source=Path(source); destination=Path(destination)
    destination.parent.mkdir(parents=True,exist_ok=True)
    with destination.open('wb') as raw:
        with gzip.GzipFile(filename='',fileobj=raw,mode='wb',mtime=0) as compressed:
            with tarfile.open(fileobj=compressed,mode='w',format=tarfile.USTAR_FORMAT) as tar:
                for path in sorted(source.rglob('*')):
                    rel=path.relative_to(source)
                    if path.is_symlink(): raise ValueError('Symlinks cannot be packaged: '+str(rel))
                    if not path.is_file(): continue
                    if '__pycache__' in rel.parts or path.suffix in ('.pyc','.pyo'): continue
                    if rel.parts[0] not in ALLOWED_ROOTS and str(rel) not in ALLOWED_ROOT_FILES:
                        raise ValueError('Unexpected package content: '+str(rel))
                    data=path.read_bytes()
                    info=tarfile.TarInfo('linkedin_assistant/'+rel.as_posix())
                    info.size=len(data); info.mtime=0; info.uid=0; info.gid=0
                    info.uname=''; info.gname=''
                    info.mode=0o755 if rel.as_posix()=='bin/linkedin_zip_worker.py' else 0o644
                    tar.addfile(info,io.BytesIO(data))
    return hashlib.sha256(destination.read_bytes()).hexdigest()


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[1]/'build/linkedin_assistant')
    parser.add_argument('--output',type=Path,default=Path(__file__).resolve().parents[1]/'dist/linkedin_assistant-1.0.2.spl')
    args=parser.parse_args()
    digest=package(args.source,args.output)
    args.output.with_suffix(args.output.suffix+'.sha256').write_text(digest+'  '+args.output.name+'\n')
    print(str(args.output)+' SHA256 '+digest)
