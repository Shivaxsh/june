import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from june.errors import JuneError


class KeychainBoundary(unittest.IsolatedAsyncioTestCase):
    async def test_secrets_travel_over_stdin_not_arguments(self):
        from june.keychain import Keychain
        process = AsyncMock()
        process.returncode = 0
        process.communicate.return_value = (b'{"ok":true}', b'')
        with tempfile.TemporaryDirectory() as home:
            binary = Path(home) / 'JuneSecrets'
            binary.touch()
            with patch('june.keychain.asyncio.create_subprocess_exec', return_value=process) as spawn:
                await Keychain(binary).put('google.calendar', 'private-test-token')
                self.assertNotIn('private-test-token', str(spawn.call_args))
                sent = json.loads(process.communicate.call_args.args[0])
                self.assertEqual(sent, {'operation':'put','account':'google.calendar','secret':'private-test-token'})

    async def test_no_helper_or_invalid_account_fails_without_spawning(self):
        from june.keychain import Keychain
        with patch('june.keychain.asyncio.create_subprocess_exec') as spawn:
            for account in ('arbitrary', 'google.calendar'):
                with self.assertRaises(JuneError):
                    await Keychain(Path('/nonexistent/JuneSecrets')).get(account)
            spawn.assert_not_called()

    async def test_private_helper_error_is_not_exposed(self):
        from june.keychain import Keychain
        process = AsyncMock()
        process.returncode = 1
        process.communicate.return_value = (b'private-token', b'private-error')
        with tempfile.TemporaryDirectory() as home:
            binary = Path(home) / 'JuneSecrets'
            binary.touch()
            with patch('june.keychain.asyncio.create_subprocess_exec', return_value=process):
                with self.assertRaises(JuneError) as caught:
                    await Keychain(binary).get('google.calendar')
                self.assertNotIn('private', caught.exception.message)
