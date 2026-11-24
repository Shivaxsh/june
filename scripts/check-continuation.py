#!/usr/bin/env python3
"""Opt-in real-model continuation checks in disposable synthetic stores only."""
import argparse,ast,asyncio,json,re,tempfile,time,uuid,fcntl
from dataclasses import replace
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
import httpx
from june.config import Settings
from june.memory import Store
from june.memory_service import Coordinator,persisted_chat
from june.chat import validate_chat

CASES=[
 ('addition','Write only a Python function add(a, b) that returns their sum. No examples.',
  '```python\ndef add(a, b):\n    return a'),
 ('calculator','Finish this Python calculator with add/subtract/multiply/divide, input error handling and a loop. Use the existing functions and finish main, then invoke main under the standard __name__ guard. No extra examples.',
  '```python\ndef add(a, b): return a + b\ndef subtract(a, b): return a - b\ndef multiply(a, b): return a * b\ndef divide(a, b):\n    if b == 0: raise ValueError("division by zero")\n    return a / b\n\ndef main():\n    operations = {"+": add, "-": subtract, "*": multiply, "/": divide}\n    while True:\n        try:\n            operator = input("Operation (+ - * /), or q: ").strip()\n            if operator == "q":\n                break\n')]

for name,tail in (('newline','\n'),('indent','\n    '),('space','\n    return a '),('tab','\n\t')):
 CASES.append((name,'Write only a Python function add(a, b) that returns their sum. No examples.',
               '```python\ndef add(a, b):'+tail))

async def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run',action='store_true');parser.add_argument('--cases');args=parser.parse_args()
 if not args.run:parser.error('Use --run to authorize local model inference.')
 lock=(ROOT/'.june-work/routing-benchmark.lock').open('w')
 try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:parser.error('Another model benchmark is running')
 output=ROOT/'.june-work'/('continuation-'+uuid.uuid4().hex[:10]);output.mkdir(mode=0o700)
 report={'model':'qwen3:4b-instruct-2507-q4_K_M','defaultsChanged':False,'cases':[]}
 print('Reports:',output,flush=True)
 selected=[c for c in CASES if not args.cases or c[0] in args.cases.split(',')]
 if not selected or (args.cases and set(args.cases.split(','))-{c[0] for c in CASES}):parser.error('Unknown case')
 for name,question,prefix in selected:
  row={'case':name,'segments':[],'passed':False};report['cases'].append(row)
  with tempfile.TemporaryDirectory(prefix='june-cont-') as home:
   settings=replace(Settings.from_env(),model=report['model'])
   store=Store(Path(home));assert store.path.parent.resolve()==Path(home).resolve();coordinator=Coordinator();cid=store.create_conversation()['id'];store.bind_library_chat(cid)
   source='seed';store.start_turn(cid,source,question,store.revision())
   store.finish_library_turn(cid,source,prefix,[],'general',0,output={'limited':True,'incomplete':True})
   assembled=prefix
   async with httpx.AsyncClient(timeout=180,trust_env=False) as client:
    try:
     for n in range(5):
      tid=uuid.uuid4().hex;value={'mode':'local','knowledge':{'mode':'auto'},'conversationId':cid,'turnId':tid,
       'continueTurn':source,'messages':[{'role':'user','content':'Continue.'}]}
      mode,messages=validate_chat(value);started=time.perf_counter()
      events=[e async for e in persisted_chat(client,settings,store,coordinator,value,mode,messages,None)]
      done=events[-1];suffix=''.join(e['text'] for e in events if e['type']=='delta')
      assert done['type']=='done' and done.get('continuedFrom')==source and suffix
      assert not suffix.startswith(assembled[-6000:]),'Echo reached suffix'
      assembled+=suffix;source=tid
      row['segments'].append({'elapsedMs':round((time.perf_counter()-started)*1000),'limited':done['limited'],
        'incomplete':done['incomplete'],'suffixChars':len(suffix)})
      if not done['incomplete']:
       code=re.search(r'```(?:python)?\s*\n([\s\S]*?)\n```',assembled)
       assert code,'Missing complete code fence'
       row['assembled']=assembled
       tree=ast.parse(code[1]);compile(tree,'synthetic-calculator','exec')
       functions={node.name for node in tree.body if isinstance(node,ast.FunctionDef)}
       assert ('add' in functions if name!='calculator' else {'add','subtract','multiply','divide','main'}<=functions)
       assert store.conversation(cid)['resumable'] is None
       row['passed']=True;row['assembled']=assembled;break
     assert row['passed'],'Continuation did not finish within five segments'
    except Exception as exc:row['error']=f'{type(exc).__name__}: {exc}'
    finally:await coordinator.cancel()
  report['status']='completed' if len(report['cases'])==len(selected) else 'running'
  (output/'report.json').write_text(json.dumps(report,indent=2));(output/'report.json').chmod(0o600)
  print(json.dumps({k:v for k,v in row.items() if k!='assembled'}),flush=True)
 return int(not all(r['passed'] for r in report['cases']))

if __name__=='__main__':raise SystemExit(asyncio.run(main()))
