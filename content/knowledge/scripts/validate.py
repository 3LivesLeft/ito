#!/usr/bin/env python3
"""Validate the supported static subset of Micron and the content manifest."""
import argparse, hashlib, json, re, sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]; pages=root/'pages'
p=argparse.ArgumentParser(); p.add_argument('--category'); args=p.parse_args()
m=json.loads((root/'manifest.json').read_text()); sources=json.loads((root/'sources.json').read_text())['sources']; source_ids={x['id'] for x in sources}; errors=[]; warnings=[]
entries=m['pages']; ids=set(); paths=set(); contents={}; link_re=re.compile(r'`\[([^\]\n]+)`:(/page/[a-z0-9_./-]+\.mu)\]')
def fail(msg): errors.append(msg)
if len(source_ids)!=len(sources): fail('duplicate source id')
for source in sources:
 for key in ('id','organisation','title','url','accessed','limitations','relevant_pages'):
  if not source.get(key) and key!='relevant_pages': fail(f"source missing {key}: {source.get('id')}")
 expected=sorted(e.get('id') for e in entries if source.get('id') in e.get('sources',[]))
 if sorted(source.get('relevant_pages',[]))!=expected: fail(f"source mapping mismatch: {source.get('id')}")
 if not str(source.get('url','')).startswith('https://'): fail(f"invalid source URL: {source.get('id')}")
for e in entries:
 for key in ('id','title','category','path','description','version','last_reviewed','sources','safety_critical','review_status','size_bytes','sha256','related_pages','page_type'):
  if key not in e: fail(f"{e.get('id')}: missing {key}")
 if e.get('id') in ids: fail(f"duplicate id {e.get('id')}")
 ids.add(e.get('id'))
 path=e.get('path',''); file=root/path
 if path in paths: fail(f'duplicate path {path}')
 paths.add(path)
 if not path.startswith('pages/') or '..' in Path(path).parts or not file.is_file() or not file.resolve().is_relative_to(pages.resolve()): fail(f'bad path {path}'); continue
 if not e.get('sources') or set(e['sources'])-source_ids: fail(f'missing sources: {path}')
 if not re.fullmatch(r'[a-z0-9-]+',str(e.get('id',''))) or not re.fullmatch(r'[a-z0-9-]+',str(e.get('category',''))): fail(f'invalid id or category: {path}')
 if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',str(e.get('last_reviewed',''))): fail(f'invalid review date: {path}')
 if not isinstance(e.get('safety_critical'),bool) or e.get('review_status') not in ('requires_independent_review','reviewed'): fail(f'invalid review status: {path}')
 if not e.get('description') or not e.get('version'): fail(f'empty metadata: {path}')
 if file.is_symlink() or file.stat().st_mode & 0o111: fail(f'page must be static and non-executable: {path}')
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
  if '..' in Path(match.group(2)).parts or not target.resolve().is_relative_to(pages.resolve()) or not target.is_file(): fail(f'broken or unsafe link: {rel} -> {match.group(2)}')
 stripped=link_re.sub('',body)
 if '`' in stripped or '<script' in stripped.lower() or re.search(r'https?://|<[^>]+>',stripped): fail(f'unsupported markup or external dependency: {rel}')
 if not body.startswith('>'): fail(f'no heading: {rel}')
 if rel!='index.mu' and ':/page/index.mu' not in body: fail(f'no home navigation: {rel}')
 if rel.endswith('/index.mu') and len(f.read_bytes())>1024: warnings.append(f'category index too large: {rel}')
 if rel=='index.mu' and len(f.read_bytes())>2048: warnings.append('main index too large')
 if rel!='index.mu' and not rel.endswith('/index.mu') and 'pages/'+rel not in paths: fail(f'unlisted page: {rel}')
category_targets = {}
for category in {e['category'] for e in entries}:
 category_root = pages / category
 index = category_root / 'index.mu'
 targets = set()
 if index.is_file():
  targets = {target for _, target in link_re.findall(index.read_text())}
  direct_targets = targets.copy()
  for section in category_root.glob('*/index.mu'):
   section_link = '/page/' + section.relative_to(pages).as_posix()
   if section_link in direct_targets:
    targets.update(target for _, target in link_re.findall(section.read_text()))
 category_targets[category] = targets
for e in entries:
 if '/page/' + e['path'][6:] not in category_targets[e['category']]:
  fail(f"not linked from category: {e['path']}")
for cat in {e['category'] for e in entries}:
 if f':/page/{cat}/index.mu' not in (pages/'index.mu').read_text(): fail(f'category not linked from main index: {cat}')
for x in errors: print('ERROR:',x)
for x in warnings: print('WARNING:',x)
print(f"Checked {len(entries)} manifest entries, {len(allfiles)} page files; {len(errors)} errors, {len(warnings)} size warnings.")
sys.exit(bool(errors))
