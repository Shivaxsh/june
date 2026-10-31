"""Validate configuration once; never route model traffic to a remote host."""
from dataclasses import dataclass
from pathlib import Path
import os
import json
from urllib.parse import urlsplit

VERSION = json.loads((Path(__file__).resolve().parents[2] / 'package.json').read_text())['version']


def local_url(value: str) -> str:
    url = urlsplit(value)
    if (url.scheme != 'http' or url.hostname not in ('localhost', '127.0.0.1', '::1')
            or url.username or url.password or url.path not in ('', '/') or url.query or url.fragment):
        raise ValueError('June server addresses must use a local HTTP origin.')
    if url.port is not None and not 1 <= url.port <= 65535:
        raise ValueError('Invalid local port.')
    return f'{url.scheme}://{url.netloc}'


@dataclass(frozen=True)
class Settings:
    ollama: str
    model: str
    speech_home: Path
    backend: str

    @classmethod
    def from_env(cls):
        model = os.environ.get('JUNE_MODEL', 'qwen2.5:1.5b')
        if not model.strip() or len(model) > 120:
            raise ValueError('JUNE_MODEL must name an installed local model.')
        return cls(
            local_url(os.environ.get('OLLAMA_BASE_URL', 'http://127.0.0.1:11434')),
            model,
            Path(os.environ.get('JUNE_SPEECH_HOME', str(Path.home() / 'Library/Application Support/June/speech'))).expanduser(),
            local_url(os.environ.get('JUNE_BACKEND_URL', 'http://127.0.0.1:8001')),
        )

    @property
    def audio_home(self):
        return Path(os.environ.get('JUNE_AUDIO_HOME', str(Path.home() / 'Library/Application Support/June/audio'))).expanduser()

    @property
    def data_home(self):
        return Path(os.environ.get('JUNE_DATA_HOME', str(Path.home() / 'Library/Application Support/June/data'))).expanduser()

    @property
    def web_origins(self):
        return {'http://127.0.0.1:3001', 'http://localhost:3001', 'http://[::1]:3001'}
