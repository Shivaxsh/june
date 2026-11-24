"""Resident NVIDIA Parakeet (TDT 0.6B v2, int8 ONNX via sherpa-onnx) speech worker, CPU-only and local.

Speaks the same Protocol 1 as the Whisper worker (see whisper_worker.py), so June's existing supervisor owns its
lifetime, timeouts, cancellation and restarts:
  stdin : one JSON line <=4096 bytes; {"type":"transcribe","id":...,"bytes":N} is followed by N bytes of 16 kHz mono
          16-bit WAV; {"type":"cancel","id":...} cancels nothing that already finished.
  stdout: {"type":"ready","protocol":1,"model":<id>} once, then one JSON line per job:
          {"type":"result","id","text","confidence","noSpeechProbability"} | {"type":"error","id","code"} |
          {"type":"cancel-ignored","id"}.
Never logs audio or text. Run: python parakeet_worker.py --model <model directory>
"""
import json
import math
import struct
import sys

MODEL_ID = 'parakeet-tdt-0.6b-v2-int8'
MAX_LINE, MAX_AUDIO = 4096, 1048576


def emit(message):
    sys.stdout.write(json.dumps(message) + '\n'); sys.stdout.flush()


def samples(wav):
    import numpy as np
    if len(wav) < 44 or wav[:4] != b'RIFF' or wav[8:12] != b'WAVE' or struct.unpack_from('<HHI', wav, 20)[:3] != (1, 1, 16000):
        raise ValueError('wav')
    return np.frombuffer(wav[44:], dtype='<i2').astype(np.float32) / 32768


def main(argv):
    if len(argv) != 3 or argv[1] != '--model':
        return 2
    try:
        from pathlib import Path
        import numpy as np
        import sherpa_onnx
        folder = Path(argv[2])
        recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
            encoder=str(folder / 'encoder.int8.onnx'), decoder=str(folder / 'decoder.int8.onnx'),
            joiner=str(folder / 'joiner.int8.onnx'), tokens=str(folder / 'tokens.txt'),
            num_threads=4, model_type='nemo_transducer', decoding_method='greedy_search')
    except Exception:
        emit({'type': 'error', 'id': '', 'code': 'model-load-failed'})
        return 2
    emit({'type': 'ready', 'protocol': 1, 'model': MODEL_ID})
    stdin = sys.stdin.buffer
    while True:
        line = stdin.readline(MAX_LINE + 1)
        if not line:
            return 0
        if len(line) > MAX_LINE or not line.endswith(b'\n'):
            return 3
        try:
            command = json.loads(line)
            kind, job = command.get('type'), command.get('id')
        except (ValueError, AttributeError):
            return 3
        if kind == 'cancel':
            emit({'type': 'cancel-ignored', 'id': job}); continue  # jobs run to completion before the next command
        if kind != 'transcribe' or type(command.get('bytes')) is not int or not 44 <= command['bytes'] <= MAX_AUDIO:
            return 3
        wav = stdin.read(command['bytes'])
        if len(wav) != command['bytes']:
            return 3
        try:
            stream = recognizer.create_stream(); stream.accept_waveform(16000, samples(wav)); recognizer.decode_stream(stream)
            result = stream.result
            text = result.text.strip()
            logs = list(getattr(result, 'ys_log_probs', []) or [])
            confidence = float(math.exp(sum(logs) / len(logs))) if logs else (1.0 if text else 0.0)
            emit({'type': 'result', 'id': job, 'text': text[:16000], 'confidence': max(0., min(1., confidence)),
                  'noSpeechProbability': 0.0 if text else 1.0})
        except Exception:
            emit({'type': 'error', 'id': job, 'code': 'engine-failed'})


if __name__ == '__main__':
    sys.exit(main(sys.argv))
