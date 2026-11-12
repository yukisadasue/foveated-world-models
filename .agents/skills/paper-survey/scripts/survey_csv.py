#!/usr/bin/env python3
"""Offline CSV operations. No networking or model invocation. Single host writer."""
import argparse
import csv
import datetime as dt
import difflib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import unicodedata

FIELDS = 'social_background technical_background problem method results contributions summary remaining_issues'.split()
SCHEMAS = {
 'papers': 'paper_id title authors keywords_author keywords_survey first_published version version_date venue venue_status paper_url fulltext_url ' + ' '.join(FIELDS) + ' read_scope status review_status reader_model retrieved_at',
 'evidence': 'paper_id field item_index kind source_url locator note',
 'registry': 'paper_id title authors arxiv_id doi semantic_scholar_id paper_url version status selected priority priority_reason assigned_to assignment_model duplicate_of',
 'search_log': 'search_id source query filters searched_at coverage stop_reason',
 'citations': 'citing_id cited_id cited_title cited_url locator priority_reason scope_status',
}
SCHEMAS = {k:v.split() for k,v in SCHEMAS.items()}
CONFIG = Path(__file__).resolve().parents[1] / 'config.json'

def read(path):
 with Path(path).open(encoding='utf-8-sig', newline='') as f:
  reader = csv.DictReader(f)
  header = reader.fieldnames
  if not header or len(header) != len(set(header)):
   raise ValueError(f'{path}: missing/duplicate header')
  rows = list(reader)
  if any(None in r or any(v is None for v in r.values()) for r in rows):
   raise ValueError(f'{path}: malformed row length')
  return header, rows

