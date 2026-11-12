import contextlib
import csv
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import survey_csv as s

class SurveyTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
 def tearDown(self):self.tmp.cleanup()
 def run_cli(self,*args,ok=True):
  p=subprocess.run([sys.executable,str(Path(s.__file__)),*map(str,args)],capture_output=True,text=True)
  self.assertEqual(p.returncode==0,ok,p.stderr)
  return p.stdout
 def registry(self,n):
  rows=[]
  for i in range(n):
   r=dict.fromkeys(s.SCHEMAS['registry'],'');r.update(paper_id=str(i),title='Paper '+str(i),authors='[]',selected='true',status='pending',priority=str(i));rows.append(r)
  p=self.root/'registry.csv';s.write(p,s.SCHEMAS['registry'],rows);return p
 def test_batches_and_resume(self):
  p=self.registry(65)
  a=json.loads(self.run_cli('plan',p,'--available-readers','3','--model','test-model'))
  self.assertEqual(a['selected'],50);self.assertEqual(len(a['assignments']),5)
  self.assertEqual([x['wave'] for x in a['assignments']],[1,1,1,2,2])
  self.assertTrue(all(len(x['paper_ids'])<=10 and x['model']=='test-model' for x in a['assignments']))
  b=json.loads(self.run_cli('plan',p,'--target','15'))
  self.assertEqual(b['selected'],15)
  self.assertFalse(set(sum([x['paper_ids'] for x in a['assignments']],[])) & set(sum([x['paper_ids'] for x in b['assignments']],[])))
 def test_dedup(self):
  self.assertEqual(s.matches({'arxiv_id':'https://arxiv.org/pdf/2601.12345v2.pdf'},{'arxiv_id':'2601.12345v1'}),'id_match:arxiv_id')
  self.assertEqual(s.matches({'doi':'https://doi.org/10.123/X'},{'doi':'doi:10.123/x'}),'id_match:doi')
  self.assertEqual(s.matches({'title':'A: Paper'},{'title':'a paper'}),'same_title_review')
 def test_merge_preserves_conflict(self):
  a=self.root/'a.csv';b=self.root/'b.csv';h=['paper_id','text']
  s.write(a,h,[{'paper_id':'x','text':'日本語, "quoted"\nnext'}]);s.write(b,h,[{'paper_id':'x','text':'different'}]);old=a.read_bytes()
  self.run_cli('merge',a,b,ok=False);self.assertEqual(old,a.read_bytes())
  s.write(b,h,s.read(a)[1]);self.run_cli('merge',a,b);self.assertEqual(s.read(a)[1][0]['text'],'日本語, "quoted"\nnext')
 def test_evidence_validation(self):
  self.run_cli('init',self.root)
  (self.root/'registry.csv').unlink() # worker-only extraction fixture
  p=dict.fromkeys(s.SCHEMAS['papers'],'')
  p.update(paper_id='p1',title='test',paper_url='https://example.org/p',read_scope='methods results limitations',reader_model='test',first_published='2026-11-12',version='v1',version_date='2026-11-12',fulltext_url='https://example.org/p',retrieved_at='2026-11-12T00:00:00Z',status='extracted',review_status='pending')
  for f in s.FIELDS+['authors','keywords_author','keywords_survey']:p[f]=json.dumps(['test'])
  s.write(self.root/'papers.csv',s.SCHEMAS['papers'],[p]);self.assertTrue(s.validate(self.root))
  ev=[dict(paper_id='p1',field=f,item_index='1',kind='author_claim',source_url='https://example.org/p',locator='section 3',note='test') for f in s.FIELDS]
  s.write(self.root/'evidence.csv',s.SCHEMAS['evidence'],ev);self.assertEqual(s.validate(self.root),[])
  p['first_published']='2026-02-31';s.write(self.root/'papers.csv',s.SCHEMAS['papers'],[p]);self.assertTrue(s.validate(self.root))
 def test_registry_and_manifest(self):
  self.run_cli('init',self.root)
  (self.root/'registry.csv').write_text('invalid\nregistry\n')
  self.assertTrue(s.validate(self.root))
  p=self.registry(1)
  self.run_cli('plan',p,'--model','override')
  self.assertEqual(s.read(p)[1][0]['assignment_model'],'override')
  manifests=list((self.root/'assignments').glob('*.json'))
  self.assertEqual(len(manifests),1)
  self.assertEqual(json.loads(manifests[0].read_text())['assignments'][0]['model'],'override')
 def test_duplicate_mark_retains_rows(self):
  p=self.registry(2);self.run_cli('mark-duplicate',p,'--keep','0','--drop','1');r=s.read(p)[1]
  self.assertEqual(len(r),2);self.assertEqual(r[1]['duplicate_of'],'0');self.assertEqual(r[1]['selected'],'false')

 def test_export_roundtrip_and_edit_preservation(self):
  self.run_cli('init',self.root)
  (self.root/'registry.csv').unlink()
  p=dict.fromkeys(s.SCHEMAS['papers'],'')
  p.update(paper_id='p1',title='日本語, "quoted"',paper_url='https://example.org/p',read_scope='methods',reader_model='test',first_published='2026',version_date='unknown',status='partial',review_status='pending')
  for f in s.FIELDS+['authors','keywords_author','keywords_survey']:p[f]=json.dumps(['日本語, "quoted"\nnext'],ensure_ascii=False)
  s.write(self.root/'papers.csv',s.SCHEMAS['papers'],[p])
  ev=[dict(paper_id='p1',field=f,item_index='1',kind='author_claim',source_url='https://example.org/p',locator='section 3',note='evidence '+f) for f in s.FIELDS]
  s.write(self.root/'evidence.csv',s.SCHEMAS['evidence'],ev)
  c=dict(citing_id='p1',cited_id='',cited_title='未読の引用先',cited_url='https://example.org/c',locator='Ref 1',priority_reason='基礎',scope_status='unresolved')
  s.write(self.root/'citations.csv',s.SCHEMAS['citations'],[c])
  sources={name:(self.root/(name+'.csv')).read_bytes() for name in ['papers','evidence','citations']}
  result=json.loads(self.run_cli('export',self.root))
  self.assertEqual((result['papers'],result['evidence'],result['citations']),(1,8,1))
  target=self.root/'survey.csv';self.assertTrue(target.read_bytes().startswith(b'\xef\xbb\xbf'))
  h,rows=s.read(target)
  self.assertEqual(rows[0]['結果'],'1. 日本語, "quoted"\nnext')
  self.assertEqual(rows[0]['調査状態'],'partial')
  for e in ev:self.assertIn(e['note'],rows[0]['根拠'])
  self.assertIn(c['cited_url'],rows[0]['重要な引用先'])
  self.assertTrue(json.loads(self.run_cli('export',self.root))['unchanged'])
  rows[0]['結果']='ユーザーの変更';s.write(target,h,rows);edited=target.read_bytes()
  self.run_cli('export',self.root,ok=False);self.assertEqual(target.read_bytes(),edited)
  self.run_cli('export',self.root,'--replace-reviewed')
  self.assertTrue(any(x.read_bytes()==edited for x in (self.root/'history').glob('survey-*.csv')))
  for name,data in sources.items():self.assertEqual((self.root/(name+'.csv')).read_bytes(),data)

if __name__=='__main__':unittest.main()
