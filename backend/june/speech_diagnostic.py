"""Explicit operator opt-in: save ONE (or, when asked, up to six) normal speech inputs for a short local audit.

Disabled unless both environment variables are set. Never opens the microphone,
never changes transcription, never logs audio/text, never uploads anything. The
operator removes the clip after the authorised comparison.
"""
import json
import math
import os
from pathlib import Path
import time


class OneShotSpeechDiagnostic:
    def __init__(self,clock=time.time):
        self.clock=clock;self.used=False;self.path=None;self.until=0;self.skip=0;self.count=1;self.saved=0
        value=os.environ.get('JUNE_SPEECH_AUDIT_FILE','')
        try:until=float(os.environ.get('JUNE_SPEECH_AUDIT_UNTIL','0'))
        except ValueError:return
        try:self.count=min(6,max(1,int(os.environ.get('JUNE_SPEECH_AUDIT_COUNT','1'))))
        except ValueError:self.count=1
        # No permanently armed flag, even if accidentally inherited by a launcher. A multi-clip audit may last 5 minutes.
        if not value or not math.isfinite(until) or not self.clock()<until<=self.clock()+(180 if self.count==1 else 300):return
        self.path=Path(value).expanduser();self.until=until
        try:self.skip=min(1,max(0,int(os.environ.get('JUNE_SPEECH_AUDIT_SKIP','0'))))
        except ValueError:self.skip=0

    def capture(self,wav):
        if self.used or self.path is None or self.clock()>=self.until:return
        if self.skip:
            self.skip-=1;return
        self.saved+=1;self.used=self.saved>=self.count
        if not isinstance(wav,bytes) or not 44<=len(wav)<=1048576:return
        # One clip keeps the given name; several are numbered capture-1.wav ... capture-N.wav.
        target=self.path if self.count==1 else self.path.with_name(f'{self.path.stem}-{self.saved}{self.path.suffix}')
        try:
            target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            target.parent.chmod(0o700)
            flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0)
            fd=os.open(target,flags,0o600)
            with os.fdopen(fd,'wb') as out:out.write(wav)
            meta=target.with_suffix('.json')
            fd=os.open(meta,flags,0o600)
            with os.fdopen(fd,'w') as out:json.dump({'createdAt':self.clock(),'bytes':len(wav),'durationMs':(len(wav)-44)/32,'retention':'delete after this authorised audit'},out)
        except OSError:
            pass  # Recording diagnostics must never break the live speech path.


class FrameAudit:
    """Explicit operator opt-in: log NUMBERS ONLY for each processed 20 ms frame (speech probability, loudness, noise
    floor, whether it counted as speech, the turn phase) for at most 5 minutes. No audio and no words are written.
    Enabled only by JUNE_SPEECH_AUDIT_FRAMES (a file path) with JUNE_SPEECH_AUDIT_UNTIL <= now + 300 s."""
    MAX_LINES = 15000

    def __init__(self, clock=time.time):
        self.clock = clock; self.out = None; self.until = 0; self.lines = 0; self.started = clock()
        value = os.environ.get('JUNE_SPEECH_AUDIT_FRAMES', '')
        try: until = float(os.environ.get('JUNE_SPEECH_AUDIT_UNTIL', '0'))
        except ValueError: return
        if not value or not math.isfinite(until) or not self.clock() < until <= self.clock() + 300: return
        try:
            path = Path(value).expanduser(); path.parent.mkdir(mode=0o700, parents=True, exist_ok=True); path.parent.chmod(0o700)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
            self.out = os.fdopen(fd, 'w'); self.until = until
        except OSError:
            self.out = None

    @property
    def active(self):
        return self.out is not None and self.clock() < self.until and self.lines < self.MAX_LINES

    def frame(self, phase, probability, rms, floor, voiced):
        if not self.active:
            return
        try:
            self.out.write(json.dumps({'t': round(self.clock() - self.started, 3), 'phase': phase, 'p': round(float(probability), 3),
                                       'rms': round(float(rms), 5), 'floor': round(float(floor), 5), 'v': bool(voiced)}) + '\n')
            self.lines += 1
            if self.lines % 50 == 0: self.out.flush()
        except (OSError, ValueError, TypeError):
            self.out = None  # diagnostics never break listening
