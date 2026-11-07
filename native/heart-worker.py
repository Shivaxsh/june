"""Persistent CPU synthesis. Only bounded JSON/PCM goes over private pipes."""
import base64
import json
from pathlib import Path
import sys

import numpy as np
import onnxruntime as ort
from kokoro_onnx import Kokoro

home = Path(sys.argv[1])
options = ort.SessionOptions()
options.intra_op_num_threads = 2
options.inter_op_num_threads = 1
session = ort.InferenceSession(str(home / 'kokoro-v1.0.onnx'), sess_options=options,
                              providers=['CPUExecutionProvider'])
engine = Kokoro.from_session(session, str(home / 'voices-v1.0.bin'))
print(json.dumps({'type': 'ready', 'voice': 'af_heart', 'sampleRate': 24000}), flush=True)
while True:
    line = sys.stdin.buffer.readline(16001)
    if not line:
        break
    if len(line) > 16000:
        break
    value = json.loads(line)
    identity = value['id']
    try:
        text, speed = value['text'], value['speed']
        if not isinstance(text, str) or not 1 <= len(text) <= 2000 or speed not in (.96, .90, 1.02):
            raise ValueError('Invalid synthesis input')
        samples, rate = engine.create(text, voice='af_heart', speed=speed, lang='en-us')
        if rate != 24000 or not np.isfinite(samples).all() or len(samples) > 24000 * 180:
            raise ValueError('Invalid synthesis output')
        audio = (np.clip(samples, -1, 1) * 32767).astype('<i2').tobytes()
        for offset in range(0, len(audio), 8192):
            print(json.dumps({'id': identity, 'audio': base64.b64encode(audio[offset:offset+8192]).decode('ascii')}), flush=True)
        print(json.dumps({'id': identity, 'type': 'done'}), flush=True)
    except Exception:
        print(json.dumps({'id': identity, 'type': 'error'}), flush=True)
