"""Repeatable official model install; never extract an unchecked archive."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import urllib.request
import zipfile

MODEL = 'vosk-model-small-en-us-0.15'
SHA256 = '30f26242c4eb449f948e42cb302dd7a686cb29a3423a8367f99ff41780942498'
URL = 'https://alphacephei.com/vosk/models/' + MODEL + '.zip'


def install():
    root = Path(os.environ.get('JUNE_REALTIME_HOME', str(Path.home() / 'Library/Application Support/June/realtime')))
    root.mkdir(parents=True, exist_ok=True)
    archive = root / (MODEL + '.zip')
    if not archive.exists() or hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
        import certifi
        import ssl
        context = ssl.create_default_context(cafile=certifi.where())
        temporary = root / (MODEL + '.download')
        try:
            with urllib.request.urlopen(URL, context=context, timeout=60) as source, temporary.open('wb') as output:
                total = 0
                while chunk := source.read(1024 * 1024):
                    total += len(chunk)
                    if total > 50000000:
                        raise ValueError('Unexpected wake model archive size')
                    output.write(chunk)
            if hashlib.sha256(temporary.read_bytes()).hexdigest() != SHA256:
                raise ValueError('Wake model checksum did not match the pinned release.')
            temporary.replace(archive)
        finally:
            temporary.unlink(missing_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='setup-', dir=root))
    try:
        with zipfile.ZipFile(archive) as bundle:
            if sum(info.file_size for info in bundle.infolist()) > 150000000:
                raise ValueError('Unexpected expanded wake model size')
            for entry in bundle.infolist():
                target = (staging / entry.filename).resolve()
                if not target.is_relative_to(staging.resolve()) or not entry.filename.startswith(MODEL + '/'):
                    raise ValueError('Unsafe wake model archive path')
            bundle.extractall(staging)
        model = staging / MODEL
        if not (model / 'am/final.mdl').is_file():
            raise ValueError('Wake model is incomplete')
        from vosk import Model, KaldiRecognizer, SetLogLevel
        from pipecat.audio.vad.silero import SileroVADAnalyzer
        SetLogLevel(-1)
        decoder = KaldiRecognizer(Model(str(model)), 16000, '["hey june", "[unk]"]')
        decoder.AcceptWaveform(bytes(3200))
        vad = SileroVADAnalyzer(sample_rate=16000)
        vad.set_sample_rate(16000)
        probability = float(vad.voice_confidence(bytes(1024)).item())
        if not 0 <= probability < .2:
            raise ValueError('CPU voice-activity check failed')
        # Hash all installed files, so readiness can detect partial/corrupt models.
        hashes = {str(file.relative_to(model)): hashlib.sha256(file.read_bytes()).hexdigest()
                  for file in model.rglob('*') if file.is_file()}
        destination = root / MODEL
        previous = root / (MODEL + '.previous')
        if previous.exists():
            shutil.rmtree(previous)
        if destination.exists():
            destination.rename(previous)
        try:
            model.rename(destination)
            manifest = root / 'ready.json'
            manifest.write_text(json.dumps({'model': MODEL, 'sha256': SHA256, 'files': hashes}, indent=2) + '\n')
        except BaseException:
            if previous.exists() and not destination.exists():
                previous.rename(destination)
            raise
        if previous.exists():
            shutil.rmtree(previous)
        print('Wake phrase and CPU VAD setup passed. Restart June, then enable hands-free.')
    finally:
        shutil.rmtree(staging)


if __name__ == '__main__':
    try:
        install()
    except Exception as error:
        print('Hands-free setup failed: ' + str(error), file=sys.stderr)
        sys.exit(1)
