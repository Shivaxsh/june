"""Audio turn ownership; independent of sockets, models and React."""
import asyncio
from contextlib import suppress
import re
import struct
import time

from .errors import JuneError

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
        if phase == 'waiting':
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
        # Notify the browser before waiting for Whisper to exit: playback and
        # model generation should stop as soon as the wake phrase is detected.
        await self.emit({'type': 'wake', 'turn': self.number})
        await self.cancel_job()
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
        if self.phase == 'followup' and voiced:
            self.number += 1
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
            if self.voiced >= .5:
                await self.finish_capture()
            else:
                self.buffer.clear()
                await self.state('waiting')
        elif self.voiced >= .5 and self.silence + 1e-6 >= self.pause:
            await self.finish_capture()

    async def finish_capture(self):
        number, clip = self.number, pcm_wav(bytes(self.buffer[:960000]))
        self.buffer.clear()
        self.preroll.clear()
        self.preroll_voice.clear()
        self.reset_pending()
        self.deadline = None
        await self.state('transcribing')

        async def decode():
            try:
                result = await self.transcribe(clip)
                if self.closed or number != self.number:
                    return
                text = remove_wake_phrase(result['text'])
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

    async def activity(self, number, phase):
        if self.closed or number != self.number:
            return
        if phase == 'cancel':
            self.number += 1
            await self.cancel_job()
            self.buffer.clear()
            self.deadline = None
            await self.state('waiting')
        elif self.phase in ('generating', 'speaking'):
            if phase in ('generating', 'speaking'):
                await self.state(phase)
            elif phase == 'complete':
                self.preroll.clear()
                self.preroll_voice.clear()
                self.deadline = self.clock() + 30
                await self.state('followup')
            elif phase == 'failed':
                self.deadline = None
                await self.state('waiting')

    async def tick(self):
        if self.deadline is not None and self.clock() >= self.deadline:
            if self.phase == 'followup' or (self.phase == 'listening' and self.voiced < .5):
                self.buffer.clear()
                self.deadline = None
                await self.state('waiting')

    async def flush(self):
        while self.job is not None:
            job = self.job
            await job
            if self.job is job:
                return

    async def close(self):
        self.closed = True
        self.number += 1
        await self.cancel_job()
        self.buffer.clear()
        self.preroll.clear()
        self.preroll_voice.clear()
        self.reset_pending()
