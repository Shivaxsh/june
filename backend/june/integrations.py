"""The executable registry is application-owned; unavailable tools cannot run."""
from .tool_plans import Capability, ToolPlans
from .actions import DETAIL
from .errors import JuneError


CONNECTIONS = (
    ('apple-calendar', 'Apple Calendar', 'Calendar reading is off.'),
    ('google', 'Google Calendar and Gmail', 'Authorise calendar and mail separately when their connectors are ready.'),
    ('open-meteo', 'Weather', 'Choose a city and enable the weather connector before online requests.'),
    ('apple-music', 'Apple Music', 'Playlist selection and macOS Automation permission are not configured yet.'),
    ('github-pages', 'GitHub Pages', 'Publishing needs a selected repository and separate authorisation.'),
    ('mcp', 'Local MCP tools', 'No MCP servers or tools have been registered.'),
    ('home-assistant', 'Home Assistant', 'No Home Assistant instance or devices are configured.'),
)


def connection_state(plans):
    daily=getattr(plans,'daily',None)
    return plans.envelope(connections=[daily.connection(cid) if daily and cid in ('google','open-meteo','apple-music','apple-calendar') else dict(id=cid, label=label, state='not-configured',
        hosts=[], scopes=[], checkedAt=None, message=message) for cid, label, message in CONNECTIONS])


def no_input(build):
    """An intent that takes no arguments refuses any."""
    def steps(value):
        if value != {}:
            from .errors import JuneError
            raise JuneError('invalid-plan', 'This intent accepts no additional arguments.', 400)
        return build(value)
    return steps


