#!/usr/bin/env python3
"""Opt-in isolated local parameter comparison. Never changes app configuration."""
import argparse
import asyncio
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import runpy
import statistics
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]


async def main(model):
    runner=runpy.run_path(str(ROOT/'scripts/check-knowledge.py'))
    fixture,_=runner['load_fixtures']()
    sample={**fixture,'cases':[c for c in fixture['cases'] if c['id'] in {'K02','K03','K12','K13','K17'}]}
    sys.path.insert(0,str(ROOT/'backend'))
    import june.knowledge_chat as chat
    original=chat.bounded_json
    output=Path(tempfile.mkdtemp(prefix='knowledge-parameters-',dir=ROOT/'.june-work'));output.chmod(0o700)
    summary=[]
    # Same five questions across profiles; no tuning to individual answers.
    for label,temperature,context,cap in [('default',0,4096,1024),('compact-context',0,2048,1024),('warmer',.2,4096,1024),('short-output',0,4096,512)]:
        path=output/(label+'.json')
        report={'status':'incomplete','imports':[],'cases':[],'startedAt':datetime.now(timezone.utc).isoformat(),
                'scope':'Five-case synthetic parameter probe, not full Phase 7 acceptance.',
                'parameters':{'temperature':temperature,'context':context,'outputCap':cap}}
        async def configured(client,url,payload,*args,**kwargs):
            if url.endswith('/api/chat'):
                payload={**payload,'options':{**payload['options'],'temperature':temperature,'num_ctx':context,'num_predict':cap}}
            return await original(client,url,payload,*args,**kwargs)
        try:
            with patch.object(chat,'bounded_json',configured):
                await runner['evaluate'](SimpleNamespace(model=model,timeout=180),sample,report,path)
            # The acceptance helper correctly requires 20 for its full-suite flag.
            report['subsetPassed']=len(report['cases'])==5 and all(c['passed'] for c in report['cases'])
        except Exception as exc:
            report['status']='blocked';report['error']=f'{type(exc).__name__}: {exc}';report['subsetPassed']=False
        runner['write_report'](path,report)
        times=[c['timings']['answerTurnMs'] for c in report['cases']]
        item={'profile':label,**report['parameters'],'cases':len(report['cases']),
              'passed':sum(c['passed'] for c in report['cases']), 'subsetPassed':report['subsetPassed'],
              'medianAnswerMs':statistics.median(times) if times else None,
              'failures':[{'id':c['id'],'failedChecks':[k for k,v in c['checks'].items() if not v]} for c in report['cases'] if not c['passed']]}
        summary.append(item);runner['write_report'](output/'summary.json',{'profiles':summary,'configurationChanged':False})
        print(json.dumps(item),flush=True)
    print(f'Reports: {output}',flush=True)
    return 0 if len(summary)==4 and all(row['subsetPassed'] for row in summary) else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',action='store_true',required=True)
    parser.add_argument('--model',default=os.environ.get('JUNE_MODEL','qwen3:4b-instruct-2507-q4_K_M'))
    args=parser.parse_args()
    raise SystemExit(asyncio.run(main(args.model)))
