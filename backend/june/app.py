"""FastAPI owns local model HTTP connections and speech subprocess lifetimes."""
import asyncio
from contextlib import aclosing, asynccontextmanager, suppress
import json
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse
import httpx
from starlette.requests import ClientDisconnect

from .chat import model_status, stream_chat, validate_chat
from .memory import Store
from .memory_service import Coordinator, persisted_chat
from .memory_api import router as memory_router
from .config import Settings, VERSION
from .errors import JuneError
from .speech import SpeechService, MAX_AUDIO_BYTES
from .realtime_assets import RealtimeAssets
from .realtime_socket import VoiceSlots, voice_socket
from .native_audio import NativeAudioService
from .voice_api import router as voice_router
from .voice_runtime import VoiceRuntime


@asynccontextmanager
async def lifespan(app):
    app.state.settings = Settings.from_env()
    app.state.coordinator = Coordinator()
    try:
        app.state.store = Store(app.state.settings.data_home)
    except JuneError:
        app.state.store = None
    app.state.speech = SpeechService(app.state.settings)
    app.state.voice_assets = RealtimeAssets(app.state.settings)
    app.state.voice_slots = VoiceSlots()
    app.state.native_audio = NativeAudioService(app.state.settings.audio_home)
    async with httpx.AsyncClient(timeout=httpx.Timeout(180, connect=5), trust_env=False,
                                 limits=httpx.Limits(max_connections=6, max_keepalive_connections=3)) as client:
        app.state.client = client
        app.state.voice_runtime = VoiceRuntime(app.state.settings,client,app.state.speech,app.state.native_audio,app.state.voice_assets,app.state.coordinator,app.state.store)
        app.state.voice_runtime.start()
        async def sweep():
            while True:
                await asyncio.sleep(60)
                if app.state.store:
                    try: app.state.store.cleanup()
                    except JuneError: pass  # Next access exposes the failure; no data is claimed saved.
        sweeper=asyncio.create_task(sweep())
        try: yield
        finally:
            sweeper.cancel()
            await app.state.voice_runtime.close()
            await app.state.native_audio.close()
            if hasattr(app.state.speech,'close'):await app.state.speech.close()
            await app.state.coordinator.cancel()
            with suppress(asyncio.CancelledError):await sweeper


app = FastAPI(title='June local backend', version=VERSION, lifespan=lifespan)


class CancellableStream(StreamingResponse):
    async def __call__(self, scope, receive, send):
        # Keep an active disconnect listener even with ASGI 2.4+. Waiting for
        # the next model token before noticing Stop would leave inference open.
        scope = {**scope, 'asgi': {**scope.get('asgi', {}), 'spec_version': '2.3'}}
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self.body_iterator.aclose()


def local_host(host, settings):
    try:
        url = urlsplit('http://' + host)
        return (url.hostname in ('127.0.0.1', 'localhost', '::1')
                and url.port == urlsplit(settings.backend).port
                and not url.username and not url.password and not url.path and not url.query and not url.fragment)
    except ValueError:
        return False


