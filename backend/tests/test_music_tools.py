import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock
from june.errors import JuneError


class MusicTools(unittest.IsolatedAsyncioTestCase):
    async def test_verify_playlist_identity_and_playback_not_just_launch(self):
        from june.music_tools import MusicNative
        music = MusicNative(Path('/not-used'))
        music._call = AsyncMock(return_value={'ok':True,'state':'playing','playlistId':'ABCDEF0123456789','track':'A track'})
        result = await music.play({'playlistId':'ABCDEF0123456789','playlistName':'Focus'})
        self.assertTrue(result['verified'])
        music._call.return_value['playlistId'] = '0000000000000000'
        self.assertFalse((await music.play({'playlistId':'ABCDEF0123456789','playlistName':'Focus'}))['verified'])
        music._call.return_value['state'] = 'paused'
        self.assertFalse((await music.play({'playlistId':'ABCDEF0123456789','playlistName':'Focus'}))['verified'])

    async def test_playlist_ids_cannot_contain_script(self):
        from june.music_tools import MusicNative
        music = MusicNative(Path('/not-used'))
        music._call = AsyncMock()
        with self.assertRaises(JuneError):
            await music.play({'playlistId':'\"; do shell script bad','playlistName':'Focus'})
        music._call.assert_not_called()

    async def test_missing_permission_is_error_not_empty_success(self):
        from june.music_tools import MusicNative
        music = MusicNative(Path('/not-used'))
        music._call = AsyncMock(return_value={'ok':False,'code':'automation-permission'})
        with self.assertRaises(JuneError) as caught:
            await music.playlists()
        self.assertEqual(caught.exception.code, 'automation-permission')


class MusicHelperIdentity(unittest.TestCase):
    """Live failure: Allow reported 'verified' without any prompt, then playlists returned -1743."""
    root = Path(__file__).resolve().parents[2]

    def test_permission_check_sends_a_real_protected_apple_event(self):
        source = (self.root / 'native/JuneMusic.swift').read_text()
        block = source[source.index('operation == "permission"'):source.index('operation == "playlists"')]
        # "get version" is answered without Automation consent, so it proves nothing.
        self.assertNotIn('get version', block)
        self.assertIn('count user playlists', block)

    def test_helper_is_its_own_responsible_signed_app(self):
        source = (self.root / 'native/JuneMusic.swift').read_text()
        self.assertIn('responsibility_spawnattrs_setdisclaim', source)
        self.assertLess(source.index('becomeResponsibleForSelf()\n'), source.index('FileHandle.standardInput.read'))
        script = (self.root / 'scripts/music.mjs').read_text()
        self.assertIn("JuneMusic.app", script)
        self.assertRegex(script, r"codesign',\[[^\]]*'--identifier','local\.june\.music'")
        app = (self.root / 'backend/june/app.py').read_text()
        self.assertIn("'JuneMusic.app'/'Contents'/'MacOS'/'JuneMusic'", app)

    def test_only_the_persons_own_playlists_are_offered(self):
        # Live: the only "playlist" offered was Music's built-in "Music" list, which the user then chose by mistake.
        source = (self.root / 'native/JuneMusic.swift').read_text()
        block = source[source.index('operation == "playlists"'):source.index('operation == "play"')]
        self.assertIn('special kind of p is none', block)
