import unittest
from june.signal_gate import ProcessedSignalGate

class ProcessedGateTests(unittest.TestCase):
    def test_delayed_wake_result_after_speech_can_arrive_during_silence(self):
        gate=ProcessedSignalGate()
        for _ in range(20):gate.accept(640,.95,.08,.001,False)
        for _ in range(20):gate.accept(640,.05,.0001,.001,False)
        voiced,wake=gate.accept(640,.03,.0001,.001,True)
        self.assertFalse(voiced);self.assertTrue(wake)

    def test_noise_and_old_speech_do_not_authorize_a_wake(self):
        gate=ProcessedSignalGate()
        for _ in range(50):gate.accept(640,.2,.15,.08,False)
        self.assertEqual(gate.accept(640,.2,.15,.08,True),(False,False))
        for _ in range(10):gate.accept(640,.95,.08,.001,False)
        for _ in range(80):gate.accept(640,.03,.0001,.001,False)
        self.assertEqual(gate.accept(640,.03,.0001,.001,True),(False,False))
