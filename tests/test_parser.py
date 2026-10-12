import csv
import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'build/linkedin_assistant/bin'))
try:
    from linkedin_lib.parser import parse_archive, parse_date
except ImportError:
    parse_archive = parse_date = None


def make_zip(path, files):
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            if isinstance(data, list):
                out = io.StringIO(newline='')
                csv.writer(out).writerows(data)
                data = out.getvalue()
            z.writestr(name, data)
    return path


class ParserTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(parse_archive, 'archive parser must exist')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'export.zip'

    def parse(self, files):
        make_zip(self.path, files)
        return parse_archive(self.path, 'personal', '2026-10-11T12:00:00Z', 'America/New_York')

    def test_connections_preamble_multiline_and_sensitive_projection(self):
        result = self.parse({'Connections.csv': [['Notes:'], ['intro'], [], ['First Name','Last Name','URL','Email Address','Company','Position','Connected On'], ['A','B','https://linkedin.com/in/a','secret@example.com','Acme\nLabs','Engineer','10 Oct 2026']]})
        row = result['records'][0]
        self.assertEqual(row['company'], 'Acme\nLabs')
        self.assertNotIn('secret@example.com', str(result))
        self.assertEqual(row['event_time'], '2026-10-10T04:00:00Z')
        self.assertEqual(row['time_precision'], 'day')
        self.assertEqual(result['manifests'][0]['source_rows'], 1)

    def test_duplicate_headers_preserved_and_unnamed_header_accounted(self):
        from linkedin_lib.schema import SCHEMAS
        head = SCHEMAS['Ad_Targeting.csv']
        values = [''] * len(head)
        values[0] = '42'
        values[2:4] = ['Acme','Beta']
        learning_head = SCHEMAS['Learning.csv']
        learning_row = [''] * len(learning_head)
        learning_row[-1] = 'extra'
        result = self.parse({'Ad_Targeting.csv':[head,values], 'Learning.csv':[learning_head,learning_row]})
        row = next(r for r in result['records'] if r['dataset']=='ad_targeting')
        self.assertEqual(row['company_names_2'], 'Beta')
        self.assertNotIn('member_age', row)
        learning = next(r for r in result['records'] if r['dataset']=='learning')
        self.assertNotIn('column_8',learning)
        self.assertIn('',result['manifests'][1]['original_headers'][0]['headers'])

    def test_parts_duplicate_accounting_and_repacked_identity(self):
        rows = [['Saved Date','Job Url','Job Title','Company Name'], ['3/30/20, 9:00 AM','https://linkedin.com/jobs/1','Engineer','Acme']]
        result = self.parse({'Export/Jobs/Saved Jobs.csv': rows, 'Export/Jobs/Saved Jobs_1.csv':rows})
        self.assertEqual(len(result['records']), 1)
        m = result['manifests'][0]
        self.assertEqual((m['source_rows'], m['expected_records'], m['duplicate_rows']), (2,1,1))
        other = Path(self.tmp.name) / 'renamed.zip'
        make_zip(other, {'Export/Jobs/Saved Jobs_1.csv':rows,'Export/Jobs/Saved Jobs.csv':rows})
        self.assertEqual(result['export_id'], parse_archive(other,'personal','2026-10-12T00:00:00Z','UTC')['export_id'])

    def test_partial_career_dates_use_snapshot_time(self):
        result = self.parse({'Positions.csv': [['Company Name','Title','Description','Location','Started On','Finished On'], ['Acme','Engineer','secret@example.com','NY','2025','']]})
        row = result['records'][0]
        self.assertEqual(row['event_time'], '2026-10-11T12:00:00Z')
        self.assertEqual(row['time_basis'], 'snapshot')
        self.assertEqual(row['started_on_precision'], 'year')
        self.assertNotIn('description', row)

    def test_unknown_schema_and_bad_width_accounted(self):
        result = self.parse({'Skills.csv':[['Name'],['Python'],['too','many']], 'Unrecognized.csv': [['Secret'],['private']]})
        self.assertEqual(len(result['records']),1)
        self.assertEqual(sum(m['quarantined_rows'] for m in result['manifests']),2)
        self.assertNotIn('private',str(result))

    def test_dataset_directory_is_not_mistaken_for_export_wrapper(self):
        result=self.parse({'Jobs/Saved Jobs.csv':[['Saved Date','Job Url','Job Title','Company Name'],['3/30/20, 9:00 AM','https://linkedin.com/jobs/1','Engineer','Acme']]})
        self.assertEqual(len(result['records']),1)
        self.assertEqual(result['records'][0]['dataset'],'saved_job')

    def test_narrative_and_unknown_learning_columns_are_excluded(self):
        from linkedin_lib.schema import SCHEMAS
        rows={}
        for file,column in [('Recommendations_Received.csv','Text'),('Recommendations_Given.csv','Text'),('Education.csv','Activities'),('Learning.csv','')]:
            headers=SCHEMAS[file]; values=['']*len(headers)
            values[headers.index(column)]='narrative-secret@example.com'
            rows[file]=[headers,values]
        result=self.parse(rows)
        self.assertNotIn('narrative-secret@example.com',str(result))

    def test_distinct_source_rows_do_not_collapse_after_privacy_projection(self):
        from linkedin_lib.schema import SCHEMAS
        headers=SCHEMAS['Recommendations_Received.csv']
        a=['A','B','Acme','Engineer','narrative one','2026-10-10','VISIBLE']
        b=list(a);b[headers.index('Text')]='narrative two'
        result=self.parse({'Recommendations_Received.csv':[headers,a,b]})
        self.assertEqual(len(result['records']),2)
        self.assertEqual(result['manifests'][0]['duplicate_rows'],0)

    def test_sensitive_datasets_excluded(self):
        result = self.parse({'Private_identity_asset.csv':[['Private Identity Asset Name','Private Identity Asset Raw Text'], ['passport','secret']], 'Email Addresses.csv':[['Email Address'],['private@example.com']]})
        self.assertFalse(result['records'])
        self.assertEqual(sum(m['excluded_rows'] for m in result['manifests']),2)
        self.assertNotIn('secret',str(result))

    def test_traversal_and_symlink_rejected(self):
        for name in ['../Skills.csv','/Skills.csv','C:/Skills.csv','a/../../Skills.csv']:
            with self.subTest(name=name):
                with self.assertRaises(ValueError): self.parse({name:'Name\nPython\n'})
        with zipfile.ZipFile(self.path,'w') as z:
            info=zipfile.ZipInfo('Skills.csv'); info.external_attr=(0o120777<<16)
            z.writestr(info,'/tmp/target')
        with self.assertRaises(ValueError): parse_archive(self.path,'personal','2026-10-11T00:00:00Z','UTC')

    def test_dates_explicit_utc_invalid_and_pivot(self):
        self.assertEqual(parse_date('10/01/26 11:36 AM UTC','UTC')[0], '2026-10-01T11:36:00Z')
        self.assertIsNone(parse_date('not a date','UTC'))
        self.assertEqual(parse_date('3/30/20, 9:00 AM','America/New_York')[0], '2020-03-30T13:00:00Z')

class ObservedFormatTests(unittest.TestCase):
    def test_all_observed_date_shapes(self):
        examples = {
            '2026/08/10 15:49:00 UTC':'2026-08-10T15:49:00Z',
            'Tue Sep 15 03:25:36 UTC 2026':'2026-09-15T03:25:36Z',
            '2025-11-06 00:18 UTC':'2025-11-06T00:18:00Z',
            'Dec 11, 2025 04:00 PM - Dec 11, 2025 05:00 PM':'2025-12-11T21:00:00Z',
            'You uploaded a feed photo on October 4, 2026 at 10:00 PM (GMT)':'2026-10-04T22:00:00Z',
        }
        for raw, expected in examples.items():
            with self.subTest(raw=raw):
                result=parse_date(raw,'America/New_York')
                self.assertIsNotNone(result)
                self.assertEqual(result[0],expected)

if __name__ == '__main__': unittest.main()
