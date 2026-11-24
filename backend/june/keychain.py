"""Secrets go directly through a private pipe to the macOS Keychain helper."""
import asyncio
from contextlib import suppress
import json
from pathlib import Path
from .errors import JuneError

ACCOUNTS = frozenset(('google.client', 'google.calendar', 'google.gmail', 'github.pages'))


class Keychain:
    def __init__(self, binary):
        self.binary = Path(binary)

    async def _request(self, operation, account, secret=None):
        if account not in ACCOUNTS or not self.binary.is_file():
            raise JuneError('keychain-unavailable', 'June’s credential helper is not ready.', 503)
        if secret is not None and (not isinstance(secret, str) or not 1 <= len(secret.encode()) <= 16384):
            raise JuneError('invalid-credential', 'The service credential could not be stored.', 400)
        request = dict(operation=operation, account=account)
        if secret is not None:
            request['secret'] = secret
        process = None
        try:
            process = await asyncio.create_subprocess_exec(str(self.binary), stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            output, _ = await asyncio.wait_for(process.communicate(json.dumps(request).encode()), 15)
            if process.returncode or len(output) > 65536:
                raise ValueError()
            reply = json.loads(output)
            if not isinstance(reply, dict) or reply.get('ok') is not True:
                raise ValueError()
            return reply
        except (OSError, TimeoutError, ValueError, UnicodeError):
            raise JuneError('keychain-unavailable', 'macOS could not complete the credential request. No credential was written to a file.', 503) from None
        finally:
            if process is not None and process.returncode is None:
                process.kill()
                with suppress(ProcessLookupError):
                    await process.wait()

    async def put(self, account, secret):
        await self._request('put', account, secret)

    async def get(self, account):
        reply = await self._request('get', account)
        value = reply.get('secret')
        if value is not None and not isinstance(value, str):
            raise JuneError('keychain-unavailable', 'macOS returned an invalid credential response.', 503)
        return value

    async def delete(self, account):
        await self._request('delete', account)
