"""Live check: does the real local model route every phrasing the fixed grammars miss? (opt-in, slow)

Usage: backend/.venv/bin/python scripts/check-commands.py --run
Sends each corpus phrase that no grammar recognises (and each everyday sentence that passes the router's
gate) to the running Ollama model, the way June does, and reports accuracy per intent. The report is
written to .june-work/command-check.json (ignored by Git). Nothing is executed: only routing is checked.
"""
import asyncio
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'backend/tests')]


async def main():
    import httpx
    from corpus_support import family
    from june.intent_router import route, routable
    from phrasing_corpus import NEGATIVE, POSITIVE
    settings = SimpleNamespace(ollama='http://127.0.0.1:11434', model=json.loads((ROOT / 'backend/model-default.json').read_text())['model']
                               if (ROOT / 'backend/model-default.json').exists() else 'qwen3:4b-instruct-2507-q4_K_M')
    cases = [(intent, text) for intent, phrases in POSITIVE.items() for text in phrases if family(text) is None]
    cases += [('none', text) for text in NEGATIVE if routable(text) and not family(text)]
    results, start = [], time.time()
    async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=5), trust_env=False) as client:
        for n, (want, text) in enumerate(cases, 1):
            began = time.time()
            cmd = await route(client, settings, text)
            got = (family(cmd) or 'unrecognised:' + cmd) if cmd else 'none'
            ok = got == want
            results.append(dict(text=text, want=want, command=cmd, got=got, ok=ok, seconds=round(time.time() - began, 1)))
            print(f'{n:3}/{len(cases)} {"ok " if ok else "MISS"} {time.time() - began:5.1f}s  {want:18} {text!r} -> {cmd!r}', flush=True)
    misses = [r for r in results if not r['ok']]
    out = ROOT / '.june-work' / 'command-check.json'
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(dict(when=time.strftime('%Y-%m-%d %H:%M'), model=settings.model, total=len(results), misses=len(misses),
                                   minutes=round((time.time() - start) / 60, 1), results=results), indent=1))
    print(f'\n{len(results) - len(misses)}/{len(results)} routed correctly; report: {out}')
    for r in misses:
        print('MISS', r['want'], repr(r['text']), '->', r['command'])


if __name__ == '__main__':
    if '--run' not in sys.argv:
        sys.exit(__doc__)
    asyncio.run(main())
