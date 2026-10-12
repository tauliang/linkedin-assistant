"""Generate the packaged Simple XML views from reviewable SPL definitions."""
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]/'build/linkedin_assistant/default/data/ui/views'


def search(parent, query, refresh='60s'):
    s=ET.SubElement(parent,'search')
    ET.SubElement(s,'query').text=query
    ET.SubElement(s,'earliest').text='0'
    ET.SubElement(s,'latest').text='now'
    ET.SubElement(s,'refresh').text=refresh
    ET.SubElement(s,'refreshType').text='delay'
    return s


def view(name,label,description,panels,analytical=True):
    root=ET.Element('form',{'version':'1.1','theme':'light'})
    ET.SubElement(root,'label').text=label
    ET.SubElement(root,'description').text=description
    init=ET.SubElement(root,'init')
    ET.SubElement(init,'set',{'token':'latest_export'}).text='__none__'
    fs=ET.SubElement(root,'fieldset',{'submitButton':'false','autoRun':'true'})
    member=ET.SubElement(fs,'input',{'type':'dropdown','token':'member','searchWhenChanged':'true'})
    ET.SubElement(member,'label').text='Member'
    ET.SubElement(member,'default').text='personal'
    search(member,'index=linkedin sourcetype=linkedin:* earliest=0 latest=+10y | search member_id=* | stats count BY member_id | eval member_label=if(member_id="personal","Personal",member_id) | fields member_id member_label')
    ET.SubElement(member,'fieldForLabel').text='member_label'
    ET.SubElement(member,'fieldForValue').text='member_id'
    if analytical:
        snapshot=ET.SubElement(fs,'input',{'type':'dropdown','token':'snapshot','searchWhenChanged':'true'})
        ET.SubElement(snapshot,'label').text='Snapshot'
        ET.SubElement(snapshot,'choice',{'value':'latest'}).text='Latest ready snapshot (automatic)'
        ET.SubElement(snapshot,'default').text='latest'
        search(snapshot,'index=linkedin sourcetype=linkedin:ready earliest=0 latest=+10y | search event_kind=ready member_id=$member|s$ | dedup export_id | sort - import_epoch | eval label=snapshot_time." — ".status | fields label export_id')
        ET.SubElement(snapshot,'fieldForLabel').text='label'
        ET.SubElement(snapshot,'fieldForValue').text='export_id'
        latest=search(root,'index=linkedin sourcetype=linkedin:ready earliest=0 latest=+10y | search event_kind=ready member_id=$member|s$ | dedup export_id | sort - import_epoch | head 1 | fields export_id','30s')
        done=ET.SubElement(latest,'done')
        condition=ET.SubElement(done,'condition',{'match':'$job.resultCount$ > 0'})
        ET.SubElement(condition,'set',{'token':'latest_export'}).text='$result.export_id$'
        other=ET.SubElement(done,'condition')
        ET.SubElement(other,'set',{'token':'latest_export'}).text='__none__'
        banner=ET.SubElement(ET.SubElement(root,'row'),'panel')
        ET.SubElement(banner,'title').text='Selected snapshot'
        table=ET.SubElement(banner,'table')
        search(table,'index=linkedin sourcetype=linkedin:ready earliest=0 latest=+10y | search event_kind=ready member_id=$member|s$ | where export_id=if($snapshot|s$="latest",$latest_export|s$,$snapshot|s$) | dedup export_id | table snapshot_time snapshot_time_basis status actual_records warning_count export_id')
        ET.SubElement(table,'option',{'name':'drilldown'}).text='none'
    for start in range(0,len(panels),2):
        row=ET.SubElement(root,'row')
        for title,kind,query in panels[start:start+2]:
            p=ET.SubElement(row,'panel'); ET.SubElement(p,'title').text=title
            chart=ET.SubElement(p,'single' if kind=='single' else 'table' if kind=='table' else 'chart')
            search(chart,query)
            if kind not in ('single','table'):
                ET.SubElement(chart,'option',{'name':'charting.chart'}).text=kind
                ET.SubElement(chart,'option',{'name':'charting.legend.placement'}).text='bottom'
            ET.SubElement(chart,'option',{'name':'drilldown'}).text='none'
            if kind=='table': ET.SubElement(chart,'option',{'name':'count'}).text='10'
    ET.indent(root)
    ET.ElementTree(root).write(ROOT/(name+'.xml'),encoding='utf-8',xml_declaration=True)


