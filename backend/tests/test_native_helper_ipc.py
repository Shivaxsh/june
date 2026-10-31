"""Installed helper smoke: small pipe commands and silent preparation, no mic."""
import sys
import asyncio
import json
import unittest
from june.config import Settings
from june.native_audio import NativeAudioService,NICKY

class NativeHelperIPC(unittest.IsolatedAsyncioTestCase):
    async def test_real_multichannel_to_mono_conversion_preserves_signal_without_microphone(self):
        binary=NativeAudioService(Settings.from_env().audio_home).binary
        if sys.platform!='darwin' or not binary.is_file():self.skipTest('Build native helper first')
        p=await asyncio.create_subprocess_exec(str(binary),'--self-test',stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        try:
            stdout,_=await asyncio.wait_for(p.communicate(),5)
            result=json.loads(stdout)
            self.assertEqual(p.returncode,0)
            self.assertTrue(result['passed'])
            self.assertFalse(result['microphoneOpened'])
            self.assertGreater(result['rms'],.1)
        finally:
            if p.returncode is None:p.kill();await p.wait()

    async def test_small_command_is_not_buffered_and_prepare_does_not_capture(self):
        service=NativeAudioService(Settings.from_env().audio_home)
        if sys.platform!='darwin' or not service.binary.is_file():
            self.skipTest('Build the native Mac helper to run real IPC checks')
        try:
            await service.ensure_started()
            before=await service.command('status',timeout=3)
            self.assertFalse(before['capturing'])
            if any(v['id']==NICKY for v in service.available_voices):
                await service.warm()
            after=await service.command('status',timeout=3)
            self.assertFalse(after['capturing'])
            self.assertEqual(after['permission'],before['permission'])
            self.assertIsNone(service.capture_owner)
        finally:await service.close()
