#!/usr/bin/env python3
"""Splunk scheduled entry point. No credentials, subprocesses or network access."""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from linkedin_lib.parser import encode
from linkedin_lib.worker import run_once


def main():
    os.umask(0o077)
    splunk_home = os.environ.get('SPLUNK_HOME')
    if not splunk_home:
        raise ValueError('SPLUNK_HOME must be set by Splunk Enterprise')
    from splunk.clilib.cli_common import getMergedConf
    configured = getMergedConf('linkedin_assistant').get('settings',{})
    config = dict(runtime_root=str(Path(splunk_home)/'var/lib/linkedin_assistant'),
                  member_id=configured.get('member_id','personal'),
                  timezone=configured.get('timezone','UTC'),
                  copy_grace_seconds=configured.get('copy_grace_seconds','300'),
                  archive_retention_days=configured.get('archive_retention_days','30'))
    statuses = run_once(config)
    # Analytics and status events are ingested from the durable monitored spool.
    print(encode(dict(event_time=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
          event_kind='worker',status='active',member_id=config['member_id'],
          inbox_path=str(Path(config['runtime_root'])/'inbox'),operations=len(statuses))))


if __name__ == '__main__':
    try: main()
    except Exception as error:
        # Avoid traceback/row content in indexed operational output.
        print(encode(dict(event_time=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            event_kind='worker',status='worker_error',reason=type(error).__name__)),flush=True)
        print('LinkedIn Assistant worker failed: '+type(error).__name__+'; check runtime permissions and configuration.',file=sys.stderr)
        sys.exit(1)
