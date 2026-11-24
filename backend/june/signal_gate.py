"""Recent processed speech can validate a delayed lexical wake result.

Vosk may finalize at a silence boundary. Requiring speech in that exact 20 ms
packet discards a valid wake phrase; retain only recent acoustic evidence.
"""
from collections import deque

# Barge-in evidence while June is speaking (measured 2026-11-23 on this Mac's voice-processed input): the user's words
# reached RMS 0.13-0.44 with VAD only 0.3-0.73 (AEC lowers VAD confidence), while June's own echo stayed at RMS <= 0.049.
# So loudness leads, VAD only has to say "not silence".
BARGE_MIN_RMS, BARGE_FLOOR_RATIO, BARGE_MIN_PROBABILITY = .08, 60, .3


def barge_evidence(probability, rms, noise_floor):
    return probability >= BARGE_MIN_PROBABILITY and rms >= max(BARGE_MIN_RMS, noise_floor * BARGE_FLOOR_RATIO)


class ProcessedSignalGate:
    def __init__(self):
        self.elapsed=0.
        self.recent=deque()

    def accept(self, size, probability, rms, noise_floor, wake):
        duration=size/32000
        self.elapsed+=duration
        voiced=probability>=.8 and rms>=max(.002,noise_floor*2)
        self.recent.append((self.elapsed,duration if voiced else 0.))
        while self.recent and self.recent[0][0]<self.elapsed-1.5:
            self.recent.popleft()
        evidence=sum(value for _,value in self.recent)
        return voiced,bool(wake and evidence+1e-6>=.16)
