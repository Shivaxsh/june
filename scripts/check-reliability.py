"""Opt-in local acceptance: real Qwen + a private clone of SQLite; no microphone.

Run: PYTHONPATH=backend backend/.venv/bin/python scripts/check-reliability.py
Reports contain private reply text, stay ignored, and must not be published.
The source database is opened read-only and is never edited by this check.
"""
import asyncio
from datetime import datetime
import json
from pathlib import Path
import re
import sqlite3
import time
import uuid

import httpx

from june.config import Settings
from june.memory import Store
from june.memory_service import Coordinator, persisted_chat


async def main():
    settings = Settings.from_env()
    output = Path('.june-work') / ('acceptance-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    data = output / 'isolated-data'
    data.mkdir(parents=True, mode=0o700)
    output.chmod(0o700)
    with sqlite3.connect(f'file:{settings.data_home / "june.sqlite3"}?mode=ro', uri=True) as source:
        with sqlite3.connect(data / 'june.sqlite3') as target:
            source.backup(target)
    store = Store(data)
    coordinator = Coordinator()
    results = []

    def record(case, passed, **details):
        row = dict(case=case, passed=bool(passed), **details)
        results.append(row)
        print(json.dumps({k: row[k] for k in ('case', 'passed')}), flush=True)
        (output / 'results.json').write_text(json.dumps(results, indent=2))
        (output / 'results.json').chmod(0o600)

    async with httpx.AsyncClient(timeout=180, trust_env=False) as client:
        async def ask(query, cid=None):
            cid = cid or store.create_conversation()['id']
            tid = str(uuid.uuid4())
            started = time.perf_counter()
            first = None
            events = []
            async for event in persisted_chat(client, settings, store, coordinator,
                    {'conversationId': cid, 'turnId': tid}, 'local', [{'role': 'user', 'content': query}]):
                events.append(event)
                if event['type'] == 'delta' and first is None:
                    first = round((time.perf_counter() - started) * 1000)
            text = ''.join(e.get('text', '') for e in events if e['type'] == 'delta')
            good = bool(text) and any(e['type'] == 'done' and not e.get('limited') and not e.get('repetitionStopped') for e in events) and not any(e['type'] == 'error' for e in events)
            return text, good, {'firstTextMs': first, 'totalMs': round((time.perf_counter() - started) * 1000), 'answer': text}, events

        for label, query, field in (
            ('approved name after new chat', 'Wait, what is my approved name?', 'name'),
            ('approved colour after new chat', 'Just tell me what my favorite color is.', 'color')):
            from june.app_info import fact_fields
            expected = [f for f in store.snapshot()['memories'] if field in fact_fields(f['text'])]
            text, good, detail, events = await ask(query)
            used = next((e.get('memoryIds', []) for e in events if e['type'] == 'done'), [])
            record(label, good and len(expected) == 1 and used == [expected[0]['id']], **detail)
        store = Store(data)  # Reopen independently: no Python object/session memory.
        text, good, detail, _ = await ask('Tell me my name and my favourite colour.')
        record('approved recall after database reopen', good and text.startswith('Saved memory:'), **detail)

        technical = [
            ('React explanation', 'What is React.js used for? Keep it to two short sentences.', lambda s: bool(re.search(r'interface|\bui\b|component', s, re.I))),
            ('async CPU thread', 'Does putting a heavy CPU loop in an async function move it to another thread? Answer briefly.', lambda s: bool(re.search(r'\bno\b|does not|doesn.t|won.t|not automatically', s, re.I)) and bool(re.search(r'block|main thread|same thread', s, re.I))),
            ('Web Worker DOM', 'Can a Web Worker directly change the DOM? What should it do instead? Answer briefly.', lambda s: bool(re.search(r'\bno\b|cannot|can.t|does not', s, re.I)) and bool(re.search(r'message|postMessage|main thread', s, re.I))),
            ('GPU 5060 correction', 'Repeat my exact graphics-card number: RTX 5060, not 3060. Do not discuss product specs.', lambda s: '5060' in s and not re.search(r'you said (?:RTX )?3060', s, re.I)),
            ('GPU 5070 Ti suffix', 'Repeat exactly the identifier I supplied: RTX 5070 Ti.', lambda s: bool(re.search(r'5070\s*Ti', s, re.I))),
            ('honest booking capability', 'Can you book and pay for a movie ticket for me right now?', lambda s: bool(re.search(r'not connected|cannot|can.t', s, re.I)) and not re.search(r'I (?:have )?(?:booked|paid)', s, re.I)),
        ]
        for label, query, judge in technical:
            text, good, detail, _ = await ask(query)
            record(label, good and judge(text), **detail)

        followup_chat = store.create_conversation()['id']
        await ask('What is a web worker?', followup_chat)
        text, good, detail, _ = await ask('Does async move work to another thread?', followup_chat)
        correct = bool(re.search(r'\bno\b|does not|doesn.t|not automatically|not by itself', text, re.I))
        record('real spoken async follow-up', good and correct and 'C#' not in text, **detail)

        cid = store.create_conversation()['id']
        for n in range(14):
            query = ('For a fictional test, the project code is Copper. Reply with Copper only.' if n == 0 else
                     'For this test the project code changes to Amber. Repeat Amber only.' if n == 11 else
                     'Repeat the latest project code only.')
            expected = 'Amber' if n >= 11 else 'Copper'
            text, good, detail, _ = await ask(query, cid)
            record('long conversation turn ' + str(n + 1), good and expected.casefold() in text.casefold(), **detail)
        record('all fourteen turns persisted', len(store.conversation(cid)['turns']) == 14)

        cid = store.create_conversation()['id']
        await ask('Actually, my favorite color is amber. Acknowledge briefly.', cid)
        text, good, detail, _ = await ask('What is my favorite color?', cid)
        record('current correction takes priority', good and 'amber' in text.casefold(), **detail)
        color = next(f for f in store.snapshot()['memories'] if 'color' in fact_fields(f['text']))
        store.edit_memory(color['id'], 'My favorite color is amber.', False)
        text, good, detail, _ = await ask('What is my favorite color?', cid)
        record('edited fact replaces inference context', good and 'amber' in text.casefold() and not store.context(cid)[:-2], **detail)
        store.delete_memory(color['id'])
        text, good, detail, events = await ask('What is my favorite color?', cid)
        used = next((e.get('memoryIds', []) for e in events if e['type'] == 'done'), [])
        record('deleted fact absent from later context', good and color['id'] not in used and 'amber' not in text.casefold(), **detail)
    print(json.dumps({'report': str(output / 'results.json'), 'passed': sum(r['passed'] for r in results), 'total': len(results)}), flush=True)
    return 0 if all(r['passed'] for r in results) else 1


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
