"""Exercise failures against disposable copies; no production content is modified."""
import json, shutil, subprocess, tempfile, unittest
from pathlib import Path
SOURCE=Path(__file__).resolve().parents[1]
class ValidatorTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'knowledge';shutil.copytree(SOURCE,self.root)
 def tearDown(self):self.tmp.cleanup()
 def run_check(self, expected):
  r=subprocess.run(['python3',str(self.root/'scripts/validate.py')],capture_output=True,text=True)
  self.assertNotEqual(r.returncode,0);self.assertIn(expected,r.stdout)
 def test_broken_link(self):
  p=self.root/'pages/index.mu';p.write_text(p.read_text()+'`[Missing`:/page/missing.mu]\n');self.run_check('broken or unsafe link')
 def test_malformed_markup(self):
  p=self.root/'pages/index.mu';p.write_text(p.read_text()+'`[Unclosed\n');self.run_check('unsupported markup')
 def test_missing_source(self):
  p=self.root/'manifest.json';m=json.loads(p.read_text());m['pages'][0]['sources'].append('not-a-source');p.write_text(json.dumps(m));self.run_check('missing sources')
 def test_duplicate_id(self):
  p=self.root/'manifest.json';m=json.loads(p.read_text());m['pages'][1]['id']=m['pages'][0]['id'];p.write_text(json.dumps(m));self.run_check('duplicate id')
 def test_path_traversal(self):
  p=self.root/'pages/index.mu';p.write_text(p.read_text()+'`[Escape`:/page/../manifest.json.mu]\n');self.run_check('broken or unsafe link')
 def test_altered_content(self):
  p=self.root/'pages/water/boiling.mu';p.write_text(p.read_text()+'altered\n');self.run_check('size/hash mismatch')
 def test_external_url(self):
  p=self.root/'pages/index.mu';p.write_text(p.read_text()+'https://example.org/test\n');self.run_check('external dependency')
 def test_unlinked_category_section(self):
  index = self.root / 'pages/shelter/index.mu'
  index.write_text(''.join(line for line in index.read_text().splitlines(keepends=True)
                           if ':/page/shelter/outdoors/index.mu]' not in line))
  self.run_check('not linked from category: pages/shelter/tarp.mu')
if __name__=='__main__':unittest.main()
