#!/usr/bin/env python3
"""Validate a local sample without retaining or printing personal records."""
import argparse
import csv
import json
import sys
import tempfile
import time
import zipfile
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'build/linkedin_assistant/bin'))
from linkedin_lib.worker import run_once


def validate(sample, output):
    with tempfile.TemporaryDirectory() as temporary:
        root=Path(temporary); (root/'inbox').mkdir()
        with zipfile.ZipFile(root/'inbox/sample.zip','w',zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(sample.rglob('*.csv')):
                archive.write(path,path.relative_to(sample))
        config=dict(runtime_root=str(root),member_id='personal',timezone='America/New_York',archive_retention_days=0)
        now=time.time()
        run_once(config,now=now); run_once(config,now=now+30)
        events=[json.loads(line) for path in (root/'spool').rglob('*.json') for line in path.read_text().splitlines()]
        manifests=[e for e in events if e['event_kind']=='manifest']
        records=[e for e in events if e['event_kind']=='record']
        counts={k:sum(m[k] for m in manifests) for k in ['source_rows','expected_records','excluded_rows','duplicate_rows','quarantined_rows','date_issues']}
        assert counts['source_rows']==sum(counts[k] for k in ['expected_records','excluded_rows','duplicate_rows','quarantined_rows'])
        assert counts['expected_records']==len(records)
        assert len({r['event_id'] for r in records})==len(records)
        assert all(len(line.encode('utf-8'))<=128*1024 for path in (root/'spool').rglob('*.json') for line in path.read_text().splitlines())
        excluded=set()
        for path in sample.rglob('*.csv'):
            rows=list(csv.reader(path.open(encoding='utf-8-sig',newline='')))
            offset=3 if path.name=='Connections.csv' else 0
            if len(rows)<=offset: continue
            indices=[i for i,h in enumerate(rows[offset]) if any(w in h.lower() for w in ('email','phone','raw text'))]
            for row in rows[offset+1:]:
                excluded.update(row[i].strip() for i in indices if i<len(row) and len(row[i].strip())>5)
        from linkedin_lib.schema import BLOCKED
        assert not any(BLOCKED.search(key) for record in records for key in record),'Excluded field was indexed'
        indexed=json.dumps(records,ensure_ascii=False)
        leaks=sum(value in indexed for value in excluded)
        assert leaks==0,'An excluded source value appeared in normalized records'
        result=dict(counts,records=len(records),datasets=len(manifests),excluded_values_checked=len(excluded),value_leaks=leaks,narrative_field_leaks=0)
        output.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('sample',type=Path)
    parser.add_argument('--output',type=Path,default=Path('docs/sample-validation-summary.json'))
    args=parser.parse_args(); validate(args.sample,args.output)
