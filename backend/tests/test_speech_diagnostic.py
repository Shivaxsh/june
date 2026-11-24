import os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from june.speech_diagnostic import OneShotSpeechDiagnostic


class OneShotDiagnosticTests(unittest.TestCase):
    def test_default_off_expired_and_long_lived_flags_never_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'private'/'clip.wav'
            for until in ('', 'bad', 'nan', '99','1000'):
                with patch.dict(os.environ,{'JUNE_SPEECH_AUDIT_FILE':str(target),'JUNE_SPEECH_AUDIT_UNTIL':until}):
                    OneShotSpeechDiagnostic(clock=lambda:100).capture(b'x'*100)
                self.assertFalse(target.exists())

    def test_one_clip_only_private_permissions_no_overwrite_and_expiry(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'private'/'clip.wav'
            with patch.dict(os.environ,{'JUNE_SPEECH_AUDIT_FILE':str(target),'JUNE_SPEECH_AUDIT_UNTIL':'150'}):
                audit=OneShotSpeechDiagnostic(clock=lambda:100)
                audit.capture(b'a'*100);audit.capture(b'b'*100)
                self.assertEqual(target.read_bytes(),b'a'*100)
                self.assertEqual(target.stat().st_mode&0o777,0o600)
                self.assertEqual(target.parent.stat().st_mode&0o777,0o700)
                OneShotSpeechDiagnostic(clock=lambda:100).capture(b'c'*100)
                self.assertEqual(target.read_bytes(),b'a'*100)
                target.unlink()
                late=OneShotSpeechDiagnostic(clock=lambda:200);late.capture(b'd'*100)
                self.assertFalse(target.exists())

    def test_one_bounded_skip_records_only_the_followup(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'private'/'clip.wav'
            with patch.dict(os.environ,{'JUNE_SPEECH_AUDIT_FILE':str(target),'JUNE_SPEECH_AUDIT_UNTIL':'150','JUNE_SPEECH_AUDIT_SKIP':'1'}):
                audit=OneShotSpeechDiagnostic(clock=lambda:100)
                audit.capture(b'a'*100);self.assertFalse(target.exists())
                audit.capture(b'b'*100);audit.capture(b'c'*100)
                self.assertEqual(target.read_bytes(),b'b'*100)

    def test_an_authorised_multi_clip_audit_saves_exactly_n_numbered_private_clips_then_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'private'/'capture.wav'
            with patch.dict(os.environ,{'JUNE_SPEECH_AUDIT_FILE':str(target),'JUNE_SPEECH_AUDIT_UNTIL':'390','JUNE_SPEECH_AUDIT_COUNT':'6'}):
                audit=OneShotSpeechDiagnostic(clock=lambda:100)
                for n in range(8): audit.capture(bytes([65+n])*100)
            saved=sorted(target.parent.glob('capture-*.wav'))
            self.assertEqual([p.name for p in saved],[f'capture-{n}.wav' for n in range(1,7)])
            self.assertEqual(saved[5].read_bytes(),b'F'*100)
            self.assertTrue(all(p.stat().st_mode&0o777==0o600 for p in saved))
            self.assertFalse(target.exists())

    def test_multi_clip_limits_count_to_six_and_life_to_five_minutes(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'private'/'capture.wav'
            with patch.dict(os.environ,{'JUNE_SPEECH_AUDIT_FILE':str(target),'JUNE_SPEECH_AUDIT_UNTIL':'401','JUNE_SPEECH_AUDIT_COUNT':'6'}):
                OneShotSpeechDiagnostic(clock=lambda:100).capture(b'x'*100)
            self.assertEqual(list(target.parent.glob('*')) if target.parent.exists() else [],[])
            with patch.dict(os.environ,{'JUNE_SPEECH_AUDIT_FILE':str(target),'JUNE_SPEECH_AUDIT_UNTIL':'200','JUNE_SPEECH_AUDIT_COUNT':'99'}):
                audit=OneShotSpeechDiagnostic(clock=lambda:100)
                for n in range(9): audit.capture(b'y'*100)
            self.assertEqual(len(list(target.parent.glob('capture-*.wav'))),6)

    def test_frame_audit_is_off_by_default_numbers_only_private_and_bounded(self):
        import json
        from june.speech_diagnostic import FrameAudit
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'private'/'frames.jsonl'
            with patch.dict(os.environ,{},clear=False):
                os.environ.pop('JUNE_SPEECH_AUDIT_FRAMES',None)
                self.assertIsNone(FrameAudit(clock=lambda:100).out)
            with patch.dict(os.environ,{'JUNE_SPEECH_AUDIT_FRAMES':str(target),'JUNE_SPEECH_AUDIT_UNTIL':'1000'}):
                self.assertIsNone(FrameAudit(clock=lambda:100).out,'longer than five minutes never arms')
            with patch.dict(os.environ,{'JUNE_SPEECH_AUDIT_FRAMES':str(target),'JUNE_SPEECH_AUDIT_UNTIL':'300'}):
                audit=FrameAudit(clock=lambda:100)
                audit.frame('speaking',.91,.0123,.001,True); audit.out.flush()
                row=json.loads(target.read_text().splitlines()[0])
                self.assertEqual(set(row),{'t','phase','p','rms','floor','v'})
                self.assertEqual(target.stat().st_mode&0o777,0o600)
                audit.lines=audit.MAX_LINES; audit.frame('speaking',.5,.01,.001,False); audit.out.flush()
                self.assertEqual(len(target.read_text().splitlines()),1)
