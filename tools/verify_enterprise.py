#!/usr/bin/env python3
"""Exercise the installed app's SPL in an actual Splunk Enterprise instance.

Read-only: this verifier never writes ready events or modifies app settings.
Credentials come from environment variables, never command-line arguments.
"""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


class Enterprise:
    def __init__(self, url, username, password, insecure=False):
        self.url=url.rstrip('/')
        self.auth='Basic '+base64.b64encode((username+':'+password).encode()).decode()
        self.context=ssl._create_unverified_context() if insecure else ssl.create_default_context()

    def request(self, endpoint, data=None):
        body=urllib.parse.urlencode(data).encode() if data is not None else None
        request=urllib.request.Request(self.url+endpoint,body,
                                       headers={'Authorization':self.auth})
        try:
            with urllib.request.urlopen(request,context=self.context,timeout=90) as response:
                return response.read().decode()
        except urllib.error.HTTPError as error:
            raise RuntimeError('Splunk HTTP '+str(error.code)+': '+error.read().decode()) from error

    def get(self, endpoint):
        return json.loads(self.request(endpoint+'?output_mode=json&count=0'))

    def search(self, query):
        # Model Splunk Web and scheduler dispatch, including leading macros.
        if not query.lstrip().startswith(('search ', '|')):
            query='search '+query
        payload=self.request('/servicesNS/admin/linkedin_assistant/search/jobs/export',
            {'search':query,'output_mode':'json','preview':'false',
             'earliest_time':'0','latest_time':'+10y'})
        entries=[json.loads(line) for line in payload.splitlines() if line.strip()]
        errors=[entry for entry in entries if entry.get('type') in ('ERROR','FATAL')]
        for entry in entries:
            errors += [message for message in entry.get('messages',[])
                       if message.get('type') in ('ERROR','FATAL')]
        if errors:
            raise RuntimeError(json.dumps(errors))
        return [entry['result'] for entry in entries if 'result' in entry and not entry.get('preview')]


