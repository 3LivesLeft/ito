#!/usr/bin/env python3
"""Optional integration check using installed NomadNet, RNS and urwid.

Run with PYTHONPATH pointing to the NomadNet checkout and its dependencies.
This uses the real Micron parser and urwid widgets with a minimal mock UI.
It does not start a node, test navigation, or exercise a radio.
"""
import pathlib,re,types,urwid
import nomadnet.ui.textui.MicronParser as parser
root=pathlib.Path(__file__).resolve().parents[1]/'pages'
ui=types.SimpleNamespace(colormode=256,screen=urwid.raw_display.Screen(),glyphs={})
parser.nomadnet.NomadNetworkApp.get_shared_instance=lambda:types.SimpleNamespace(ui=ui,config={'textui':{'theme':parser.nomadnet.ui.TextUI.THEME_DARK}})
files=list(root.rglob('*.mu'));failures=[];links=0
for f in files:
 try:
  body=f.read_text(encoding='utf-8');want=re.findall(r'`\[[^\]\n]+`:(/page/[a-z0-9_./-]+\.mu)\]',body);got=[]
  for widget in parser.markup_to_attrmaps(body,url_delegate=types.SimpleNamespace()):
   widget.render((40,),focus=False);w=widget.original_widget
   while hasattr(w,'original_widget'):w=w.original_widget
   if hasattr(w,'get_text'):
    for attr,_ in w.get_text()[1]:
     if isinstance(attr,parser.LinkSpec):got.append(attr.link_target)
  if got!=[':'+x for x in want]:failures.append(f'{f}: parsed link targets differ')
  links+=len(got)
 except Exception as e:failures.append(f'{f}: {type(e).__name__}: {e}')
print(f'Nomad parser: {len(files)} pages, {links} links, {len(failures)} errors')
for e in failures:print(e)
raise SystemExit(bool(failures))
