import hashlib
import importlib.util
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
class PackageTests(unittest.TestCase):
    def test_package_is_deterministic_and_contains_no_runtime_data(self):
        spec=importlib.util.spec_from_file_location('package',ROOT/'tools/package.py')
        self.assertIsNotNone(spec.loader if spec else None)
        self.assertTrue((ROOT/'tools/package.py').exists(),'packager must exist')
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as d:
            a=Path(d)/'a.spl'; b=Path(d)/'b.spl'
            module.package(ROOT/'build/linkedin_assistant',a)
            module.package(ROOT/'build/linkedin_assistant',b)
            self.assertEqual(hashlib.sha256(a.read_bytes()).hexdigest(),hashlib.sha256(b.read_bytes()).hexdigest())
            with tarfile.open(a) as tar:
                names=tar.getnames()
                self.assertIn('linkedin_assistant/default/app.conf',names)
                self.assertIn('linkedin_assistant/bin/linkedin_zip_worker.py',names)
                for member in tar.getmembers():
                    self.assertFalse(member.issym() or member.islnk())
                    self.assertTrue(member.name.startswith('linkedin_assistant/'))
                    self.assertNotIn('__pycache__',member.name)
                    self.assertNotIn('sample-export',member.name)
                    self.assertNotIn('/local/',member.name)
                    if member.isfile():
                        self.assertIn(member.mode,(0o644,0o755))

if __name__=='__main__': unittest.main()