def write(path, header, rows, encoding='utf-8'):
 path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
 if path.exists():
  hist=path.parent/'history'; hist.mkdir(exist_ok=True)
  shutil.copy2(path, hist/(path.stem+'-'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%f')+'.csv'))
 fd, name = tempfile.mkstemp(dir=path.parent, prefix='.'+path.name)
 try:
  with os.fdopen(fd,'w',encoding=encoding,newline='') as f:
   writer=csv.DictWriter(f,fieldnames=header);writer.writeheader();writer.writerows(rows)
  os.replace(name,path)
 finally:
  if os.path.exists(name):os.unlink(name)

def norm(s):
 return re.sub(r'[^\w]+',' ',unicodedata.normalize('NFKC',s).casefold()).strip()

def arxiv(s):
 s=re.sub(r'^https?://(?:export\.)?arxiv.org/(?:abs|pdf|html)/','',s.strip(),flags=re.I)
 s=re.sub(r'^arxiv:\s*','',s,flags=re.I)
 return re.sub(r'v\d+$','',re.sub(r'\.pdf$','',s)).casefold()

def doi(s):
 return re.sub(r'^(?:https?://(?:dx\.)?doi.org/|doi:\s*)','',s.strip(),flags=re.I).casefold()

def matches(a,b):
 for key,fn in [('arxiv_id',arxiv),('doi',doi),('semantic_scholar_id',str.casefold)]:
  if a.get(key) and b.get(key) and fn(a[key])==fn(b[key]):return 'id_match:'+key
 if a.get('paper_url') and a['paper_url']==b.get('paper_url'):return 'same_url_review'
 ta,tb=norm(a.get('title','')),norm(b.get('title',''))
 if ta and ta==tb:return 'same_title_review'
 if ta and tb and difflib.SequenceMatcher(None,ta,tb).ratio()>=.92:return 'similar_title_review'
 return None

def validate(root):
 errors=[]
 try:
  ph, papers=read(root/'papers.csv');eh,evidence=read(root/'evidence.csv')
  for name,h in [('papers',ph),('evidence',eh)]:
   if not set(SCHEMAS[name])<=set(h):errors.append(name+': missing columns')
  for name in ['registry','search_log','citations']:
   path=root/(name+'.csv')
   if path.exists():
    header, items=read(path)
    if not set(SCHEMAS[name])<=set(header):
     errors.append(name+': missing columns');continue
    if name=='registry':
     known={r['paper_id'] for r in items}
     if '' in known or len(known)!=len(items):errors.append('registry: empty/duplicate paper_id')
     for r in items:
      if r['selected'] not in ['true','false']:errors.append('registry: invalid selected')
      if r['status'] not in ['candidate','pending','assigned','extracted','reviewed','partial','fulltext_unavailable','excluded']:errors.append('registry: invalid status')
      if r['duplicate_of'] and (r['duplicate_of'] not in known or r['duplicate_of']==r['paper_id']):errors.append('registry: invalid duplicate target')
      if r['assigned_to'] and not r['assignment_model']:errors.append('registry: assignment model missing')
      try:int(r['priority'])
      except ValueError:errors.append('registry: invalid priority')
    if name=='citations':
     for r in items:
      if not r['citing_id'] or not r['cited_title'] or r['scope_status'] not in ['in_scope','foundational_outside_scope','unresolved']:errors.append('citations: invalid relationship')
  if (root/'registry.csv').exists():
   rh, rr=read(root/'registry.csv')
   if set(SCHEMAS['registry'])<=set(rh):
    byid={r['paper_id']:r for r in rr}
    for r in rr:
     seen=set();current=r['paper_id']
     while current in byid and byid[current]['duplicate_of']:
      if current in seen:errors.append('registry: duplicate cycle');break
      seen.add(current);current=byid[current]['duplicate_of']
    for p in papers:
     if p.get('paper_id') not in byid:errors.append('papers: ID missing from registry')
    if (root/'citations.csv').exists():
     ch, cr=read(root/'citations.csv')
     if set(SCHEMAS['citations'])<=set(ch):
      for c in cr:
       if c['citing_id'] not in byid or (c['cited_id'] and c['cited_id'] not in byid):errors.append('citations: unresolved registry ID')
  ids=set(); lengths={}
  for p in papers:
   pid=p.get('paper_id','')
   if not pid or pid in ids:errors.append('empty/duplicate paper_id: '+pid)
   ids.add(pid)
   for f in ['title','paper_url','read_scope','reader_model']:
    if not p.get(f):errors.append(pid+': missing '+f)
   if p.get('status')=='extracted':
    for f in ['version','version_date','fulltext_url','retrieved_at']:
     if not p.get(f) or p.get(f)=='unknown':errors.append(pid+': extracted requires '+f)
    for f in ['paper_url','fulltext_url']:
     if not re.match(r'^https?://[^/\s]+',p.get(f,'')):errors.append(pid+': invalid URL '+f)
    try:dt.datetime.fromisoformat(p.get('retrieved_at','').replace('Z','+00:00'))
    except ValueError:errors.append(pid+': invalid retrieved_at')
   for f in FIELDS+['authors' ,'keywords_author','keywords_survey']:
    try:
     val=json.loads(p[f]); assert isinstance(val,list) and all(isinstance(x,str) and x.strip() for x in val)
     if f in FIELDS:assert val
     lengths[pid,f]=len(val)
    except (KeyError,ValueError,AssertionError):errors.append(pid+': invalid list '+f)
   for f in ['first_published','version_date']:
    v=p.get(f,'')
    try:
     if v!='unknown':
      assert re.fullmatch(r'\d{4}(?:-\d{2}){0,2}',v)
      dt.date.fromisoformat(v+('-01-01' if len(v)==4 else '-01' if len(v)==7 else ''))
    except (ValueError,AssertionError):errors.append(pid+': invalid date '+f)
   if p.get('status') not in ['partial','fulltext_unavailable','extracted']:errors.append(pid+': invalid status')
   if p.get('review_status') not in ['pending','changes_requested','reviewed']:errors.append(pid+': invalid review_status')
   if p.get('review_status')=='reviewed' and p.get('status')!='extracted':errors.append(pid+': incomplete cannot be reviewed')
  covered=set()
  for e in evidence:
   pid,f=e.get('paper_id'),e.get('field')
   try:
    i=int(e.get('item_index',''));assert 1<=i<=lengths.get((pid,f),0)
    key=(pid,f,i);assert key not in covered;covered.add(key)
   except (ValueError,AssertionError):errors.append(str(pid)+': invalid/duplicate evidence index');continue
   kind=e.get('kind')
   if kind not in ['author_claim','demonstrated','interpretation','not_stated','unverified','not_applicable']:errors.append(str(pid)+': invalid evidence kind')
   if kind not in ['unverified','not_applicable','not_stated'] and (not e.get('source_url') or not e.get('locator')):errors.append(str(pid)+': missing evidence URL/location')
   if not e.get('note'):errors.append(str(pid)+': missing evidence note')
  for p in papers:
   if p.get('status')=='extracted':
    for f in FIELDS:
     for i in range(1,lengths.get((p['paper_id'],f),0)+1):
      if (p['paper_id'],f,i) not in covered:errors.append(p['paper_id']+': uncovered '+f+':'+str(i))
 except (OSError,ValueError) as ex:errors.append(str(ex))
 return errors


LABELS = dict(zip(SCHEMAS['papers'], [
 '論文ID','タイトル','著者','キーワード（著者）','キーワード（調査）','初回公開日','版','版公開日',
 '学会・誌名','採択確認状況','論文URL','本文URL','社会的背景','技術的背景','取り組む課題',
 '解決手段','結果','貢献','まとめ','残った課題','確認範囲','調査状態','レビュー状態','調査モデル','取得日時']))
KINDS = dict(author_claim='著者の主張', demonstrated='実証結果', interpretation='調査者の解釈',
             not_stated='記載なし', unverified='未確認', not_applicable='該当なし')

def export(root, replace_reviewed=False):
 errors=validate(root)
 if errors:raise ValueError('export validation failed: '+ '; '.join(errors))
 header,papers=read(root/'papers.csv');_,evidence=read(root/'evidence.csv')
 citations=read(root/'citations.csv')[1] if (root/'citations.csv').exists() else []
 ids={p['paper_id'] for p in papers}
 if any(c['citing_id'] not in ids for c in citations):
  raise ValueError('citation source has no paper row; resolve before export')
 labels=[LABELS.get(k,k) for k in header]+['根拠','重要な引用先']
 if len(labels)!=len(set(labels)):raise ValueError('export column name collision')
 rows=[]
 for p in papers:
  row={LABELS.get(k,k):v for k,v in p.items()}
  for key in FIELDS+['authors','keywords_author','keywords_survey']:
   row[LABELS[key]]='\n'.join(f'{i}. {item}' for i,item in enumerate(json.loads(p[key]),1))
  ev=[]
  for e in evidence:
   if e['paper_id']!=p['paper_id']:continue
   ev.append(f"{LABELS[e['field']]} {e['item_index']} [{KINDS[e['kind']]}]\n"
             f"{e['source_url']}\n{e['locator']}\n{e['note']}")
  row['根拠']='\n\n'.join(ev)
  refs=[]
  for c in citations:
   if c['citing_id']!=p['paper_id']:continue
   refs.append(f"{len(refs)+1}. {c['cited_title']} (ID: {c['cited_id'] or '未登録'})\n"
               f"{c['cited_url']}\n引用位置: {c['locator']}\n"
               f"優先理由: {c['priority_reason']}\n範囲: {c['scope_status']}")
  row['重要な引用先']='\n\n'.join(refs)
  rows.append(row)
 output=root/'survey.csv'
 if output.exists():
  old_header,old_rows=read(output)
  if old_header==labels and old_rows==rows:
   return {'output':str(output),'papers':len(rows),'evidence':len(evidence),'citations':len(citations),'unchanged':True}
  if not replace_reviewed:
   raise ValueError('survey.csv differs; review existing edits and source changes before --replace-reviewed; old output will be archived')
 write(output,labels,rows,encoding='utf-8-sig')
 return {'output':str(output),'papers':len(rows),'evidence':len(evidence),'citations':len(citations),'unchanged':False}

def main():
 parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='cmd',required=True)
 p=sub.add_parser('init');p.add_argument('directory',type=Path)
 p=sub.add_parser('query');p.add_argument('csv',type=Path);p.add_argument('--contains',default='');p.add_argument('--where',action='append',default=[]);p.add_argument('--columns');p.add_argument('--limit',type=int,default=50)
 p=sub.add_parser('duplicates');p.add_argument('csv',type=Path)
 p=sub.add_parser('mark-duplicate');p.add_argument('csv',type=Path);p.add_argument('--keep',required=True);p.add_argument('--drop',required=True)
 p=sub.add_parser('plan');p.add_argument('csv',type=Path);p.add_argument('--target',type=int);p.add_argument('--available-readers',type=int);p.add_argument('--model');p.add_argument('--config',type=Path,default=CONFIG)
 p=sub.add_parser('validate');p.add_argument('directory',type=Path)
 p=sub.add_parser('export');p.add_argument('directory',type=Path);p.add_argument('--replace-reviewed',action='store_true')
 p=sub.add_parser('merge');p.add_argument('destination',type=Path);p.add_argument('source',type=Path);p.add_argument('--key',default='paper_id')
 a=parser.parse_args()
 if a.cmd=='init':
  for name,h in SCHEMAS.items():
   p=a.directory/(name+'.csv')
   if not p.exists():write(p,h,[])
  print('initialized',a.directory);return
 if a.cmd=='export':
  print(json.dumps(export(a.directory,a.replace_reviewed),ensure_ascii=False));return
 if a.cmd=='validate':
  errors=validate(a.directory);print(json.dumps({'valid':not errors,'errors':errors},ensure_ascii=False));return 1 if errors else 0
 if a.cmd=='merge':
  sh,sr=read(a.source)
  if a.destination.exists():dh,dr=read(a.destination)
  else:dh,dr=sh,[]
  if set(sh)!=set(dh):raise ValueError('header mismatch; refusing to discard columns')
  keys=a.key.split(',');index={}
  for row in dr+sr:
   k=tuple(row[x] for x in keys)
   if any(not v for v in k):raise ValueError('empty merge key')
   if k in index and index[k]!=row:raise ValueError('conflict; host must review: '+str(k))
   index[k]=row
  write(a.destination,dh,list(index.values()));print('merged',len(index));return
 h,rows=read(a.csv)
 if a.cmd=='query':
  cols=a.columns.split(',') if a.columns else h
  if not set(cols)<=set(h):raise ValueError('unknown column')
  predicates=[x.split('=',1) for x in a.where]
  if any(len(x)!=2 or x[0] not in h for x in predicates):raise ValueError('where requires known_column=value')
  if a.limit<1:raise ValueError('limit must be positive')
  found=[r for r in rows if all(r[k]==v for k,v in predicates) and a.contains.casefold() in ' '.join(r.values()).casefold()]
  print(json.dumps({'total':len(found),'rows':[{k:r[k] for k in cols} for r in found[:a.limit]]},ensure_ascii=False));return
 if a.cmd=='duplicates':
  for i,r in enumerate(rows):
   for other in rows[:i]:
    reason=matches(r,other)
    if reason:print(json.dumps({'left':other['paper_id'],'right':r['paper_id'],'reason':reason},ensure_ascii=False))
  return
 ids=[r['paper_id'] for r in rows]
 if len(ids)!=len(set(ids)):raise ValueError('duplicate registry primary key')
 if a.cmd=='mark-duplicate':
  if a.keep==a.drop or a.keep not in ids or a.drop not in ids:raise ValueError('invalid IDs')
  keep=rows[ids.index(a.keep)];drop=rows[ids.index(a.drop)]
  if keep['duplicate_of'] or drop['assigned_to'] or drop['status'] in ['extracted','reviewed']:raise ValueError('resolve existing assignments/results or canonical link first')
  drop.update(duplicate_of=a.keep,selected='false',status='excluded');write(a.csv,h,rows);return
 if a.cmd=='plan':
  if not set(SCHEMAS['registry'])<=set(h):raise ValueError('registry: missing columns')
  cfg=json.loads(a.config.read_text());target=a.target if a.target is not None else cfg['default_papers']
  slots=min(cfg['max_agents'],a.available_readers if a.available_readers is not None else cfg['max_agents'])
  size=cfg['max_papers_per_assignment'];model=a.model or cfg['reader_agent']['model']
  if min(target,slots,size)<1:raise ValueError('positive limits required')
  eligible=[r for r in rows if r['selected']=='true' and not r['duplicate_of'] and not r['assigned_to'] and r['status'] in ['pending','candidate']]
  eligible.sort(key=lambda r:(-int(r['priority'] or 0),r['paper_id']))
  selected=eligible[:target];stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%f');batches=[]
  for n,start in enumerate(range(0,len(selected),size)):
   group=selected[start:start+size];aid=stamp+'-'+str(n+1)
   for r in group:r.update(assigned_to=aid,assignment_model=model,status='assigned')
   batches.append({'assignment_id':aid,'wave':n//slots+1,'model':model,'paper_ids':[r['paper_id'] for r in group]})
  manifest={'target':target,'selected':len(selected),'shortfall':max(0,target-len(selected)),'max_parallel_readers':slots,'assignments':batches}
  folder=a.csv.parent/'assignments';folder.mkdir(exist_ok=True)
  # Manifest first: interrupted uncommitted plans must be reconciled against registry.
  with (folder/(stamp+'.json')).open('x',encoding='utf-8') as f:json.dump(manifest,f,ensure_ascii=False,indent=2)
  write(a.csv,h,rows);print(json.dumps(manifest,ensure_ascii=False))

if __name__=='__main__':
 try:raise SystemExit(main() or 0)
 except (ValueError,KeyError,OSError) as e:raise SystemExit(str(e))
