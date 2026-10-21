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


def playback_tokens(text):
    # Comparison only: keep source offsets so prefix removal never rewrites
    # the remaining transcript. Native ASR can spell "5070 Ti" as "5,070t".
    tokens = []
    for match in re.finditer(r'[0-9]{1,3}(?:,[0-9]{3})+(?:ti|t|super|xtx|xt)?\b|[a-z0-9]+', text, re.I):
        word = match.group().lower()
        number = re.fullmatch(r'([0-9,]+)(ti|t|super|xtx|xt)?', word)
        if number:
            digits = number[1].replace(',', '')
            tokens.append((digits, match.start()))
            if number[2]:
                suffix = 'ti' if number[2] == 't' and len(digits) == 4 else number[2]
                tokens.append((suffix, match.start() + number.start(2)))
        else:
            tokens.append((word, match.start()))
    return tokens


def playback_identity(words, index):
    suffix = words[index + 1] if index + 1 < len(words) and words[index + 1] in {'ti', 'super', 'xt', 'xtx'} else ''
    if suffix == 'ti' and words[index + 2:index + 3] == ['super']:
        suffix = 'ti super'
    return words[index], suffix


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
        self.playback = []
        self.audio_time = 0.
        self.echo_check = False

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
            if not self.closed and self.number == number:
                # Completion may arrive while the voice is held. Do not lose
                # it, or leave a completed reply labelled as still speaking.
                await self.activity(number, probe['activity'])

    async def probe_paused(self, number, probe):
        if number == self.number and self.probe and self.probe['id'] == probe and self.probe['paused'] is None:
            self.probe['paused'] = self.audio_time

    async def probe_cancelled(self, number, probe):
        if number == self.number and self.probe and self.probe['id'] == probe:
            await self.clear_probe()

    async def interrupt(self):
        # The owned candidate retains the user's first word during decoding.
        # The browser invalidates its request on confirmed interruption.
        probe = self.probe
        seconds = self.interrupt_voiced
        # Quantise to whole PCM16 samples; wall-clock jitter can produce an odd
        # byte count, which would shift every sample and invalidate the WAV.
        size = min(len(self.preroll), int((seconds + .2) * 16000) * 2)
        clip = bytes(probe['audio']) if probe else bytes(self.preroll[-size:])
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
        self.voiced, self.silence = .24, probe['silence'] if probe else 0.
        self.echo_check = True
        self.deadline = self.clock() + 10
        self.question_deadline = None
        await self.state('listening')

    def is_playback_echo(self, text, reference):
        words = [word for word, _ in playback_tokens(clean_transcript(text))]
        spoken = [word for word, _ in playback_tokens(clean_transcript(reference))]
        if words and spoken:
            if any((word.isdigit() or word in {'ti', 'super', 'xt', 'xtx'}) and word not in spoken for word in words):
                return False
            # A base model is also a correction to a suffixed model. Do not
            # let fuzzy matching discard that distinction in either direction.
            identities = {playback_identity(spoken, i)
                          for i, word in enumerate(spoken) if word.isdigit()}
            for i, word in enumerate(words):
                if word.isdigit():
                    if playback_identity(words, i) not in identities:
                        return False
            # Common words alone are not echo. Preserve a newly phrased
            # question/correction about the subject June just discussed.
            openings = {'how', 'what', 'why', 'where', 'when', 'which', 'can', 'could', 'does', 'do', 'did', 'is', 'are', 'wait', 'stop', 'actually', 'no'}
            prefix = words[:2]
            if words[0] in openings and not any(spoken[i:i + len(prefix)] == prefix for i in range(len(spoken))):
                return False
            matcher = SequenceMatcher(None, words, spoken, autojunk=False)
            if matcher.find_longest_match().size / len(words) >= .85:
                return True
            # Clipped native speech can become "Eating the page" for
            # "updating the page". Compare local phrases, not global overlap.
            if 3 <= len(words) <= 16:
                phrase = ' '.join(words)
                for size in (len(words) - 1, len(words), len(words) + 1):
                    for start in range(len(spoken) - size + 1):
                        window = spoken[start:start + size]
                        shared = SequenceMatcher(None, words, window, autojunk=False).find_longest_match().size
                        if shared / len(words) >= .5 and SequenceMatcher(None, phrase, ' '.join(window), autojunk=False).ratio() >= .8:
                            return True
        return False

    def without_playback_prefix(self, text, reference):
        # Overlapping native output can precede a real question in the mic
        # recording. Trim only a substantial, matching leading playback span;
        # preserve the original spelling/case of the user's remaining words.
        tokens = playback_tokens(text)
        words = [word for word, _ in tokens]
        spoken = [word for word, _ in playback_tokens(clean_transcript(reference))]
        for block in SequenceMatcher(None, words, spoken, autojunk=False).get_matching_blocks():
            if block.a == 0 and 4 <= block.size < len(words):
                size = block.size
                start = size - 1
                while start > 0 and words[start] in {'ti', 'super', 'xt', 'xtx'}:
                    start -= 1
                if words[start].isdigit():
                    if playback_identity(words, start) != playback_identity(spoken, block.b + start):
                        # Retain the whole corrected identifier, including a
                        # number that happened to match the playback prefix.
                        size = start
                if size >= 4:
                    return text[tokens[size][1]:].strip()
        return text

    async def check_short_probe(self):
        probe, number = self.probe, self.number
        if not probe or probe.get('checking'):
            return
        probe['checking'] = True
        probe['checks'] = probe.get('checks', 0) + 1
        clip = pcm_wav(bytes(probe['audio']))
        probe['tail_voiced'] = 0.

        async def verify():
            try:
                # This path preserves a brief "wait" that ended before the
                # echo-settling window. It does not require sustained speech.
                result = await asyncio.wait_for(self.transcribe(clip), 8)
                if self.closed or number != self.number or self.probe is not probe:
                    return
                raw = clean_transcript(result['text'])
                text = self.without_playback_prefix(remove_wake_phrase(raw), probe['spoken'])
                wake_only = bool(raw and not text and not self.is_playback_echo(raw, probe['spoken']))
                if wake_only:
                    await self.interrupt()
                    if not self.closed and self.number == number + 1 and probe['tail_voiced'] < .08:
                        self.buffer.clear(); self.preroll.clear(); self.preroll_voice.clear()
                        self.minimum_voiced = .5
                        self.voiced = self.silence = 0.
                        self.echo_check = False
                    return
                # Before the first spoken sentence there is no echo reference.
                # A real multiword question can still interrupt generation.
                no_playback_question = not probe['spoken'] and len(re.findall(r'[a-z0-9]+', text.lower())) >= 2
                controls = {'wait', 'stop', 'pause', 'hold', 'no', 'actually', 'sorry', 'okay', 'ok', 'why', 'how', 'what'}
                words = re.findall(r'[a-z0-9]+', text.lower())
                explicit = bool(controls.intersection(words)) or any(word.isdigit() for word in words)
                acoustic_evidence = probe['clean_voiced'] + 1e-6 >= .18 or explicit or no_playback_question
                if acoustic_evidence and words and not self.is_playback_echo(text, probe['spoken']):
                    if probe['tail_voiced'] >= .08 or probe['silence'] < .3:
                        # Speech continued while Whisper checked the prefix.
                        # Keep the entire bounded capture, including its start,
                        # and finish transcribing at the normal silence boundary.
                        await self.interrupt()
                        return
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
                if probe['tail_voiced'] >= .08 and probe['checks'] < 3 and len(probe['audio']) < 960000:
                    # The first clip was noise/echo, but a person started talking
                    # during its decoder job. Check the retained question before
                    # releasing the hold. Bound repeated decoding under noise.
                    probe['checking'] = False
                    await self.check_short_probe()
                    return
                await self.clear_probe()
                self.probe_cooldown = self.audio_time + (0. if probe['tail_voiced'] >= .08 else 1.)
        async def owned():
            try:
                await verify()
            finally:
                if self.probe_job is asyncio.current_task():
                    self.probe_job = None
        self.probe_job = asyncio.create_task(owned())

    async def consider_interruption(self, voiced, duration, now):
        if self.probe:
            probe = self.probe
            paused = probe['paused']
            # Count actual audio, not CPU/wall-clock delay. VAD alone cannot
            # confirm a turn: fans and speaker tails can stay classified voiced.
            probe['silence'] = 0. if voiced else probe['silence'] + duration
            if paused is not None and self.audio_time - paused >= .25 and voiced:
                probe['clean_voiced'] += duration
            if probe.get('checking') and voiced:
                probe['tail_voiced'] += duration
            if paused is not None and self.audio_time - paused + 1e-6 >= .8:
                if not probe.get('checking'):
                    await self.check_short_probe()
            return
        self.interrupt_voiced = self.interrupt_voiced + duration if voiced else 0.
        threshold = .12 if self.phase == 'speaking' else .24
        if self.audio_time >= self.probe_cooldown and self.interrupt_voiced + 1e-6 >= threshold:
            self.probe_number += 1
            size = int((self.interrupt_voiced + .2) * 16000) * 2
            # Verify the words while playback continues. Pausing on VAD alone
            # made speaker echo repeatedly break speech into tiny fragments.
            self.probe = {'id': self.probe_number, 'started': now, 'paused': self.audio_time,
                          'spoken': ' '.join(self.playback) or self.spoken,
                          'audio': bytearray(self.preroll[-size:]), 'silence': 0.,
                          'clean_voiced': 0.,
                          'activity': self.phase}

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
        self.echo_check = False
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
        self.audio_time += duration
        if self.probe:
            self.probe['audio'].extend(pcm[:max(0, 960000 - len(self.probe['audio']))])
        # Restricted wake recognition can mistake speaker echo for the wake
        # phrase too. During replies it must use the same confirmation path.
        if wake and self.phase not in ('generating', 'speaking') and now - self.last_wake >= 1.5:
            self.last_wake = now
            await self.wake()
            return
        if self.phase in ('generating', 'speaking') or self.probe:
            await self.consider_interruption(voiced, duration, now)
            return
        if self.phase == 'followup' and voiced:
            self.number += 1
            self.minimum_voiced = .5
            self.echo_check = True
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
                if self.echo_check:
                    text = self.without_playback_prefix(text, ' '.join(self.playback))
                if self.echo_check and self.playback and text and self.is_playback_echo(text, ' '.join(self.playback)):
                    self.echo_check = False
                    self.deadline = self.clock() + 30
                    await self.state('followup')
                    return
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
                if not self.playback or self.playback[-1] != self.spoken:
                    self.playback.append(self.spoken)
                    while len(self.playback) > 6 or len(' '.join(self.playback)) > 8000:
                        self.playback.pop(0)
            if self.probe and phase in ('generating', 'speaking', 'complete'):
                self.probe['activity'] = phase
                self.probe['spoken'] = ' '.join(self.playback) or self.spoken
                if phase == 'complete':
                    self.deadline = self.clock() + 30
                    await self.state('followup')
                else:
                    await self.state(phase)
                return
            if phase in ('generating', 'speaking'):
                # A streamed sentence may end during a pause probe. Generation
                # feedback must not release the held queue before validation.
                if self.probe:
                    return
                if phase != self.phase:
                    self.interrupt_voiced = 0.
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
        while self.probe_job is not None:
            job = self.probe_job
            with suppress(asyncio.CancelledError):
                await job
            if self.probe_job is job:
                break
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
        self.playback.clear()