BASE='`li_records` | search member_id=$member|s$ | where export_id=if($snapshot|s$="latest",$latest_export|s$,$snapshot|s$)'
def data(dataset): return BASE+' | search dataset='+dataset

view('overview','LinkedIn Assistant',
     'Drop a LinkedIn export ZIP into the server inbox shown in Setup & inbox. Dashboards switch automatically after indexed record counts reconcile. Dates labeled import_observed describe when the snapshot was received.',[
    ('Connections','single',data('connection')+' | stats count AS Connections'),
    ('Applications','single',data('job_application')+' | stats count AS Applications'),
    ('Endorsements received','single',data('endorsement_received')+' | stats count AS Endorsements'),
    ('Completed learning items','single',data('learning')+' | where isnotnull(content_completed_at_if_completed) AND content_completed_at_if_completed!="" AND content_completed_at_if_completed!="N/A" | stats count AS Completed'),
    ('Available datasets','bar',BASE+' | stats count AS records BY dataset | sort - records'),
    ('Import inventory','table','index=linkedin sourcetype=linkedin:manifest earliest=0 latest=+10y | search event_kind=manifest member_id=$member|s$ | where export_id=if($snapshot|s$="latest",$latest_export|s$,$snapshot|s$) | dedup export_id dataset | table dataset source_rows expected_records excluded_rows duplicate_rows quarantined_rows date_issues'),
])
view('network','Network','Company and job title reflect the exported profile, not employment at the connection date. Cumulative totals use all dated connections in the selected snapshot.',[
    ('Connection additions by month','column',data('connection')+' time_basis=activity | timechart span=1mon count AS Added'),
    ('Cumulative dated connections','line',data('connection')+' time_basis=activity | timechart span=1mon count AS Added | streamstats sum(Added) AS Connections | fields _time Connections'),
    ('Top companies','bar',data('connection')+' | where company!="" | stats count AS Connections BY company | sort - Connections | head 20'),
    ('Top job titles','bar',data('connection')+' | where job_title!="" | stats count AS Connections BY job_title | sort - Connections | head 20'),
    ('Contacts','table',data('connection')+' | sort - _time | table first_name last_name company job_title connected_on url'),
    ('Profile field completeness','table',data('connection')+' | stats count AS total count(eval(company="" OR isnull(company))) AS missing_company count(eval(job_title="" OR isnull(job_title))) AS missing_title'),
])
view('invitations','Invitations','Exported invitations show direction and activity. Acceptance outcomes are not available in this dataset.',[
    ('Invitations by month and direction','column',data('invitation')+' time_basis=activity | timechart span=1mon count BY direction'),
    ('Incoming and outgoing totals','pie',data('invitation')+' | stats count AS Invitations BY direction'),
    ('Invitation activity','table',data('invitation')+' | sort - _time | table sent_at direction from to inviterprofileurl inviteeprofileurl'),
])
view('jobs','Job search','Applications and saved jobs are activity records. The export does not contain reliable interview, rejection or offer outcomes.',[
    ('Applications by month','column',data('job_application')+' time_basis=activity | timechart span=1mon count AS Applications'),
    ('Saved jobs by month','column',data('saved_job')+' time_basis=activity | timechart span=1mon count AS Saved'),
    ('Companies applied to','bar',data('job_application')+' | stats count AS Applications BY company | sort - Applications | head 20'),
    ('Roles applied to','bar',data('job_application')+' | stats count AS Applications BY job_title | sort - Applications | head 20'),
    ('Applications also present in saved jobs','table',BASE+' | search dataset IN (job_application,saved_job) | where job_url!="" | stats values(dataset) AS datasets values(company) AS company values(job_title) AS job_title BY job_url | where mvcount(datasets)=2 | table company job_title job_url'),
    ('Application history','table',data('job_application')+' | sort - _time | table application_date company job_title job_url'),
])
view('career','Skills & career','Endorsements describe exported activity, not proficiency. Year/month career dates retain their original precision.',[
    ('Most endorsed skills','bar',data('endorsement_received')+' | stats count AS Endorsements BY skill | sort - Endorsements | head 20'),
    ('Given and received endorsements','column',BASE+' | search dataset IN (endorsement_given,endorsement_received) time_basis=activity | timechart span=1mon count BY dataset'),
    ('Declared skills without received endorsements','table',BASE+' | search dataset IN (skill,endorsement_received) | eval declared=if(dataset="skill",1,0), received=if(dataset="endorsement_received",1,0), skill=coalesce(skill,name) | stats max(declared) AS declared sum(received) AS endorsements BY skill | where declared=1 AND endorsements=0 | table skill'),
    ('Position history','table',data('position')+' | table company title location started_on started_on_precision finished_on finished_on_precision'),
    ('Education','table',data('education')+' | table school_name degree_name start_date end_date'),
    ('Certifications','table',data('certifications')+' | table name authority started_on finished_on url'),
])
view('learning','Learning','Counts refer to exported content items. Viewing duration and hours are not available.',[
    ('Completed items over time','column',data('learning')+' time_basis=activity selected_date_field=content_completed_at_if_completed | timechart span=1mon count AS Completed'),
    ('Content types','pie',data('learning')+' | stats count AS Items BY content_type'),
    ('Saved items','single',data('learning')+' | where in(lower(content_saved),"true","yes","1") | stats count AS Saved'),
    ('Items without a usable activity date','single',data('learning')+' time_basis=snapshot | stats count AS Undated'),
    ('Learning library','table',data('learning')+' | table content_title content_type content_saved content_last_watched_date_if_viewed content_completed_at_if_completed'),
])
view('import_health','Import health','Processing completion and indexing completion are distinct. New imports become ready only after every dataset matches its manifest.',[
    ('Latest watcher heartbeat','table','index=linkedin sourcetype=linkedin:worker earliest=0 latest=+10y | search member_id=$member|s$ | sort - _time | head 1 | eval seconds_since_heartbeat=round(now()-_time) | table _time status inbox_path seconds_since_heartbeat reason'),
    ('Recent import lifecycle','table','index=linkedin sourcetype=linkedin:import earliest=0 latest=+10y | search member_id=$member|s$ status!=watching | sort - _time | head 50 | table _time status archive_name export_id expected_records reason'),
    ('Per-dataset index reconciliation','table','index=linkedin sourcetype=linkedin:* earliest=0 latest=+10y | where event_kind="record" OR event_kind="manifest" | search member_id=$member|s$ | stats dc(eval(if(event_kind="record",event_id,null()))) AS indexed_unique max(expected_records) AS expected max(quarantined_rows) AS quarantined max(excluded_rows) AS excluded max(duplicate_rows) AS source_duplicates max(date_issues) AS date_issues BY export_id dataset | fillnull value=0 indexed_unique | eval outcome=if(isnull(expected),"manifest pending",if(indexed_unique=expected,"matched","indexing")) | table export_id dataset expected indexed_unique outcome quarantined excluded source_duplicates date_issues'),
    ('Imports awaiting reconciliation','table','index=linkedin sourcetype=linkedin:manifest earliest=0 latest=+10y | search event_kind=manifest member_id=$member|s$ | dedup export_id | search NOT [ search index=linkedin sourcetype=linkedin:ready earliest=0 latest=+10y | search event_kind=ready member_id=$member|s$ | fields export_id ] | eval seconds_waiting=round(now()-import_epoch), status=if(seconds_waiting>600,"indexing delayed — check permissions and saved search","indexing") | table snapshot_time export_id seconds_waiting status'),
],analytical=False)
view('setup','Setup & inbox','Install on a single Splunk Enterprise 9.3+ Linux instance, restart Splunk, then copy ZIPs into $SPLUNK_HOME/var/lib/linkedin_assistant/inbox/. The folder is created by the worker. Default member is personal and timezone is UTC; optional local settings are described in the packaged README.',[
    ('Inbox and worker state','table','index=linkedin sourcetype=linkedin:worker earliest=0 latest=+10y | sort - _time | dedup member_id | eval age_seconds=round(now()-_time) | table member_id inbox_path status age_seconds reason'),
    ('Ready snapshots','table','index=linkedin sourcetype=linkedin:ready earliest=0 latest=+10y | search event_kind=ready | dedup member_id export_id | sort - import_epoch | table member_id snapshot_time status actual_records warning_count'),
],analytical=False)
