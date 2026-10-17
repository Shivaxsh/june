"""Audio turn ownership; independent of sockets, models and React."""
import asyncio
from contextlib import suppress
import re
import struct
import time
from difflib import SequenceMatcher

from .errors import JuneError
from .speech_text import clean_transcript

PAUSES = {'short': .8, 'normal': 1.5, 'patient': 2.5}


def remove_wake_phrase(text):
    return re.sub(r'^\s*hey[\s,;:.!—–-]*june\b[\s,;:.!?—–-]*', '', text, flags=re.I).strip()


def pcm_wav(pcm):
    return struct.pack('<4sI4s4sIHHIIHH4sI', b'RIFF', len(pcm) + 36, b'WAVE',
                       b'fmt ', 16, 1, 1, 16000, 32000, 2, 16, b'data', len(pcm)) + pcm


class VoiceTurn:
    def __init__(self, emit, transcribe, pause='normal', clock=time.monotonic):
        self.emit, self.transcribe, self.clock = emit, transcribe, clock
        self.pause = PAUSES[pause]
        self.phase, self.number = 'waiting', 0
        self.buffer, self.preroll = bytearray(), bytearray()
        self.preroll_voice = bytearray()
        self.silence = self.voiced = 0.
        self.deadline = None
        self.question_deadline = None
        self.reset_pending()
        self.job = None
        self.closed = False
        self.last_wake = float('-inf')
        self.minimum_voiced = .5
        self.interrupt_voiced = 0.
        self.probe = None
        self.probe_number = 0
        self.probe_cooldown = 0.
        self.probe_job = None
        self.spoken = ''

    async def clear_probe(self, resume=True):
        number = self.number
        probe, self.probe = self.probe, None
        self.interrupt_voiced = 0.
        job = self.probe_job
        if job is not None and job is not asyncio.current_task():
            self.probe_job = None
            job.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await job
        if probe and resume:
            await self.emit({'type': 'resume', 'turn': number, 'probe': probe['id']})

    async def probe_paused(self, number, probe):
        if number == self.number and self.probe and self.probe['id'] == probe and self.probe['paused'] is None:
            self.probe['paused'] = self.clock()

    async def probe_cancelled(self, number, probe):
        if number == self.number and self.probe and self.probe['id'] == probe:
            await self.clear_probe()
            if not self.closed and number == self.number:
                await self.state('generating')

    async def interrupt(self):
        # Short pre-roll keeps the user's first word, but not two seconds of
        # June's previous answer. The browser invalidates its request first.
        seconds = (self.clock() - self.probe['started'] + .12) if self.probe else self.interrupt_voiced
        # Quantise to whole PCM16 samples; wall-clock jitter can produce an odd
        # byte count, which would shift every sample and invalidate the WAV.
        size = min(len(self.preroll), int((seconds + .2) * 16000) * 2)
        clip = bytes(self.preroll[-size:])
        self.number += 1
        number = self.number
        await self.emit({'type': 'interrupt', 'turn': number})
        await self.clear_probe(resume=False)
        await self.cancel_job()
        if self.closed or number != self.number:
            return
        self.buffer = bytearray(clip)
        self.reset_pending()
        self.minimum_voiced = .24
        self.voiced, self.silence = .24, 0.
        self.deadline = self.clock() + 10
        self.question_deadline = None
        await self.state('listening')

    def is_new_short_speech(self, text, reference):
        words = re.findall(r'[a-z0-9]+', clean_transcript(text).lower())
        spoken = re.findall(r'[a-z0-9]+', clean_transcript(reference).lower())
        if not words or len(words) > 16:
            return False
        if spoken:
            matching = sum(block.size for block in SequenceMatcher(None, words, spoken, autojunk=False).get_matching_blocks())
            if matching / len(words) >= .7:
                return False
        controls = {'wait', 'stop', 'pause', 'hold', 'no', 'actually', 'sorry', 'okay', 'ok', 'why', 'how'}
        # With no playback reference, accept only explicit controls or a number;
        # otherwise a partial word from a speaker echo is too ambiguous.
        if not spoken or len(words) == 1:
            return bool(controls.intersection(words)) or any(word.isdigit() for word in words)
        return True

    async def check_short_probe(self):
        probe, number = self.probe, self.number
        if not probe or probe.get('checking'):
            return
        probe['checking'] = True
        size = min(len(self.preroll), int((self.clock() - probe['started'] + .32) * 16000) * 2)
        clip = pcm_wav(bytes(self.preroll[-size:]))

        async def verify():
            try:
                # This path preserves a brief "wait" that ended before the
                # echo-settling window. It does not require sustained speech.
                result = await asyncio.wait_for(self.transcribe(clip), 8)
                if self.closed or number != self.number or self.probe is not probe:
                    return
                text = remove_wake_phrase(clean_transcript(result['text']))
                if self.is_new_short_speech(text, probe['spoken']):
                    accepted = number + 1
                    self.number = accepted
                    await self.emit({'type': 'interrupt', 'turn': accepted})
                    if self.closed or self.number != accepted:
                        return
                    await self.clear_probe(resume=False)
                    await self.cancel_job()
                    if self.closed or self.number != accepted:
                        return
                    self.buffer.clear(); self.preroll.clear(); self.preroll_voice.clear()
                    self.reset_pending(); self.question_deadline = self.deadline = None
                    await self.state('generating')
                    if not self.closed and self.number == accepted:
                        await self.emit({'type': 'transcript', 'turn': accepted, 'text': text, 'durationMs': result['durationMs']})
                    return
            except (JuneError, TimeoutError, ValueError, KeyError, TypeError):
                pass
            if not self.closed and number == self.number and self.probe is probe:
                await self.clear_probe()
                self.probe_cooldown = self.clock() + .4
        async def owned():
            try:
                await verify()
            finally:
                if self.probe_job is asyncio.current_task():
                    self.probe_job = None
        self.probe_job = asyncio.create_task(owned())

    async def consider_interruption(self, voiced, duration, now):
        if self.probe:
            paused = self.probe['paused']
            # Let speaker output and the detector's short history settle after
            # the browser acknowledges pausing. Continued speech is barge-in.
            if paused is not None and now - paused >= .25:
                self.probe['voiced'] = self.probe['voiced'] + duration if voiced else 0.
                if self.probe['voiced'] + 1e-6 >= .18:
                    await self.interrupt()
                elif now - paused >= .8:
                    await self.check_short_probe()
            return
        self.interrupt_voiced = self.interrupt_voiced + duration if voiced else 0.
        if self.phase == 'generating' and self.interrupt_voiced + 1e-6 >= .24:
            await self.interrupt()
        elif self.phase == 'speaking' and now >= self.probe_cooldown and self.interrupt_voiced + 1e-6 >= .12:
            self.probe_number += 1
            self.probe = {'id': self.probe_number, 'started': now, 'paused': None, 'voiced': 0., 'spoken': self.spoken}
            await self.emit({'type': 'probe', 'turn': self.number, 'probe': self.probe_number})

    def reset_pending(self):
        # Only provisional audio while identifying a wake-only utterance.
        # If the original clip contains a question, discard this room audio.
        self.pending_question = bytearray()
        self.pending_started = None
        self.pending_voiced = self.pending_silence = 0.
        self.pending_finished = False

    def pending_audio(self, pcm, voiced, now, duration):
        if self.question_deadline is None or self.pending_finished:
            return
        if self.pending_started is None:
            if not voiced or now > self.question_deadline:
                return
            self.pending_started = now
            self.pending_question.extend(self.preroll[:-len(pcm)][-6400:])
        remaining = 960000 - len(self.pending_question)
        self.pending_question.extend(pcm[:remaining])
        if voiced:
            self.pending_voiced += duration
            self.pending_silence = 0.
        else:
            self.pending_silence += duration
        if len(self.pending_question) >= 960000 or (self.pending_voiced >= .5 and self.pending_silence + 1e-6 >= self.pause):
            self.pending_finished = True

    async def state(self, phase):
        number = self.number
        if phase == 'waiting':
            await self.clear_probe()
            if self.closed or number != self.number:
                return
            self.buffer.clear()
            self.reset_pending()
            self.deadline = self.question_deadline = None
        self.phase = phase
        await self.emit({'type': 'state', 'phase': phase, 'turn': self.number})

    async def cancel_job(self):
        if self.job is not None:
            self.job.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await self.job
            self.job = None

    async def wake(self):
        self.number += 1
        number = self.number
        await self.clear_probe(resume=False)
        if self.closed or number != self.number:
            return
        self.minimum_voiced = .5
        # Notify the browser before waiting for Whisper to exit: playback and
        # model generation should stop as soon as the wake phrase is detected.
        await self.emit({'type': 'wake', 'turn': self.number})
        await self.cancel_job()
        if self.closed or number != self.number:
            return
        self.buffer = bytearray(self.preroll)
        self.reset_pending()
        # The detector may finish after a short combined wake/question. Count
        # real voiced samples already retained, rather than requiring new speech.
        self.voiced = self.preroll_voice.count(1) / 32000
        self.silence = 0.
        self.deadline = self.clock() + 10
        self.question_deadline = self.deadline
        await self.state('listening')

    async def audio(self, pcm, voiced, wake=False):
        if self.closed:
            return
        self.preroll.extend(pcm)
        self.preroll_voice.extend(bytes([int(voiced)]) * len(pcm))
        if len(self.preroll) > 64000:
            del self.preroll[:-64000]
            del self.preroll_voice[:-64000]
        now, duration = self.clock(), len(pcm) / 32000
        if wake and now - self.last_wake >= 1.5:
            self.last_wake = now
            await self.wake()
            return
        if self.phase in ('generating', 'speaking'):
            await self.consider_interruption(voiced, duration, now)
            return
        if self.phase == 'followup' and voiced:
            self.number += 1
            self.minimum_voiced = .5
            self.buffer = bytearray(self.preroll[:-len(pcm)])
            self.voiced = self.silence = 0.
            self.deadline = now + 10
            await self.state('listening')
        if self.phase == 'transcribing':
            self.pending_audio(pcm, voiced, now, duration)
            return
        if self.phase != 'listening':
            return
        self.buffer.extend(pcm)
        if voiced:
            self.voiced += duration
            self.silence = 0.
        else:
            self.silence += duration
        if len(self.buffer) >= 960000:
            if self.voiced >= self.minimum_voiced:
                await self.finish_capture()
            else:
                self.buffer.clear()
                await self.state('waiting')
        elif self.voiced + 1e-6 >= self.minimum_voiced and self.silence + 1e-6 >= self.pause:
            await self.finish_capture()

    async def finish_capture(self):
        if self.closed:
            return
        number, clip = self.number, pcm_wav(bytes(self.buffer[:960000]))
        self.buffer.clear()
        self.preroll.clear()
        self.preroll_voice.clear()
        self.reset_pending()
        self.interrupt_voiced = 0.
        self.deadline = None
        await self.state('transcribing')
        # Socket sends yield to disconnects and newer wake turns. Never create
        # a new engine task after those owners have already cleaned up.
        if self.closed or number != self.number:
            return

        async def decode():
            try:
                result = await self.transcribe(clip)
                if self.closed or number != self.number:
                    return
                text = remove_wake_phrase(clean_transcript(result['text']))
                if not text:
                    if result['text'].strip() and self.question_deadline is not None and (self.pending_started is not None or self.clock() < self.question_deadline):
                        # A wake phrase can be a separate utterance. Keep its
                        # original window and retain audio received during STT.
                        self.buffer = self.pending_question
                        self.voiced, self.silence = self.pending_voiced, self.pending_silence
                        finished = self.pending_finished
                        self.deadline = self.question_deadline if self.pending_started is None else None
                        self.reset_pending()
                        await self.state('listening')
                        if finished and self.voiced >= .5:
                            await self.finish_capture()
                    else:
                        await self.state('waiting')
                    return
                if len(text.encode('utf-16-le')) // 2 > 2000:
                    raise JuneError('too-long', 'That question is too long. Try a shorter question.', 400)
                self.question_deadline = None
                self.reset_pending()
                await self.state('generating')
                if not self.closed and number == self.number:
                    await self.emit({'type': 'transcript', 'turn': number, 'text': text,
                                     'durationMs': result['durationMs']})
            except JuneError as error:
                if not self.closed and number == self.number:
                    await self.emit({'type': 'error', 'turn': number, 'message': error.message, 'fatal': False})
                    await self.state('waiting')
            except (ValueError, KeyError, TypeError, UnicodeError):
                if not self.closed and number == self.number:
                    await self.emit({'type': 'error', 'turn': number, 'message': 'The local transcript was invalid. Please try again.', 'fatal': False})
                    await self.state('waiting')
        self.job = asyncio.create_task(decode())

    async def activity(self, number, phase, spoken=''):
        if self.closed or number != self.number:
            return
        if phase == 'cancel':
            self.number += 1
            number = self.number
            await self.cancel_job()
            if self.closed or number != self.number:
                return
            self.buffer.clear()
            self.deadline = None
            await self.state('waiting')
        elif self.phase in ('generating', 'speaking'):
            if phase == 'speaking' and spoken:
                self.spoken = spoken[:4000]
            if phase in ('generating', 'speaking'):
                # A streamed sentence may end during a pause probe. Generation
                # feedback must not release the held queue before validation.
                if self.probe:
                    return
                await self.state(phase)
            elif phase == 'complete':
                await self.clear_probe()
                if self.closed or number != self.number:
                    return
                self.preroll.clear()
                self.preroll_voice.clear()
                self.deadline = self.clock() + 30
                await self.state('followup')
            elif phase == 'failed':
                self.deadline = None
                await self.state('waiting')

    async def tick(self):
        if self.probe and self.probe['paused'] is None and self.clock() - self.probe['started'] >= 2:
            number = self.number
            await self.clear_probe()
            if not self.closed and number == self.number:
                await self.emit({'type': 'error', 'turn': number, 'fatal': True,
                                 'message': 'Playback could not pause for your interruption. Enable hands-free again or press Stop.'})
        if self.deadline is not None and self.clock() >= self.deadline:
            if self.phase == 'followup' or (self.phase == 'listening' and self.voiced < self.minimum_voiced):
                self.buffer.clear()
                self.deadline = None
                await self.state('waiting')

    async def flush(self):
        if self.probe_job is not None:
            with suppress(asyncio.CancelledError):
                await self.probe_job
        while self.job is not None:
            job = self.job
            await job
            if self.job is job:
                return

    async def close(self):
        self.closed = True
        self.number += 1
        await self.clear_probe(resume=False)
        await self.cancel_job()
        self.buffer.clear()
        self.preroll.clear()
        self.preroll_voice.clear()
        self.reset_pending()
