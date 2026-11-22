#!/usr/bin/env python3
"""Validate the supported static subset of Micron and the content manifest."""
import argparse, hashlib, json, re, sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]; pages=root/'pages'
p=argparse.ArgumentParser(); p.add_argument('--category'); args=p.parse_args()
m=json.loads((root/'manifest.json').read_text()); sources=json.loads((root/'sources.json').read_text())['sources']; source_ids={x['id'] for x in sources}; errors=[]; warnings=[]
entries=m['pages']; ids=set(); paths=set(); contents={}; link_re=re.compile(r'`\[([^\]\n]+)`:(/page/[a-z0-9_./-]+\.mu)\]')
def fail(msg): errors.append(msg)
for e in entries:
 for key in ('id','title','category','path','description','version','last_reviewed','sources','safety_critical','review_status','size_bytes','sha256','related_pages','page_type'):
  if key not in e: fail(f"{e.get('id')}: missing {key}")
 if e.get('id') in ids: fail(f"duplicate id {e.get('id')}")
 ids.add(e.get('id'))
 path=e.get('path',''); file=root/path
 if path in paths: fail(f'duplicate path {path}')
 paths.add(path)
 if not path.startswith('pages/') or '..' in Path(path).parts or not file.is_file(): fail(f'bad path {path}'); continue
 if not e.get('sources') or set(e['sources'])-source_ids: fail(f'missing sources: {path}')
 for rel in e.get('related_pages',[]):
  if rel not in {x.get('id') for x in entries}: fail(f'unknown related page: {path} {rel}')
 if args.category and e.get('category') != args.category: continue
 raw=file.read_bytes()
 try: body=raw.decode('utf-8')
 except UnicodeDecodeError: fail(f'invalid UTF-8: {path}'); continue
 if len(raw)!=e.get('size_bytes') or hashlib.sha256(raw).hexdigest()!=e.get('sha256'): fail(f'size/hash mismatch: {path}')
 if body in contents: fail(f'duplicate content: {path} and {contents[body]}')
 contents[body]=path
 if not body.startswith('>'+e['title']+'\n'): fail(f'title mismatch: {path}')
 limit={'quick':1024,'standard':2048,'detailed':4096}.get(e.get('page_type'))
 if not limit: fail(f'unknown page type: {path}')
 elif len(raw)>limit: warnings.append(f'{path}: {len(raw)} bytes exceeds {limit}')
allfiles=list(pages.rglob('*.mu'))
for f in allfiles:
 try: body=f.read_text(encoding='utf-8')
 except UnicodeDecodeError: fail(f'invalid UTF-8: {f}'); continue
 rel=f.relative_to(pages).as_posix(); matches=list(link_re.finditer(body))
 for match in matches:
  target=pages/match.group(2)[6:]
  if not target.is_file(): fail(f'broken link: {rel} -> {match.group(2)}')
 stripped=link_re.sub('',body)
 if '`' in stripped or '<script' in stripped.lower() or re.search(r'https?://|<[^>]+>',stripped): fail(f'unsupported markup or external dependency: {rel}')
 if not body.startswith('>'): fail(f'no heading: {rel}')
 if rel!='index.mu' and ':/page/index.mu' not in body: fail(f'no home navigation: {rel}')
 if rel.endswith('/index.mu') and len(f.read_bytes())>1024: warnings.append(f'category index too large: {rel}')
 if rel=='index.mu' and len(f.read_bytes())>2048: warnings.append('main index too large')
 if rel!='index.mu' and not rel.endswith('/index.mu') and 'pages/'+rel not in paths: fail(f'unlisted page: {rel}')
for e in entries:
 index=pages/e['category']/'index.mu'
 if not index.is_file() or (':/page/'+e['path'][6:]) not in index.read_text(): fail(f"not linked from category: {e['path']}")
for cat in {e['category'] for e in entries}:
 if f':/page/{cat}/index.mu' not in (pages/'index.mu').read_text(): fail(f'category not linked from main index: {cat}')
for x in errors: print('ERROR:',x)
for x in warnings: print('WARNING:',x)
print(f"Checked {len(entries)} manifest entries, {len(allfiles)} page files; {len(errors)} errors, {len(warnings)} size warnings.")
sys.exit(bool(errors))
