"""Fixed Music operations, never script text or file paths from a request."""
import asyncio
from contextlib import suppress
import json
from pathlib import Path
import re
from .errors import JuneError


class MusicNative:
    def __init__(self, binary):
        self.binary = Path(binary)

    async def _call(self, value):
        if not self.binary.is_file():
            raise JuneError('music-unavailable', 'The Apple Music helper is not installed.', 503)
        process = None
        try:
            process = await asyncio.create_subprocess_exec(str(self.binary), stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            output, _ = await asyncio.wait_for(process.communicate(json.dumps(value).encode()), 27)
            if len(output) > 65536:raise ValueError()
            reply = json.loads(output)
            if not isinstance(reply, dict):raise ValueError()
            return reply
        except (OSError, TimeoutError, ValueError, UnicodeError):
            raise JuneError('music-unavailable', 'Apple Music did not return a verified result. Check Music before retrying.', 503) from None
        finally:
            if process is not None and process.returncode is None:
                process.kill()
                with suppress(ProcessLookupError):await process.wait()

    def _check(self, reply):
        if reply.get('ok') is not True:
            code = reply.get('code')
            if code == 'automation-permission':
                raise JuneError(code, 'Allow June Music to control Music in macOS Privacy & Security → Automation, then enable it again.', 403)
            raise JuneError('music-unavailable', 'Apple Music could not complete this operation. Check its library and account.', 503)
        return reply

    async def permission(self):
        self._check(await self._call({'operation':'permission'}))

    async def playlists(self):
        reply = self._check(await self._call({'operation':'playlists'}))
        raw = reply.get('playlists')
        if not isinstance(raw,list) or len(raw)>200:
            raise JuneError('music-unavailable','Music returned an invalid playlist list.',502)
        items=[]
        for row in raw:
            if not isinstance(row,dict) or not isinstance(row.get('id'),str) or not re.fullmatch('[A-Fa-f0-9]{16}',row['id']) or not isinstance(row.get('name'),str) or not 1<=len(row['name'])<=200:
                raise JuneError('music-unavailable','Music returned an invalid playlist.',502)
            items.append(dict(id=row['id'].upper(),name=row['name']))
        return items

    async def play(self, payload):
        pid = payload.get('playlistId') if isinstance(payload,dict) else None
        if not isinstance(pid,str) or not re.fullmatch('[A-Fa-f0-9]{16}',pid):
            raise JuneError('invalid-playlist','Choose a playlist from Music.',400)
        reply = self._check(await self._call({'operation':'play','playlistId':pid.upper()}))
        verified = reply.get('state') == 'playing' and reply.get('playlistId') == pid.upper()
        return dict(verified=verified,message=('Music is playing the selected playlist: '+payload['playlistName']+'.') if verified else 'Music did not confirm playback of the selected playlist. Check Music before retrying.')

    async def control(self, op):
        if op not in ('next', 'previous', 'pause', 'resume', 'status'):
            raise JuneError('invalid-music', 'Unknown music control.', 400)
        reply = self._check(await self._call({'operation': op}))
        return dict(state=str(reply.get('state', ''))[:20], track=str(reply.get('track', ''))[:200], artist=str(reply.get('artist', ''))[:200])

    async def _library(self, operation, query, what):
        if not valid_query(query) or what not in ('any', 'artist', 'album', 'song'):
            raise JuneError('invalid-music', 'Say an artist, album or song name.', 400)
        reply = self._check(await self._call({'operation': operation, 'query': query, 'what': what}))
        kind, count = reply.get('kind'), reply.get('count')
        if kind not in ('artist', 'album', 'song') or type(count) is not int or count < 1:
            return None
        return dict(kind=kind, count=min(count, 100000), label=str(reply.get('label', ''))[:200], state=str(reply.get('state', ''))[:20],
                    track=str(reply.get('track', ''))[:200], artist=str(reply.get('artist', ''))[:200], playlist=str(reply.get('playlist', ''))[:200])

    async def find(self, query, what):
        """What the person's own library holds for this name, or None. Plays nothing."""
        return await self._library('find', query, what)

    async def play_library(self, query, what):
        return await self._library('play-library', query, what)


def valid_query(value):
    return isinstance(value, str) and re.fullmatch(r"[\w .,'&!+-]{1,80}", value, re.UNICODE) is not None and '_' not in value and bool(value.strip())
