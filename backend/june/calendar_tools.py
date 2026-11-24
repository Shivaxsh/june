"""Apple Calendar through a fixed native helper: reads events, and adds one event the person approved.
Nothing is ever changed or deleted."""
import asyncio
from contextlib import suppress
import json
import math
from pathlib import Path
from .errors import JuneError


class CalendarNative:
    def __init__(self, binary):
        self.binary = Path(binary)

    async def _call(self, value, timeout):
        if not self.binary.is_file():
            raise JuneError('calendar-unavailable', 'The Apple Calendar helper is not installed.', 503)
        process = None
        try:
            process = await asyncio.create_subprocess_exec(str(self.binary), stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            output, _ = await asyncio.wait_for(process.communicate(json.dumps(value).encode()), timeout)
            if len(output) > 262144: raise ValueError()
            reply = json.loads(output)
            if not isinstance(reply, dict): raise ValueError()
        except (OSError, TimeoutError, ValueError, UnicodeError):
            raise JuneError('calendar-unavailable', 'Apple Calendar did not answer. Try again.', 503) from None
        finally:
            if process is not None and process.returncode is None:
                process.kill()
                with suppress(ProcessLookupError): await process.wait()
        if reply.get('ok') is not True:
            if reply.get('code') == 'calendar-permission':
                raise JuneError('calendar-permission', 'Allow June Calendar in System Settings → Privacy & Security → Calendars (Full Access), then enable it again.', 403)
            if reply.get('code') == 'calendar-read-only':
                raise JuneError('calendar-unavailable', 'Your default calendar does not accept new events. Choose another default calendar in the Calendar app.', 409)
            raise JuneError('calendar-unavailable', 'Apple Calendar could not complete this request.', 503)
        return reply

    async def permission(self):
        # The person may take a while to answer the macOS prompt.
        await self._call({'operation': 'permission'}, 130)

    async def events(self, start, end):
        reply = await self._call({'operation': 'events', 'start': start, 'end': end}, 20)
        rows = reply.get('events')
        if not isinstance(rows, list) or len(rows) > 50:
            raise JuneError('calendar-unavailable', 'Apple Calendar returned an invalid event list.', 502)
        items = []
        for row in rows:
            if (not isinstance(row, dict) or not isinstance(row.get('title'), str) or type(row.get('allDay')) is not bool
                    or type(row.get('start')) not in (int, float) or not math.isfinite(row['start'])):
                raise JuneError('calendar-unavailable', 'Apple Calendar returned an invalid event.', 502)
            items.append(dict(title=row['title'], start=float(row['start']), allDay=row['allDay']))
        return items

    async def create(self, event):
        """Add one event to the default calendar and return what Calendar stored."""
        reply = await self._call({'operation': 'create', 'title': event['title'], 'start': event['start'], 'end': event['end'], 'allDay': event['allDay']}, 25)
        if (not isinstance(reply.get('title'), str) or type(reply.get('allDay')) is not bool or not isinstance(reply.get('calendar'), str)
                or any(type(reply.get(k)) not in (int, float) or not math.isfinite(reply[k]) for k in ('start', 'end'))):
            raise JuneError('calendar-unavailable', 'Apple Calendar returned an invalid event.', 502)
        return dict(title=reply['title'][:300], start=float(reply['start']), end=float(reply['end']), allDay=reply['allDay'], calendar=reply['calendar'][:100])
