"""One local native audio graph. IPC contains audio; diagnostics never do."""
import asyncio
import base64
from collections import deque
from contextlib import suppress
import json
import math
from pathlib import Path
import re
import uuid

import anyio

from .errors import JuneError

ID = re.compile(r'[\w-]{1,80}')
NICKY = 'com.apple.ttsbundle.siri_nicky_en-US_compact'
RELEASE_WAIT_SECONDS = 5
CLEANUP_WRITE_SECONDS = 2

def identifier(value):
    return isinstance(value,str) and bool(ID.fullmatch(value))

async def finish_cleanup(awaitable):
    """Finish resource cleanup under AnyIO and repeated asyncio cancellation."""
    with anyio.CancelScope(shield=True):
        task=asyncio.ensure_future(awaitable)
        cancelled=False
        while True:
            try:
                result=await asyncio.shield(task)
                break
            except asyncio.CancelledError:
                if task.cancelled():raise
                cancelled=True
        if cancelled:raise asyncio.CancelledError
        return result

def finite_number(value):
    return type(value) in (int,float) and (type(value) is int or math.isfinite(value))

def validate_speak(value, voices):
    if not isinstance(value,dict) or not all(identifier(value.get(k)) for k in ('ownerId','requestId','segmentId')):
        raise JuneError('voice-request','Invalid voice ownership identifiers.',400)
    text=value.get('text')
    try:units=len(text.encode('utf-16-le'))//2 if isinstance(text,str) else 0
    except UnicodeEncodeError:units=0
    if not units or not text.strip() or units>2000:
        raise JuneError('voice-request','Speech needs between 1 and 2,000 characters.',400)
    if not isinstance(value.get('voiceId'),str) or value['voiceId'] not in {v['id'] for v in voices} or value.get('rate') not in (.98,.92,1.04):
        raise JuneError('voice-request','Choose an installed local female voice and an available expression.',400)
    if 'turnId' in value and (type(value['turnId']) is not int or value['turnId']<0):
        raise JuneError('voice-request','Invalid voice turn.',400)
    if 'voiceSessionId' in value and not identifier(value['voiceSessionId']):
        raise JuneError('voice-request','Invalid voice session.',400)
    return {k:value[k] for k in ('ownerId','requestId','segmentId','text','voiceId','rate','voiceSessionId','turnId') if k in value}

