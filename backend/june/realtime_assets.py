"""Readiness is cheap after verifying unchanged local model files."""
import asyncio
import hashlib
from importlib.metadata import version, PackageNotFoundError
import json
import os
from pathlib import Path

MODEL = 'vosk-model-small-en-us-0.15'
SHA256 = '30f26242c4eb449f948e42cb302dd7a686cb29a3423a8367f99ff41780942498'
VERSIONS = {'pipecat-ai': '0.0.85', 'onnxruntime': '1.23.2', 'vosk': '0.3.44', 'numpy': '1.26.4'}


class RealtimeAssets:
    def __init__(self, settings):
        self.root = Path(os.environ.get('JUNE_REALTIME_HOME', str(settings.speech_home.parent / 'realtime')))
        self.model = self.root / MODEL
        self.verified = None

    def check(self):
        try:
            if any(version(name) != expected for name, expected in VERSIONS.items()):
                raise ValueError('versions')
            ready = json.loads((self.root / 'ready.json').read_text())
            files = ready.get('files')
            if ready.get('model') != MODEL or ready.get('sha256') != SHA256 or not isinstance(files, dict) or not 5 <= len(files) <= 100:
                raise ValueError('manifest')
            identity = []
            for relative, digest in files.items():
                file = (self.model / relative).resolve()
                if not file.is_relative_to(self.model.resolve()) or not isinstance(digest, str) or len(digest) != 64:
                    raise ValueError('file')
                info = file.stat()
                identity.append((relative, digest, info.st_size, info.st_mtime_ns))
            identity = tuple(sorted(identity))
            if identity != self.verified:
                for relative, digest, _, _ in identity:
                    with (self.model / relative).open('rb') as source:
                        if hashlib.file_digest(source, 'sha256').hexdigest() != digest:
                            raise ValueError('checksum')
                self.verified = identity
            return {'state': 'ready', 'message': 'Local wake phrase and speech detection are ready.'}
        except (PackageNotFoundError, OSError, ValueError, TypeError, AttributeError):
            return {'state': 'setup-required', 'message': 'Hands-free needs setup. Run npm run realtime:setup, restart June, then refresh hands-free.'}

    async def status(self):
        return await asyncio.to_thread(self.check)
