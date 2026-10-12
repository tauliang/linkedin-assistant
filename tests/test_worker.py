import json
import tempfile
import unittest
from pathlib import Path
from test_parser import make_zip
try:
    from linkedin_lib.worker import run_once
except ImportError:
    run_once = None

FILES = {'Skills.csv':[['Name'],['Python']]}

class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(run_once, 'durable inbox worker must exist')
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.config={'runtime_root':str(self.root),'member_id':'personal','timezone':'UTC','copy_grace_seconds':300,'archive_retention_days':30}
        (self.root/'inbox').mkdir()

    def drop(self,name='sample.zip',files=None):
        return make_zip(self.root/'inbox'/name,files or FILES)

    def events(self):
        return [json.loads(line) for p in (self.root/'spool').rglob('*.json') for line in p.read_text().splitlines()]

    def test_waits_for_stable_file_then_publishes_and_archives(self):
        self.drop()
        first=run_once(self.config,now=1000000000)
        self.assertFalse([e for e in self.events() if e['event_kind']=='record'])
        self.assertIn('waiting',[e['status'] for e in first])
        run_once(self.config,now=1000000030)
        rows=[e for e in self.events() if e['event_kind']=='record']
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['dataset'],'skill')
        self.assertEqual(len(list((self.root/'archive').glob('*.zip'))),1)
        self.assertFalse(list((self.root/'inbox').glob('*.zip')))
        manifests=[e for e in self.events() if e['event_kind']=='manifest']
        self.assertEqual(manifests[0]['expected_records'],1)
        self.assertEqual(manifests[0]['expected_dataset_count'],1)

    def test_renamed_repeat_does_not_publish_again(self):
        self.drop(); run_once(self.config,now=1000000000); run_once(self.config,now=1000000030)
        self.drop('renamed.zip'); run_once(self.config,now=1000000060)
        status=run_once(self.config,now=1000000090)
        self.assertIn('duplicate_skipped',[e['status'] for e in status])
        self.assertEqual(len([e for e in self.events() if e['event_kind']=='record']),1)

    def test_resumes_claimed_archive_after_restart(self):
        (self.root/'processing').mkdir()
        make_zip(self.root/'processing'/'orphan.zip',FILES)
        run_once(self.config,now=1000000000)
        self.assertEqual(len([e for e in self.events() if e['event_kind']=='record']),1)

    def test_corrupt_copy_retries_then_fails_without_analytic_data(self):
        p=self.root/'inbox'/'broken.zip'; p.write_bytes(b'partial')
        run_once(self.config,now=1000000000)
        early=run_once(self.config,now=1000000030)
        self.assertNotIn('failed',[e['status'] for e in early])
        late=run_once(self.config,now=1000000400)
        self.assertIn('failed',[e['status'] for e in late])
        self.assertFalse([e for e in self.events() if e['event_kind']=='record'])
        self.assertEqual(len(list((self.root/'failed').glob('*.zip'))),1)

    def test_bad_archive_does_not_stop_other_import(self):
        self.drop('bad.zip',{'../escape.csv':'a\nb'})
        self.drop('good.zip')
        run_once(self.config,now=1000000000)
        status=run_once(self.config,now=1000000030)
        self.assertIn('failed',[e['status'] for e in status])
        self.assertIn('indexing',[e['status'] for e in status])

    def test_temp_extensions_ignored(self):
        self.drop('pending.zip.part')
        run_once(self.config,now=1000000000); run_once(self.config,now=1000000030)
        self.assertFalse([e for e in self.events() if e['event_kind']=='record'])

    def test_crash_after_partial_publication_resumes_without_new_ids(self):
        from unittest.mock import patch
        import linkedin_lib.worker as worker
        self.drop(files={'Skills.csv':[['Name'],['Python']], 'Languages.csv':[['Name','Proficiency'],['English','Native']]})
        run_once(self.config,now=1000000000)
        original=worker.publish
        def fail_after_real_publish(root,dataset,identifier,events):
            original(root,dataset,identifier,events)
            if dataset=='skill': raise OSError('simulated disk interruption')
        with patch.object(worker,'publish',side_effect=fail_after_real_publish):
            with self.assertRaises(OSError): run_once(self.config,now=1000000030)
        before={e['event_id'] for e in self.events() if e['event_kind']=='record'}
        run_once(self.config,now=1000000060)
        records=[e for e in self.events() if e['event_kind']=='record']
        self.assertEqual(len(records),2)
        self.assertTrue(before.issubset({e['event_id'] for e in records}))
        manifests=[e for e in self.events() if e['event_kind']=='manifest']
        self.assertEqual(len(manifests),2)
        self.assertTrue(all(e['expected_dataset_count']==2 for e in manifests))

    def test_overlapping_worker_skips_locked_inbox(self):
        from linkedin_lib.worker import worker_lock
        self.drop()
        run_once(self.config,now=1000000000)
        with worker_lock(self.root) as acquired:
            self.assertTrue(acquired)
            self.assertEqual(run_once(self.config,now=1000000030),[])
        run_once(self.config,now=1000000060)
        self.assertEqual(len([e for e in self.events() if e['event_kind']=='record']),1)

    def test_crc_incomplete_copy_gets_grace_period(self):
        import zipfile
        path=self.root/'inbox/crc.zip'
        with zipfile.ZipFile(path,'w',zipfile.ZIP_STORED) as archive:
            archive.writestr('Skills.csv','Name\nPython\n')
        path.write_bytes(path.read_bytes().replace(b'Python',b'Pythan'))
        run_once(self.config,now=1000000000)
        status=run_once(self.config,now=1000000030)
        self.assertNotIn('failed',[e['status'] for e in status])
        self.assertIn('waiting',[e['status'] for e in status])
        late=run_once(self.config,now=1000000400)
        self.assertIn('failed',[e['status'] for e in late])

    def test_corrupt_deflate_does_not_starve_valid_zip(self):
        import struct,zipfile
        bad=self.drop('a_bad.zip')
        data=bytearray(bad.read_bytes())
        filename_len,extra_len=struct.unpack_from('<HH',data,26)
        data[30+filename_len+extra_len]=7
        bad.write_bytes(data)
        self.drop('z_good.zip')
        run_once(self.config,now=1000000000)
        run_once(self.config,now=1000000030)
        self.assertEqual(len([e for e in self.events() if e['event_kind']=='record']),1)
        status=run_once(self.config,now=1000000400)
        self.assertIn('failed',[e['status'] for e in status])

    def test_large_header_metadata_cannot_truncate_indexed_manifest(self):
        self.drop(files={'Skills.csv':[['Name','X'*140000],['Python','ignored']]})
        run_once(self.config,now=1000000000)
        run_once(self.config,now=1000000030)
        lengths=[len(line.encode('utf-8')) for p in (self.root/'spool').rglob('*.json') for line in p.read_text().splitlines()]
        self.assertLessEqual(max(lengths),128*1024)
        manifest=next(e for e in self.events() if e['event_kind']=='manifest')
        local=self.root/'state'/(manifest['export_id']+'-manifest.json')
        self.assertTrue(local.exists())
        self.assertEqual(json.loads(local.read_text())[0]['original_headers'][0]['headers'][1],'X'*140000)

    def test_directory_named_zip_does_not_starve_other_imports(self):
        (self.root/'inbox/a_directory.zip').mkdir()
        self.drop('z_good.zip')
        run_once(self.config,now=1000000000)
        status=run_once(self.config,now=1000000030)
        self.assertIn('indexing',[e['status'] for e in status])

if __name__=='__main__': unittest.main()
