"""Model adapters: genuine local inference or a deliberately selected demo."""
import asyncio
import json
from pathlib import Path
import httpx

from .errors import JuneError
from .speech_text import ReplyIdentityGuard, model_label
import re

PROMPT = Path(__file__).with_name('prompt.txt').read_text().strip()


def prompt_for_turn(messages, identity):
    latest = messages[-1]['content'] if messages else ''
    if len(identity.focus) == 1 and re.search(r'\b(?:repeat|exact (?:model )?number|(?:number|model) (?:I|you) (?:said|named))\b', latest, re.I):
        # The identifier comes from the user's own words, not product knowledge.
        # This still runs the real model; no simulated answer is substituted.
        target = model_label(next(iter(identity.focus)))
        return PROMPT + f'\nThe latest corrected identifier is {target}, taken from the user’s words. This turn only asks to repeat that identifier. Say: You said {target}. No product specifications are needed.'
    return PROMPT


def validate_chat(value):
    if not isinstance(value, dict):
        raise JuneError('invalid-chat', 'Please send a valid conversation.', 400)
    mode, messages = value.get('mode', 'local'), value.get('messages')
    if mode not in ('local', 'demo') or not isinstance(messages, list) or not 1 <= len(messages) <= 20:
        raise JuneError('invalid-chat', 'Please send a valid conversation. Start a new chat if this one is too long.', 400)
    for i, item in enumerate(messages):
        if (not isinstance(item, dict) or item.get('role') != ('user' if i % 2 == 0 else 'assistant')
                or not isinstance(item.get('content'), str) or not item['content'].strip()
                or len(item['content'].encode('utf-16-le')) // 2 > 2000):
            raise JuneError('invalid-chat', 'Each message needs valid text and a user or assistant role.', 400)
    if len(messages) % 2 != 1:
        raise JuneError('invalid-chat', 'End the conversation with a user message.', 400)
    if sum(len(x['content'].encode('utf-16-le')) // 2 for x in messages) > 6000:
        raise JuneError('context-limit', 'This conversation is getting long for June’s small model. Start a new chat to continue.', 400)
    # Ignore extra fields instead of passing client-supplied metadata to the model.
    return mode, [{'role': x['role'], 'content': x['content']} for x in messages]


async def model_status(client, settings):
    try:
        response = await client.get(settings.ollama + '/api/tags', timeout=5)
        response.raise_for_status()
        models = response.json().get('models')
        if not isinstance(models, list):
            raise ValueError('Invalid model list')
        installed = any(isinstance(x, dict) and x.get('name') == settings.model for x in models)
        return {'state': 'ready' if installed else 'missing', 'model': settings.model,
                'message': 'Ready · runs on this Mac' if installed else 'Model missing. Run npm run model:pull, then reconnect.'}
    except (httpx.HTTPError, ValueError, AttributeError):
        return {'state': 'offline', 'model': settings.model,
                'message': 'Ollama is offline. Start June’s model server, then reconnect.'}


async def model_lines(response):
    """Bound each NDJSON frame, even if the upstream never sends a newline."""
    buffer = bytearray()
    async for chunk in response.aiter_bytes():
        buffer.extend(chunk)
        while b'\n' in buffer:
            line, _, rest = buffer.partition(b'\n')
            buffer = bytearray(rest)
            if len(line) > 1048576:
                raise ValueError('Oversized model frame')
            if line.strip():
                yield json.loads(line)
        if len(buffer) > 1048576:
            raise ValueError('Oversized model frame')
    if buffer.strip():
        yield json.loads(buffer)


async def stream_chat(client, settings, mode, messages):
    if mode == 'demo':
        reply = 'This is a simulated practice reply, not a model answer. The same chat flow will show real replies when you select Local AI and connect Ollama. I’m June — ready to grow one phase at a time.'
        for word in reply.split(' '):
            await asyncio.sleep(.035)
            yield {'type': 'delta', 'text': word + ' '}
        yield {'type': 'done', 'model': 'Simulated demo'}
        return
    try:
        identity = ReplyIdentityGuard(messages)
        async with asyncio.timeout(180):
            async with client.stream('POST', settings.ollama + '/api/chat', json={
                'model': settings.model, 'messages': [{'role': 'system', 'content': prompt_for_turn(messages, identity)}, *messages],
                'stream': True, 'think': False, 'keep_alive': '5m',
                'options': {'num_ctx': 4096, 'num_predict': 256, 'temperature': .1},
            }) as response:
                if response.status_code != 200:
                    raise JuneError('model-failed', 'Model missing. Run npm run model:pull, then reconnect.' if response.status_code == 404
                                    else 'Ollama could not start this reply. Check the model server and try again.')
                async for chunk in model_lines(response):
                    if not isinstance(chunk, dict) or chunk.get('error'):
                        raise JuneError('invalid-stream', 'The model could not finish this reply. Start a new chat or reconnect.')
                    message = chunk.get('message', {})
                    if not isinstance(message, dict) or not isinstance(message.get('content', ''), str):
                        raise ValueError('Invalid model text')
                    if message.get('content'):
                        message['content'].encode('utf-8')
                        for text in identity.push(message['content']):
                            yield {'type': 'delta', 'text': text}
                        if identity.rejected:
                            yield {'type': 'done', 'model': settings.model}
                            return
                    if chunk.get('done') is True:
                        for text in identity.finish():
                            yield {'type': 'delta', 'text': text}
                        yield {'type': 'done', 'model': settings.model}
                        return
                raise JuneError('incomplete', 'The model connection ended before the reply finished. Please try again.')
    except (TimeoutError, httpx.TimeoutException):
        yield {'type': 'error', 'message': 'June took too long to reply. Try a shorter message or reconnect.'}
    except httpx.HTTPError:
        yield {'type': 'error', 'message': 'The model server disconnected. Restart Ollama, then reconnect.'}
    except JuneError as error:
        yield {'type': 'error', 'message': error.message}
    except (ValueError, UnicodeError):
        yield {'type': 'error', 'message': 'Ollama sent an invalid response. Reconnect and try again.'}
    # CancelledError deliberately propagates: context managers close HTTPX.
