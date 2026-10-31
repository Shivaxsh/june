"""Optional heavy imports: ordinary chat still starts without hands-free setup."""
import asyncio
from dataclasses import dataclass
import json
import time
from functools import lru_cache
from .signal_gate import ProcessedSignalGate

from loguru import logger
logger.disable('pipecat')
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import DataFrame, StartFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask, PipelineParams
from pipecat.processors.frame_processor import FrameProcessor
from vosk import Model, KaldiRecognizer, SetLogLevel

SetLogLevel(-1)


@lru_cache(maxsize=1)
def wake_model(path):
    return Model(str(path))

class Detectors:
    def __init__(self, model):
        self.model = wake_model(str(model))
        self.wake = KaldiRecognizer(self.model, 16000, '["hey june", "[unk]"]')
        self.wake.SetWords(True)
        self.wake.SetPartialWords(True)
        self.vad = SileroVADAnalyzer(sample_rate=16000)
        self.vad.set_sample_rate(16000)
        self.pending = bytearray()
        self.confidence = 0.
        self.last_detection = float('-inf')

    def analyse(self, pcm):
        self.pending.extend(pcm)
        while len(self.pending) >= 1024:
            frame = bytes(self.pending[:1024])
            del self.pending[:1024]
            self.confidence = float(self.vad.voice_confidence(frame).item())
        final = self.wake.AcceptWaveform(pcm)
        result = json.loads(self.wake.Result() if final else self.wake.PartialResult())
        words = result.get('text', result.get('partial', '')).split()
        detected = any(words[i:i + 2] == ['hey', 'june'] for i in range(max(0, len(words) - 1)))
        if detected and time.monotonic() - self.last_detection >= 1.5:
            self.last_detection = time.monotonic()
            self.wake.Reset()
        else:
            detected = False
        return self.confidence >= .65, detected, self.confidence


@dataclass
class PCMFrame(DataFrame):
    audio: bytes
    processed: bool = False
    rms: float = 0.
    noise_floor: float = .001


@dataclass
class DetectionFrame(DataFrame):
    audio: bytes
    voiced: bool
    wake: bool
    probability: float


class DetectionProcessor(FrameProcessor):
    def __init__(self, detectors, fail):
        super().__init__()
        self.detectors, self.fail = detectors, fail
        self.processed_gate = ProcessedSignalGate()

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if isinstance(frame, PCMFrame):
            try:
                voiced, wake, probability = await asyncio.to_thread(self.detectors.analyse, frame.audio)
                if frame.processed:
                    voiced,wake = self.processed_gate.accept(len(frame.audio),probability,frame.rms,frame.noise_floor,wake)
                await self.push_frame(DetectionFrame(frame.audio, voiced, wake, probability), direction)
            except Exception:
                await self.fail('Local speech detection failed. Disable hands-free and run its setup again.')
        else:
            await self.push_frame(frame, direction)


class TurnProcessor(FrameProcessor):
    def __init__(self, turn, consumed, fail, ready, metrics):
        super().__init__()
        self.turn, self.consumed, self.fail = turn, consumed, fail
        self.ready, self.metrics = ready, metrics
        self.last_meter = 0.

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if isinstance(frame, StartFrame):
            self.ready.set()
        if isinstance(frame, DetectionFrame):
            try:
                await self.turn.audio(frame.audio, frame.voiced, frame.wake)
                if time.monotonic() - self.last_meter >= .5:
                    self.last_meter = time.monotonic()
                    await self.metrics(frame.probability)
            except Exception:
                await self.fail('The voice turn could not continue. Enable hands-free again.')
            finally:
                self.consumed(len(frame.audio))
        else:
            await self.push_frame(frame, direction)


def make_pipeline(detectors, turn, consumed, fail, ready, metrics):
    pipeline = Pipeline([DetectionProcessor(detectors, fail), TurnProcessor(turn, consumed, fail, ready, metrics)])
    task = PipelineTask(pipeline, params=PipelineParams(audio_in_sample_rate=16000),
                        idle_timeout_secs=None, enable_turn_tracking=False, cancel_timeout_secs=3)
    runner = PipelineRunner(handle_sigint=False, handle_sigterm=False)
    return task, runner