def verify(api, args):
    info=api.get('/services/server/info')['entry'][0]['content']
    report={'splunk_version':info['version'],'stage':args.stage,'checks':[]}
    rows=api.search('`li_reconcile`')
    report['checks'].append({'name':'reconciliation','rows':rows})
    matching=[row for row in rows if row.get('member_id')==args.member]
    assert len(matching)==1, 'Expected exactly one reconciled import; got '+str(len(matching))
    row=matching[0]
    assert int(row['actual'])==args.expected_records, 'Reconciled record count differs'
    assert int(row['expected'])==args.expected_records, 'Manifest record count differs'
    assert int(row['datasets_seen'])==args.expected_datasets, 'Dataset count differs'
    if args.stage=='reconcile':
        return report
    ready=api.search('index=linkedin sourcetype=linkedin:ready | where member_id='+
        json.dumps(args.member)+' | stats count AS ready_events dc(export_id) AS exports '
        'max(actual_records) AS actual_records')
    report['checks'].append({'name':'scheduled_readiness','rows':ready})
    assert ready and int(ready[0]['ready_events'])==1, 'Expected one automatically written ready event'
    assert int(ready[0]['actual_records'])==args.expected_records
    if args.stage=='ready':
        return report
    # The endpoint includes globally exported views from other installed apps.
    views=[view for view in api.get('/servicesNS/admin/linkedin_assistant/data/ui/views')['entry']
           if view['acl']['app']=='linkedin_assistant']
    tasks=[]
    for view in views:
        root=ET.fromstring(view['content']['eai:data'])
        member_query=root.find('.//input[@token="member"]/search/query')
        assert member_query is not None, 'Member search missing: '+view['name']
        member_rows=api.search(member_query.text)
        assert len([r for r in member_rows if r.get('member_id')==args.member])==1, \
            'Member selector must contain the fixture member exactly once: '+view['name']
        # Run the real token-producing search. Injecting the reconciled ID
        # would conceal multivalue extraction bugs seen in Splunk Web.
        latest_export=None
        token_search=root.find('search/query')
        if token_search is not None:
            latest_rows=api.search(token_search.text.replace('$member|s$',json.dumps(args.member)))
            assert len(latest_rows)==1, 'Latest snapshot search must return one row: '+view['name']
            latest_export=latest_rows[0].get('export_id')
            assert isinstance(latest_export,str), 'Snapshot token must be a single ID: '+view['name']
            assert latest_export==row['export_id'], 'Snapshot token differs from reconciled import'
        for panel in root.findall('.//panel'):
            for query in panel.findall('.//query'):
                spl=query.text or ''
                for token,value in (('member',args.member),('snapshot','latest'),
                                    ('latest_export',latest_export)):
                    if value is None:
                        continue
                    spl=spl.replace('$'+token+'|s$',json.dumps(value))
                assert '$' not in spl, 'Unresolved dashboard token in '+view['name']
                tasks.append((view['name'],panel.findtext('title'),spl))
    def execute(task):
        name,title,spl=task
        rows=api.search(spl+' | eval verification_epoch=_time' if 'timechart ' in spl else spl)
        evidence={'view':name,'panel':title,'rows':len(rows)}
        if 'timechart ' in spl and rows:
            latest=max(datetime.fromtimestamp(float(r['verification_epoch']),timezone.utc) for r in rows)
            assert latest<=datetime.now(timezone.utc), 'Future time bucket: '+name+'/'+title
            evidence['last_time_bucket']=latest.isoformat()
        # Retain aggregate single-value results, never names or record details.
        if len(rows)==1:
            numbers={key:value for key,value in rows[0].items()
                     if key not in ('_time','verification_epoch','export_id','member_id')
                     and str(value).replace('.','',1).isdigit()}
            if numbers:
                evidence['numbers']=numbers
        return evidence
    with ThreadPoolExecutor(max_workers=3) as pool:
        panels=list(pool.map(execute,tasks))
    report['checks'].append({'name':'installed_dashboard_searches','panels':panels})
    by_panel={(panel['view'],panel['panel']):panel for panel in panels}
    for title,field,expected in (('Connections','Connections',4508),
                               ('Applications','Applications',1180),
                               ('Endorsements received','Endorsements',814),
                               ('Completed learning items','Completed',14)):
        panel=by_panel.get(('overview',title),{})
        assert int(panel.get('numbers',{}).get(field,-1))==expected, title+' panel differs'
    assert len({panel['view'] for panel in panels})==8, 'Expected all eight dashboards'
    assert len(panels)==44, 'Expected all 44 installed panel searches'
    expected_empty={('import_health','Imports awaiting reconciliation'),
                    ('jobs','Applications also present in saved jobs')}
    for panel in panels:
        if (panel['view'],panel['panel']) not in expected_empty:
            assert panel['rows']>0, 'Unexpected empty panel: '+panel['view']+'/'+panel['panel']
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='https://127.0.0.1:18089')
    parser.add_argument('--insecure-local-test',action='store_true')
    parser.add_argument('--stage',choices=('reconcile','ready','dashboards'),default='dashboards')
    parser.add_argument('--member',default='personal')
    parser.add_argument('--expected-records',type=int,default=9608)
    parser.add_argument('--expected-datasets',type=int,default=39)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.insecure_local_test and urllib.parse.urlparse(args.url).hostname not in ('localhost','127.0.0.1','::1'):
        parser.error('insecure TLS is limited to an isolated localhost test instance')
    api=Enterprise(args.url,os.environ.get('SPLUNK_TEST_USER','admin'),
                   os.environ['SPLUNK_TEST_PASSWORD'],args.insecure_local_test)
    try:
        report=verify(api,args)
        report['status']='passed'
    except Exception as error:
        report={'status':'failed','stage':args.stage,'error':str(error)}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':
    sys.exit(main())
