#!/usr/bin/env python3
"""Evaluate existing mail/job adapters with synthetic data and the running model.

No Mail/Chrome helper, production store, voice, approval or model-setting writes.
Use backend/.venv/bin/python scripts/evaluate-mail-jobs.py --output <report.json>.
Token checks are screening signals, not a semantic-quality certification.
"""
import argparse
import asyncio
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import httpx
from june import jobs, mail_tools


def memory():
    result={}
    for label,command in [('vm',['vm_stat']),('swap',['sysctl','-n','vm.swapusage'])]:
        try:result[label]=subprocess.check_output(command,text=True,timeout=5).strip()
        except (OSError,subprocess.SubprocessError):result[label]='unavailable'
    return result


async def evaluate(args):
    cases=json.loads((Path(__file__).resolve().parents[1]/'tests/fixtures/assistant-accuracy/cases.json').read_text())
    report=dict(synthetic=True,emails=[],ranking=None,memoryBefore=memory(),modelCalls=[])
    def save():
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2))
    original=mail_tools.bounded_json
    async def measured(*a,**kw):
        started=time.monotonic();row={}
        try:return await original(*a,**kw)
        except BaseException as error:
            row['error']=type(error).__name__
            raise
        finally:
            row['seconds']=round(time.monotonic()-started,2)
            report['modelCalls'].append(row)
    mail_tools.bounded_json=jobs.bounded_json=measured
    async with httpx.AsyncClient(trust_env=False,timeout=330) as client:
        status=(await client.get('http://127.0.0.1:3001/api/status',timeout=15)).json()
        if status.get('state')!='ready':raise RuntimeError('June model is not ready; no inference was started.')
        settings=SimpleNamespace(model=status['model'],ollama='http://127.0.0.1:11434')
        report['model']=settings.model
        save()
        for case in cases['emails'][:args.mail_limit]:
            before=len(report['modelCalls']);started=time.monotonic()
            answer=await mail_tools.summarise(client,settings,dict(name='Synthetic sender',address='sender@example.invalid',subject=case['subject'],text=case['text']))
            checks=[bool(re.search(p,answer,re.I)) for p in case['required']]
            forbidden=[p for p in case['forbidden'] if re.search(p,answer,re.I)]
            call=report['modelCalls'][before:]
            row=dict(id=case['id'],answer=answer,seconds=round(time.monotonic()-started,2),fallback=answer.startswith('It begins:'),passed=all(checks) and not forbidden and not any(c.get('error') for c in call),missing=[p for p,ok in zip(case['required'],checks) if not ok],forbidden=forbidden)
            report['emails'].append(row);save()
            print(json.dumps(row),flush=True)
            if any(c.get('error') in ('TimeoutError','ReadTimeout') for c in call):
                report['stopped']='Model timed out; remaining cases not run under current pressure.'
                break
        if not args.skip_jobs and not report.get('stopped'):
            with tempfile.TemporaryDirectory(prefix='june-accuracy-') as folder:
                service=jobs.Jobs(Path(folder))
                service.upsert(cases['jobs'],'synthetic')
                before=len(report['modelCalls']);started=time.monotonic()
                count=await service.rank(client,settings,cases['resume'],limit=15)
                rows=service.list(limit=30)
                byid={r['id']:r for r in rows}
                pairs=[]
                for better,worse in cases['pairs']:
                    a,b=byid[str(201126000000+better)],byid[str(201126000000+worse)]
                    comparable=a['score'] is not None and b['score'] is not None
                    pairs.append(dict(better=a['title'],worse=b['title'],comparable=comparable,passed=a['score']>b['score'] if comparable else None))
                contradictions=[dict(title=r['title'],reason=r['reason']) for r in rows if any(re.search(p,r['reason'],re.I) for p in cases['forbiddenReasons'])]
                evidenceChecks=[dict(id=n,expected=expected,actual=byid[str(201126000000+int(n))]['score'],passed=byid[str(201126000000+int(n))]['score']==expected) for n,expected in cases['expectedKeywordScores'].items()]
                report['ranking']=dict(method=service.setting('ranking-method'),count=count,unscored=sum(r['score'] is None for r in rows),seconds=round(time.monotonic()-started,2),pairs=pairs,evidenceChecks=evidenceChecks,contradictions=contradictions,rows=[{k:r[k] for k in ('title','score','reason')} for r in rows],errors=report['modelCalls'][before:])
                print(json.dumps(report['ranking']),flush=True)
        report['memoryAfter']=memory();save()
    return 0 if not report.get('stopped') and all(r['passed'] for r in report['emails']) and (args.skip_jobs or report['ranking'] and report['ranking']['count']==15 and not report['ranking']['contradictions'] and all(p['passed'] for p in report['ranking']['pairs'] if p['comparable']) and all(c['passed'] for c in report['ranking']['evidenceChecks'])) else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--mail-limit',type=int,choices=range(0,11),default=10)
    parser.add_argument('--skip-jobs',action='store_true')
    raise SystemExit(asyncio.run(evaluate(parser.parse_args())))