class LocalOnly:
    """ASGI middleware keeps disconnects intact; no buffering/task wrapper."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = dict(scope.get('headers', []))
        host = headers.get(b'host', b'').decode('latin1')
        origin = headers.get(b'origin', b'').decode('latin1')
        if not local_host(host, scope['app'].state.settings) or (origin and origin != 'http://' + host):
            error = {'code': 'origin', 'message': 'Open June’s local page to use this service.'}
            response = JSONResponse({'error': error} if '/speech/' in scope['path'] else {'message': error['message']}, status_code=403)
            return await response(scope, receive, send)

        async def safe_send(message):
            if message['type'] == 'http.response.start':
                headers = [(key, value) for key, value in message.get('headers', []) if key not in (b'cache-control', b'x-content-type-options')]
                message = {**message, 'headers': [*headers, (b'cache-control', b'no-store, no-transform'), (b'x-content-type-options', b'nosniff')]}
            await send(message)
        await self.app(scope, receive, safe_send)


app.add_middleware(LocalOnly)
app.include_router(memory_router)
app.include_router(voice_router)


@app.exception_handler(JuneError)
async def failure(request, error):
    data = {'error': {'code': error.code, 'message': error.message}} if '/speech/' in request.url.path else {'message': error.message}
    return JSONResponse(data, status_code=error.status)


async def bounded_body(request, limit, speech=False):
    try:
        length = int(request.headers.get('content-length', '0'))
    except ValueError:
        raise JuneError('invalid-request', 'Invalid request size.', 400)
    if length > limit:
        raise JuneError('too-large', 'Audio is too large. Record at most 30 seconds.' if speech else 'The message request is too large.', 413 if speech else 400)
    body = bytearray()
    async for part in request.stream():
        if len(body) + len(part) > limit:
            raise JuneError('too-large', 'Audio is too large. Record at most 30 seconds.' if speech else 'The message request is too large.', 413 if speech else 400)
        body.extend(part)
    return bytes(body)


@app.get('/health')
async def health():
    return {'service': 'june-python', 'version': VERSION, 'state': 'ready'}


@app.get('/api/status')
async def status(request: Request):
    return await model_status(request.app.state.client, request.app.state.settings)


@app.post('/api/chat')
async def chat(request: Request):
    try:
        value = json.loads(await bounded_body(request, 32000))
        mode, messages = validate_chat(value)
    except (ValueError, UnicodeError, RecursionError):
        raise JuneError('invalid-chat', 'The message request was not valid JSON or was too large.', 400)
    if request.app.state.store is None and value.get('temporary') is not True:
        raise JuneError('storage','Private storage is unavailable. Retry or explicitly choose temporary chat.',503)
    if mode == 'local' and not value.get('conversationId'):
        available = await status(request)
        if available['state'] != 'ready':
            raise JuneError('model-unavailable', available['message'])

    async def events():
        # StreamingResponse cancels this iterator on disconnect. No background
        # model task is detached from its browser request.
        try:
            async with aclosing(persisted_chat(request.app.state.client, request.app.state.settings, request.app.state.store, request.app.state.coordinator, value, mode, messages)) as source:
                async for event in source:
                    yield json.dumps(event, ensure_ascii=False).encode() + b'\n'
        except JuneError as error:
            yield json.dumps({'type':'error','message':error.message}).encode()+b'\n'
    return CancellableStream(events(), media_type='application/x-ndjson')


@app.get('/api/speech/status')
async def speech_status(request: Request):
    return await request.app.state.speech.status()


@app.get('/api/voice/status')
async def realtime_status(request: Request):
    state=request.app.state
    result=await state.voice_assets.status()
    audio=await state.native_audio.status()
    speech=await state.speech.status()
    runtime=state.voice_runtime
    await runtime.refresh_model()
    if result['state']=='ready' and speech['state']!='ready':result={'state':'setup-required','message':speech['message']}
    if result['state']=='ready' and audio['state']!='ready':result={'state':'setup-required','message':audio['message']}
    whisper_warm=bool(speech.get('warm',getattr(state.speech,'warm_ready',False)))
    if result['state']=='ready' and runtime.enabled and not (runtime.model_warm and runtime.detectors_warm and whisper_warm and audio.get('voiceWarm')):
        result={'state':'preparing','message':runtime.message}
        runtime.retry_preparation()
    return {**result,'busy':state.voice_slots.owner is not None,'wakePhrase':'Hey June',
        'transport':'local-websocket','model':'Whisper base.en','audioEngine':'mac-native',
        'nativeReady':audio.get('nativeReady',False),'permission':audio.get('permission','unknown'),
        'whisperWarm':whisper_warm,'modelWarm':runtime.model_warm,'voiceWarm':audio.get('voiceWarm',False)}


@app.websocket('/ws/voice')
async def realtime(socket: WebSocket):
    settings = socket.app.state.settings
    if not local_host(socket.headers.get('host', ''), settings) or socket.headers.get('origin') not in settings.web_origins:
        await socket.close(code=1008)
        return
    await socket.app.state.coordinator.cancel('extract')
    await voice_socket(socket, socket.app.state.voice_assets, socket.app.state.voice_slots, socket.app.state.speech, socket.app.state.native_audio, socket.app.state.voice_runtime)


async def until_disconnect(request, operation):
    """Stop a subprocess operation when its HTTP caller disappears."""
    async def disconnected():
        while True:
            event = await request.receive()
            if event['type'] == 'http.disconnect':
                return
    work, watcher = asyncio.create_task(operation), asyncio.create_task(disconnected())
    try:
        done, _ = await asyncio.wait((work, watcher), return_when=asyncio.FIRST_COMPLETED)
        if work in done:
            return await work
        raise JuneError('cancelled', 'Transcription cancelled.', 499)
    finally:
        for task in (work, watcher):
            if not task.done():
                task.cancel()
        for task in (work, watcher):
            with suppress(asyncio.CancelledError, JuneError):
                await task


@app.post('/api/speech/transcribe')
async def transcribe(request: Request):
    if request.headers.get('content-type', '').split(';')[0].strip() != 'audio/wav':
        raise JuneError('format', 'Send a WAV recording from June’s listening controls.', 415)
    try:
        await request.app.state.coordinator.cancel('extract')
        data = await bounded_body(request, MAX_AUDIO_BYTES, True)
        return await until_disconnect(request, request.app.state.speech.transcribe(data))
    except ClientDisconnect:
        raise JuneError('cancelled', 'Transcription cancelled.', 499)


@app.websocket('/ws/chat')
async def socket_chat(socket: WebSocket):
    settings = socket.app.state.settings
    if not local_host(socket.headers.get('host', ''), settings) or socket.headers.get('origin') not in settings.web_origins:
        await socket.close(code=1008)
        return
    await socket.accept()
    active = None
    send_lock = asyncio.Lock()

    async def send(event):
        async with send_lock:
            await socket.send_json(event)

    async def generate(mode, messages, value):
        if mode == 'local' and not value.get('conversationId'):
            available = await model_status(socket.app.state.client, settings)
            if available['state'] != 'ready':
                await send({'type': 'error', 'message': available['message']})
                return
        try:
            async with aclosing(persisted_chat(socket.app.state.client, settings, socket.app.state.store, socket.app.state.coordinator, value, mode, messages)) as source:
                async for event in source:
                    await send(event)
        except JuneError as error:
            await send({'type':'error','message':error.message})

    async def stop():
        nonlocal active
        if active is not None:
            active.cancel()
            with suppress(asyncio.CancelledError, WebSocketDisconnect, RuntimeError):
                await active
            active = None

    try:
        while True:
            incoming = await socket.receive()
            if incoming['type'] == 'websocket.disconnect':
                break
            if not isinstance(incoming.get('text'), str):
                await socket.close(code=1003, reason='Use text JSON messages.')
                break
            text = incoming['text']
            if len(text.encode()) > 32000:
                await send({'type': 'error', 'message': 'The message request is too large.'})
                continue
            try:
                value = json.loads(text)
                if isinstance(value, dict) and value.get('type') == 'cancel':
                    await stop()
                    await send({'type': 'stopped'})
                    continue
                mode, messages = validate_chat(value)
                if active is not None and not active.done():
                    await send({'type': 'error', 'message': 'A reply is already running. Stop it before starting another.'})
                    continue
                await stop()
                active = asyncio.create_task(generate(mode, messages, value))
            except (ValueError, UnicodeError, RecursionError):
                await send({'type': 'error', 'message': 'Send valid JSON.'})
            except JuneError as error:
                await send({'type': 'error', 'message': error.message})
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        await stop()