class NativeAudioService:
    def __init__(self, home):
        self.home=Path(home);self.binary=self.home/'JuneAudio.app/Contents/MacOS/JuneAudio'
        self.process=None;self.reader=None;self.heartbeat=None;self.ready=None
        self.start_lock=asyncio.Lock();self.write_lock=asyncio.Lock()
        self.available_voices=[];self.permission='not-determined';self.voice_warm=False
        self.commands={};self.jobs={};self.captures={};self.revoked=deque(maxlen=512)
        self.capture_owner=None;self.capture_session=None;self.capture_turn=0
        self.capture_released=asyncio.Event();self.capture_released.set()
        self.capture_generation=object()
        self.closed=False

    async def ensure_started(self):
        if self.closed:raise JuneError('audio-offline','June Audio is shutting down.',503)
        if not self.binary.is_file():raise JuneError('audio-missing','Run npm run audio:setup to install June Audio.',503)
        async with self.start_lock:
            if self.closed:raise JuneError('audio-offline','June Audio is shutting down.',503)
            if self.process is not None and (self.process.returncode is not None or self.reader is None or self.reader.done()):
                await finish_cleanup(self._terminate_locked(asyncio.current_task()))
            if self.process is None:
                spawn=asyncio.create_task(asyncio.create_subprocess_exec(str(self.binary),stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,limit=1048576))
                try:process=await asyncio.shield(spawn)
                except BaseException:
                    async def reap_spawn():
                        try:child=await spawn
                        except OSError:return
                        await self._reap(child)
                    await finish_cleanup(reap_spawn())
                    raise
                if self.closed:
                    await finish_cleanup(self._reap(process))
                    raise JuneError('audio-offline','June Audio is shutting down.',503)
                self.ready=asyncio.get_running_loop().create_future()
                self.process=process
                self.reader=asyncio.create_task(self.read(process,self.ready))
                self.heartbeat=asyncio.create_task(self.beat(process,self.ready))
            process,ready=self.process,self.ready
        try:await asyncio.wait_for(asyncio.shield(ready),20)
        except asyncio.CancelledError:
            await self.terminate(process,ready)
            raise
        except TimeoutError:
            await self.terminate(process,ready)
            raise JuneError('audio-offline','June Audio did not become ready. Rebuild it and retry.',503)

    async def send(self,value):
        await self._send(value,self.process,self.ready)

    async def _send(self,value,process,ready):
        data=json.dumps(value,ensure_ascii=False).encode()+b'\n'
        if len(data)>32000:raise JuneError('voice-request','The audio command is too large.',400)
        async with self.write_lock:
            if process is None or process is not self.process or ready is not self.ready or process.returncode is not None or process.stdin is None:
                raise JuneError('audio-offline','June Audio stopped. Refresh voice controls to restart it.',503)
            try:
                process.stdin.write(data)
                await asyncio.wait_for(process.stdin.drain(),2)
            except (TimeoutError,BrokenPipeError,ConnectionResetError):
                raise JuneError('audio-offline','June Audio stopped responding. Stop and enable it again.',503)

    async def command(self,kind,timeout=10,**values):
        await self.ensure_started()
        process,ready=self.process,self.ready
        uid=uuid.uuid4().hex;future=asyncio.get_running_loop().create_future();self.commands[uid]=future
        try:
            async with asyncio.timeout(timeout):
                await self.send({'type':kind,'id':uid,**values})
                result=await future
            if result.get('error'):raise JuneError('audio-failed',result['error'],503)
            return result
        except (TimeoutError,asyncio.CancelledError) as error:
            # Prepare has no command-level cancellation in the helper protocol.
            # Retire its worker so a late prepare cannot enqueue audio work.
            if process is not None:await self.terminate(process,ready)
            if isinstance(error,asyncio.CancelledError):raise
            raise JuneError('audio-timeout','June Audio command timed out. Enable it again to retry.',503) from None
        except JuneError as error:
            if error.code=='audio-offline' and process is not None:await self.terminate(process,ready)
            raise
        finally:
            self.commands.pop(uid,None)
            if not future.done():future.cancel()
            if not future.cancelled():future.exception()

    async def beat(self,process,ready):
        try:
            while True:
                await self._send({'type':'heartbeat'},process,ready);await asyncio.sleep(.8)
        except (asyncio.CancelledError,JuneError):pass

    async def read(self,process,ready):
        try:
            while line:=await process.stdout.readline():
                if len(line)>1048576:raise ValueError('Oversized IPC')
                value=json.loads(line)
                if process is not self.process or ready is not self.ready:return
                await self.receive(value)
        except asyncio.CancelledError:return
        except (ValueError,TypeError,OverflowError,OSError,asyncio.LimitOverrunError):pass
        # Stay cancellable while waiting for the lifecycle lock: another retire
        # may hold it and be joining this reader. Once acquired, reap shielded.
        await self._retire(process,ready,asyncio.current_task())

    @staticmethod
    def offer(queue,value):
        if queue.full():
            while not queue.empty():queue.get_nowait()
            queue.put_nowait({'type':'error','error':'Audio processing fell behind. Enable hands-free again.','message':'Audio processing fell behind. Enable hands-free again.'})
        else:queue.put_nowait(value)

    async def receive(self,value):
        if not isinstance(value,dict) or not isinstance(value.get('type'),str):raise ValueError('Invalid IPC')
        kind=value.get('type')
        key='id' if kind in ('result','playback') else 'session' if kind in ('audio','capture-error') else None
        if key and not identifier(value.get(key)):raise ValueError('Invalid IPC identifier')
        if kind=='ready':
            voices=value.get('voices',[])
            if not isinstance(voices,list):raise ValueError('Invalid voices')
            self.available_voices=[v for v in voices if isinstance(v,dict) and isinstance(v.get('id'),str) and v.get('localService') is True]
            self.permission=value.get('permission','not-determined')
            if self.ready and not self.ready.done():self.ready.set_result(True)
        elif kind=='result':
            if value.get('permission'):self.permission=value['permission']
            future=self.commands.get(value.get('id'))
            if future is not None and not future.done():future.set_result(value)
        elif kind=='playback':
            job=self.jobs.get(value.get('id'))
            if job is not None:
                phase=value.get('phase')
                if phase not in ('start','boundary','end','cancelled','error'):raise ValueError('Invalid playback state')
                event={'type':phase,'approximate':True}
                for key in ('firstAudioMs','playbackMs'):
                    if key in value:
                        timing=value[key]
                        if not finite_number(timing) or not 0<=timing<=180000:raise ValueError('Invalid playback timing')
                        event[key]=timing
                if phase=='boundary':
                    index,length=value.get('charIndex',0),value.get('charLength',0)
                    if type(index) is not int or type(length) is not int or min(index,length)<0:raise ValueError('Invalid boundary')
                    level=value.get('level',0)
                    if not finite_number(level):raise ValueError('Invalid boundary level')
                    event.update(charIndex=index,charLength=length,level=max(0,min(1,level)))
                if phase=='error':event['message']='The local voice could not play. Refresh voices or select another installed female voice.'
                self.offer(job['queue'],event)
        elif kind=='audio':
            q=self.captures.get(value.get('session'))
            if q is not None:
                encoded,rms=value.get('pcm',''),value.get('rms',0)
                if not isinstance(encoded,str) or not finite_number(rms):raise ValueError('Invalid audio frame')
                pcm=base64.b64decode(encoded,validate=True)
                if len(pcm)!=640 or not 0<=rms<=1:raise ValueError('Invalid audio frame')
                self.offer(q,{'pcm':pcm,'rms':rms})
        elif kind=='capture-error':
            q=self.captures.get(value.get('session'))
            if q is not None:self.offer(q,{'error':'The audio device changed or capture stopped. Enable hands-free again.'})

    async def status(self):
        if not self.binary.is_file():return {'state':'missing','message':'Run npm run audio:setup to install June Audio. Browser push-to-talk is still available.','permission':self.permission,'nativeReady':False,'voiceWarm':False}
        try:
            await self.ensure_started()
            return {'state':'ready','message':'June Audio · native Mac echo processing ready','permission':self.permission,'nativeReady':True,'voiceWarm':self.voice_warm}
        except (JuneError,OSError) as error:
            return {'state':'error','message':error.message if isinstance(error,JuneError) else 'June Audio could not start. Run npm run audio:setup.','permission':self.permission,'nativeReady':False,'voiceWarm':False}

    async def voices(self):
        status=await self.status()
        return {**status,'voices':self.available_voices if status['state']=='ready' else []}

    async def warm(self):
        await self.ensure_started()
        if not self.voice_warm:
            await self.command('prepare',timeout=20,voiceId=NICKY)
            self.voice_warm=True

    async def capture(self,owner,session):
        if not identifier(owner) or not identifier(session):raise JuneError('voice-request','Invalid capture owner.',400)
        await self.ensure_started()
        if self.capture_owner is not None or any(j['owner']!=owner for j in self.jobs.values()):
            raise JuneError('audio-busy','June Audio is active in another session.',409)
        q=asyncio.Queue(100);self.captures[session]=q
        self.capture_owner=owner;self.capture_session=session;self.capture_turn=0
        self.capture_generation=object()
        self.capture_released.clear()
        try:
            await self.command('capture',timeout=45,session=session)
            return q
        except BaseException:
            await self.release(session)
            raise

    async def release(self,session):
        self.captures.pop(session,None)
        if self.capture_session==session:
            owner=self.capture_owner
            generation=self.capture_generation
            process,ready=self.process,self.ready
            self.capture_session=None;self.capture_turn=0
            async def release_capture():
                try:
                    if owner:await self.stop_owner(owner,session=session)
                    if process is self.process and ready is self.ready:
                        async with asyncio.timeout(CLEANUP_WRITE_SECONDS):
                            await self.send({'type':'release','session':session})
                except (JuneError,TimeoutError,OSError):
                    if process is not None:await self.terminate(process,ready)
                finally:
                    if self.capture_generation is generation and self.capture_session is None:
                        self.capture_owner=None
                        # The pipe is FIFO: manual speech may follow release only now.
                        self.capture_released.set()
            await finish_cleanup(release_capture())

    async def update_turn(self,owner,session,number,interrupted=False):
        if owner==self.capture_owner and session==self.capture_session and number>=self.capture_turn:
            self.capture_turn=number
            if interrupted:await self.stop_owner(owner,session=session)

    async def stop(self,owner,request):
        await finish_cleanup(self._stop_request(owner,request,self.process,self.ready))

    async def _stop_request(self,owner,request,process,ready):
        if (owner,request) not in self.revoked:self.revoked.append((owner,request))
        jobs=[(sid,job) for sid,job in self.jobs.items() if job['owner']==owner and job['request']==request]
        try:
            if process is self.process and ready is self.ready:
                async with asyncio.timeout(CLEANUP_WRITE_SECONDS):
                    await self.send({'type':'stop','ownerId':owner,'requestId':request})
        except (JuneError,TimeoutError,OSError):
            # A blocked pipe must not leave the helper speaking after disconnect.
            if process is not None:await self.terminate(process,ready)
        finally:
            for sid,job in jobs:
                if self.jobs.get(sid) is job:
                    self.jobs.pop(sid,None);self.offer(job['queue'],{'type':'cancelled'})

    async def stop_owner(self,owner,session=None):
        requests={job['request'] for job in self.jobs.values()
                  if job['owner']==owner and (session is None or job.get('voiceSessionId')==session)}
        for request in requests:await self.stop(owner,request)

    async def speak(self,value):
        await self.ensure_started();value=validate_speak(value,self.available_voices)
        owner,request,sid=value['ownerId'],value['requestId'],value['segmentId']
        if self.capture_owner is not None and self.capture_owner!=owner:
            raise JuneError('voice-stale','Another tab owns the audio.',409)
        if 'voiceSessionId' not in value and not self.capture_released.is_set():
            try:await asyncio.wait_for(self.capture_released.wait(),RELEASE_WAIT_SECONDS)
            except TimeoutError:
                raise JuneError('audio-busy','Native capture is still releasing. Retry voice playback.',409) from None
            # Release may have retired an unresponsive helper. Rebind before use.
            await self.ensure_started()
            value=validate_speak(value,self.available_voices)
            if not self.capture_released.is_set():
                raise JuneError('audio-busy','Native capture is active again. Retry voice playback.',409)
        if ((owner,request) in self.revoked or (self.capture_owner is not None and self.capture_owner!=owner)
                or any(job['owner']!=owner for job in self.jobs.values())):
            raise JuneError('voice-stale','This voice request was cancelled or another tab owns the audio.',409)
        if 'voiceSessionId' in value and (value['voiceSessionId']!=self.capture_session or value.get('turnId')!=self.capture_turn):
            raise JuneError('voice-stale','That voice turn is no longer active.',409)
        if sid in self.jobs or len(self.jobs)>=2:raise JuneError('audio-busy','June already has two speech segments queued.',409)
        queue=asyncio.Queue(128);job={'owner':owner,'request':request,'queue':queue,
                                    'voiceSessionId':value.get('voiceSessionId')}
        self.jobs[sid]=job
        process,ready=self.process,self.ready
        completed=False
        try:
            await self.send({'type':'speak','id':sid,**value})
            yield {'type':'accepted'}
            async with asyncio.timeout(180):
                while True:
                    event=await queue.get()
                    # The consumer can close immediately after the terminal yield.
                    completed=event['type']=='end' or (event['type']=='cancelled' and (owner,request) in self.revoked)
                    yield event
                    if event['type'] in ('end','cancelled','error'):break
        except TimeoutError:yield {'type':'error','message':'Speech playback timed out. Choose a shorter reply or retry.'}
        finally:
            if not completed and self.jobs.get(sid) is job:
                await finish_cleanup(self._stop_request(owner,request,process,ready))
            if self.jobs.get(sid) is job:self.jobs.pop(sid,None)

    @staticmethod
    async def _reap(process):
        if process.returncode is None:
            with suppress(ProcessLookupError):process.terminate()
        try:await asyncio.wait_for(process.wait(),2)
        except TimeoutError:
            with suppress(ProcessLookupError):process.kill()
            await asyncio.wait_for(process.wait(),2)

    async def _terminate_locked(self,origin):
        process,ready=self.process,self.ready
        reader,heartbeat=self.reader,self.heartbeat
        for task in (heartbeat,reader):
            if task is not None and task is not origin:task.cancel()
        for task in (heartbeat,reader):
            if task is not None and task is not origin:
                with suppress(asyncio.CancelledError):await task
        if process is not None:await self._reap(process)
        error=JuneError('audio-offline','June Audio disconnected. Enable it again after checking your audio device.',503)
        if ready and not ready.done():
            ready.set_exception(error)
            ready.exception()  # An abandoned startup still needs its exception retrieved.
        for future in list(self.commands.values()):
            if not future.done():future.set_exception(error)
        for job in list(self.jobs.values()):self.offer(job['queue'],{'type':'error','message':error.message})
        for queue in list(self.captures.values()):self.offer(queue,{'error':error.message})
        self.capture_owner=self.capture_session=None;self.capture_turn=0
        self.capture_generation=object();self.capture_released.set()
        self.process=self.reader=self.heartbeat=self.ready=None
        self.voice_warm=False

    async def _retire(self,process,ready,origin):
        async with self.start_lock:
            if process is not None and (self.process is not process or self.ready is not ready):return
            await finish_cleanup(self._terminate_locked(origin))

    async def terminate(self,process=None,ready=None):
        await finish_cleanup(self._retire(process,ready,asyncio.current_task()))

    async def close(self):
        self.closed=True
        if self.capture_session:await self.release(self.capture_session)
        for owner in {j['owner'] for j in self.jobs.values()}:await self.stop_owner(owner)
        await self.terminate()