def create_tools(directory, actions, daily=None, apps=None):
    async def open_vscode(payload):
        # The new review authorises exactly the existing fixed action. Preserve its
        # native verification, audit trail and existing remembered preference.
        proposal = (await actions.propose({'action': 'open-vscode'}))['action']
        reply = (await actions.approve(proposal['id'], {'fingerprint': proposal['fingerprint']}))['action']
        result = reply.get('result', {})
        return dict(message=result.get('message', 'The app outcome could not be verified.'),
                    verified=reply['status'] == 'completed', failed=reply['status'] == 'failed')

    def remember(payload, value):
        if actions:
            with actions.db() as db:
                db.execute("INSERT OR REPLACE INTO preferences VALUES('open-vscode',?)", (int(value),))

    capabilities = [Capability('app.open-vscode', 'Open Visual Studio Code', 'local', 'local', True,
        open_vscode if actions else None, available=actions is not None,
        unavailable_reason='Mac actions are not ready. Check Hands.',
        trusted=lambda payload: bool(actions and actions.trusted()), remember=remember)]
    for cid, label, connector, risk in (
        ('calendar.read', 'Read calendar events', 'apple-calendar', 'read'),
        ('weather.read', 'Read local weather', 'open-meteo', 'read'),
        ('music.play', 'Play a selected playlist', 'apple-music', 'local'),
        ('mail.read', 'Read selected email', 'google', 'read'),
        ('mail.send', 'Send a reviewed email', 'google', 'outward'),
        ('site.publish', 'Publish a reviewed website', 'github-pages', 'outward'),
        ('mcp.call', 'Run a registered MCP tool', 'mcp', 'local'),
        ('home.control', 'Control a selected light or switch', 'home-assistant', 'local'),
    ):
        capabilities.append(Capability(cid, label, connector, risk, False, available=False))
    plans = ToolPlans(directory, capabilities=capabilities,
        intents={'open-vscode': no_input(lambda value: [('app.open-vscode', {'action': 'open-vscode'}, DETAIL)])})
    plans.daily=daily
    if apps is not None:
        from .app_actions import register
        register(plans, apps)
    if daily:
        async def play(payload):
            if not daily.enabled('apple-music'):
                return dict(verified=False,failed=True,message='Apple Music access was disabled before playback started.')
            return await daily.music.play(payload)
        plans.capabilities['music.play']=Capability('music.play','Play the selected Apple Music playlist','apple-music','local',True,play,
            available=False,unavailable_reason='Enable Apple Music and choose a playlist in Daily.')
        def playlist_steps(value):
            selected=daily.settings()['settings']['music']['playlist']
            if not selected:
                from .errors import JuneError
                raise JuneError('music-not-configured','Choose your playlist in Daily first.',409)
            return [('music.play',dict(playlistId=selected['id'],playlistName=selected['name']),
                'Play the Apple Music playlist '+selected['name']+' (persistent ID '+selected['id']+'). No other playlist or app is controlled.')]
        plans.intents['play-playlist']=no_input(playlist_steps)
        # One approval ("Don't ask again") covers music controls and playing from the person's own
        # library by voice. It is stored with the Apple Music connection and cleared when that is
        # turned off or approvals are forgotten.
        def voice(payload): return daily.music_voice()
        def remember_voice(payload, value): daily.set_music_voice(value)
        async def control(payload):
            if not daily.enabled('apple-music'):
                return dict(verified=False, failed=True, message='Apple Music access was turned off. Nothing was changed.')
            op = payload.get('op')
            now = await daily.music.control(op)
            playing = now['state'] == 'playing'
            song = (now['track'] + (' by ' + now['artist'] if now['artist'] else '')) if now['track'] else 'the next song'
            if op == 'pause':
                return dict(verified=not playing, message='Music is paused.' if not playing else 'Music is still playing. Check the Music app.')
            if op == 'resume':
                return dict(verified=playing, message='Music is playing ' + song + '.' if playing else 'Music did not start playing. Check the Music app.')
            if op == 'previous' and not playing:
                return dict(verified=False, message='Music stopped instead of going back, which happens on the first song of a list. Say “play some music” to start again.')
            return dict(verified=playing, message='Now playing ' + song + '.' if playing else 'Music is not playing, so the song was not changed. Check the Music app.')
        async def library(payload):
            if not daily.enabled('apple-music'):
                return dict(verified=False, failed=True, message='Apple Music access was turned off. Nothing was played.')
            now = await daily.music.play_library(payload['query'], payload['what'])
            if not now:
                return dict(verified=False, failed=True, message=payload['query'].title() + ' isn’t in your Music library or playlists. Nothing was played.')
            ok = now['state'] == 'playing' and now['playlist'] == 'June Queue'
            count = now['count']
            what = {'artist': 'by ' + payload['query'].title(), 'album': 'from the album ' + now['label'], 'song': 'matching ' + now['label']}[now['kind']]
            song = (now['track'] + (' by ' + now['artist'] if now['artist'] else '')) if now['track'] else ''
            return dict(verified=ok, message=(f'Playing {count} song{"" if count == 1 else "s"} {what} from your library.' + (' Now playing ' + song + '.' if song else '')) if ok
                        else 'Music did not confirm that it is playing ' + now['label'] + '. Check the Music app.')
        plans.capabilities['music.control']=Capability('music.control','Control music playback','apple-music','local',True,control,
            available=False,unavailable_reason='Enable Apple Music in Daily.',trusted=voice,remember=remember_voice)
        plans.capabilities['music.library']=Capability('music.library','Play from your Music library','apple-music','local',True,library,
            available=False,unavailable_reason='Enable Apple Music in Daily.',trusted=voice,remember=remember_voice)
        CONTROL_WORDS={'next':('Skip to the next song','Skip to the next song in Music.'),'previous':('Go back a song','Go back to the previous song in Music.'),
            'pause':('Pause music','Pause playback in Music.'),'resume':('Resume music','Resume playback in Music.')}
        def control_steps(value):
            from .errors import JuneError
            if not isinstance(value,dict) or set(value)!={'op'} or value['op'] not in CONTROL_WORDS:
                raise JuneError('invalid-plan','Choose pause, resume, next or previous.',400)
            label,preview=CONTROL_WORDS[value['op']]
            return [('music.control',dict(op=value['op']),preview+' Nothing else is changed.',label)]
        control_steps.accepts_input=True
        def library_steps(value):
            from .errors import JuneError
            from .music_tools import valid_query
            if not isinstance(value,dict) or set(value)!={'query','what'} or not valid_query(value['query']) or value['what'] not in ('any','artist','album','song'):
                raise JuneError('invalid-plan','Say an artist, album or song from your Music library.',400)
            query=value['query'].strip()
            kind={'any':'artist, album or song','artist':'artist','album':'album','song':'song'}[value['what']]
            return [('music.library',dict(query=query,what=value['what']),
                f'Play songs from your own Music library matching the {kind} “{query.title()}”, through a playlist named June Queue that June refills. Nothing is bought, added to or removed from your library.',
                'Play '+query.title()+' from your library')]
        library_steps.accepts_input=True
        async def add_event(payload):
            from .calendar_events import when_phrase
            if not daily.enabled('apple-calendar') or daily.calendar is None:
                return dict(verified=False, failed=True, message='Calendar access was turned off. Nothing was added.')
            try:
                stored = await daily.calendar.create(payload)
            except JuneError as failure:
                # The helper refused before saving anything: a clear failure, not an unknown outcome.
                if failure.code != 'calendar-permission': raise
                daily.calendar_lost()
                return dict(verified=False, failed=True, message='macOS no longer allows June Calendar, so nothing was added. Open Systems → Daily → Calendar, click Allow June to read Calendar, then ask again.')
            same = stored['title'] == payload['title'] and abs(stored['start'] - payload['start']) < 60 and stored['allDay'] == payload['allDay']
            alert = 'an alert at 9 AM that day' if payload['allDay'] else 'an alert 15 minutes before'
            return dict(verified=same, message=(f'Added “{stored["title"]}” to your {stored["calendar"]} calendar for {when_phrase(stored, daily.zone_name())}, with {alert}.') if same
                        else 'June could not confirm the event Calendar stored. Check the Calendar app before asking again.')
        # Every event is reviewed: this capability can never be remembered.
        plans.capabilities['calendar.add']=Capability('calendar.add','Add an event to your Calendar','apple-calendar','local',False,add_event,
            available=False,unavailable_reason='Allow June to read Calendar in Daily first.')
        def event_steps(value):
            from .errors import JuneError
            from .calendar_events import valid_event, when_phrase
            if not valid_event(value, daily.clock()):
                raise JuneError('invalid-plan','Give the event a title and a future time within a year.',400)
            event=dict(title=value['title'].strip(),start=float(value['start']),end=float(value['end']),allDay=value['allDay'])
            alert='an alert at 9 AM that day' if event['allDay'] else 'an alert 15 minutes before'
            return [('calendar.add',event,f'Add “{event["title"]}” to your default calendar: {when_phrase(event, daily.zone_name())}, with {alert}. No other event is changed or deleted, and nothing leaves this Mac.',
                     'Add “'+event['title']+'” to Calendar')]
        event_steps.accepts_input=True
        plans.intents['calendar-add']=event_steps
        plans.intents['music-control']=control_steps
        plans.intents['music-library']=library_steps
        plans.intents['focus-session']=no_input(lambda value: [('app.open-vscode',{'action':'open-vscode'},DETAIL)]+playlist_steps(value))

    async def readiness():
        cap = plans.capabilities['app.open-vscode']
        cap.available = bool(actions and (await actions._inspect())['available'])
        if 'app.open' in plans.capabilities:
            plans.capabilities['app.open'].available = bool(apps and apps.ready())
        if daily:
            plans.capabilities['music.play'].available=bool(daily.enabled('apple-music') and daily.music and daily.settings()['settings']['music']['playlist'])
            for cid in ('music.control','music.library'):
                plans.capabilities[cid].available=bool(daily.enabled('apple-music') and daily.music)
            plans.capabilities['calendar.add'].available=bool(daily.enabled('apple-calendar') and daily.calendar)
            plans.capabilities['weather.read'].available=daily.enabled('open-meteo') and bool(daily.settings()['settings']['weather']['place'])
            plans.capabilities['calendar.read'].available=daily.enabled('apple-calendar') or daily.meta('google').get('state')=='connected'
            # Read capabilities are exercised only through the fact-building briefing,
            # not accepted as arbitrary plan steps.

    plans.readiness = readiness
    return plans
