#!/usr/bin/env python3
"""Opt-in, sequential local-model latency comparison using synthetic inputs only.

Run with backend/.venv/bin/python scripts/profile-latency.py --run.
Variants are diagnostic only: no environment, saved chats, or defaults are changed.
"""
import argparse,ast,asyncio,fcntl,json,re,sys,time,uuid
from dataclasses import replace
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
import httpx
from june.chat import stream_chat
from june.config import Settings

QUESTION='Finish this Python calculator with add/subtract/multiply/divide, input error handling and a loop. Use the existing functions and finish main, then invoke main under the standard __name__ guard. No extra examples.'
PREFIX=('```python\ndef add(a, b): return a + b\ndef subtract(a, b): return a - b\n'
 'def multiply(a, b): return a * b\ndef divide(a, b):\n    if b == 0: raise ValueError("division by zero")\n'
 '    return a / b\n\ndef main():\n    operations = {"+": add, "-": subtract, "*": multiply, "/": divide}\n'
 '    while True:\n        try:\n            operator = input("Operation (+ - * /), or q: ").strip()\n'
 '            if operator == "q":\n                break\n')
VARIANTS=('baseline','batch64','no-hint')

class ProbeClient(httpx.AsyncClient):
 def __init__(self,variant,**kwargs):
  super().__init__(**kwargs);self.variant=variant
 def stream(self,method,url,**kwargs):
  body=kwargs.get('json')
  if body and url.endswith('/api/chat'):
   if self.variant=='batch64':body['options']['num_batch']=64
   if self.variant=='no-hint':
    body['messages'][0]['content']=body['messages'][0]['content'].split('\nContinue the final assistant message from its exact ending.')[0]
  return super().stream(method,url,**kwargs)

def valid_code(text):
 match=re.search(r'```(?:python)?\s*\n(.*?)\n```',text,re.S)
 if not match:return False
 try:
  tree=ast.parse(match[1]);compile(tree,'<synthetic-latency-probe>','exec')
 except (SyntaxError,ValueError):return False
 return {'add','subtract','multiply','divide','main'}<={n.name for n in tree.body if isinstance(n,ast.FunctionDef)}

async def run(args):
 work=ROOT/'.june-work';work.mkdir(exist_ok=True)
 with (work/'routing-benchmark.lock').open('a') as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:raise SystemExit('Another model benchmark is running.')
  folder=work/('latency-'+uuid.uuid4().hex[:10]);folder.mkdir(mode=0o700)
  settings=replace(Settings.from_env(),model='qwen3:4b-instruct-2507-q4_K_M')
  report={'model':settings.model,'defaultsChanged':False,'rows':[]};print('Report:',folder,flush=True)
  for variant in args.variants.split(','):
   async with ProbeClient(variant,timeout=185,trust_env=False) as client:
    for kind in args.cases.split(','):
     for repeat in range(args.repeats):
      ps=(await client.get(settings.ollama+'/api/ps')).json()
      resident=any(m.get('name')==settings.model for m in ps.get('models',[]))
      start=time.perf_counter();reply='';done={};row={'variant':variant,'case':kind,'repeat':repeat+1,'residentAtStart':resident}
      continuation={'question':QUESTION,'prefix':PREFIX} if kind=='continuation' else None
      async for event in stream_chat(client,settings,'local',[{'role':'user','content':'Continue.' if continuation else 'Explain async and await in two short sentences.'}],continuation=continuation):
       if event['type']=='delta' and event['text']:
        row.setdefault('firstVisibleMs',round((time.perf_counter()-start)*1000));reply+=event['text']
       elif event['type']=='done':done=event
       elif event['type']=='error':row['error']=event['message']
      row.update(totalMs=round((time.perf_counter()-start)*1000),modelTimings=done.get('timings',{}),replyChars=len(reply),limited=bool(done.get('limited')))
      row['passed']=bool(done and reply and not done.get('incomplete') and (not continuation or valid_code(PREFIX+reply)))
      report['rows'].append(row)
      path=folder/'report.json';path.write_text(json.dumps(report,indent=2));path.chmod(0o600)
      print(json.dumps(row),flush=True)
  return int(not all(row['passed'] for row in report['rows']))

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--run',action='store_true');parser.add_argument('--variants',default='baseline');parser.add_argument('--cases',default='short,continuation');parser.add_argument('--repeats',type=int,default=2)
 args=parser.parse_args()
 if not args.run:parser.error('Use --run to authorize local synthetic inference.')
 if set(args.variants.split(','))-set(VARIANTS) or set(args.cases.split(','))-{'short','continuation'} or not 1<=args.repeats<=5:parser.error('Invalid variants, cases, or repeats.')
 raise SystemExit(asyncio.run(run(args)))
