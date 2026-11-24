"""Whether a sentence is understood by June's own fixed grammars (no model): shared by the router and corpus tests."""
import re
from datetime import datetime
from zoneinfo import ZoneInfo

SAVED = [dict(id='c1', name='dev server', kind='server', project='June'), dict(id='c2', name='Lint', kind='run', project='June')]
NOW = datetime(2027, 1, 15, 8, 0, tzinfo=ZoneInfo('Asia/Kolkata')).timestamp()


def understood(text):
    from june.app_actions import app_request, side_request
    from june.calendar_events import event_request
    from june.creations import bare_open, creation_request, open_request, restyle_request
    from june.daily_assistant import agenda_intent, briefing_intent, music_command, weather_intent
    from june.library_chat import INVENTORY
    from june.project_commands import command_request
    from june.quick_actions import quick_request
    from june.timers import timer_intent
    from june.websites import publish_request, withdraw_request
    from june.screen import screen_request
    return bool(screen_request(text) or withdraw_request(text) or family(text) or creation_request(text) or restyle_request(text) is not None or open_request(text) or bare_open(text) or publish_request(text)
                or quick_request(text) or command_request(text, SAVED) or event_request(text, NOW, 'Asia/Kolkata') or app_request(text) or side_request(text)
                or music_command(text) or agenda_intent(text) or weather_intent(text) is not None or briefing_intent(text) or timer_intent(text)
                or INVENTORY.match(text) or text == 'what reminders do I have'
                or re.match(r"\s*(?:(?:hey\s+)?june[,!:\s]+)?(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?remind me\b.+\bto\b", text, re.I))


def family(text):
    """The intent June's fixed grammars give a sentence, in the same order chat tries them; None when no grammar matches."""
    from june.app_actions import app_request, side_request
    from june.calendar_events import event_request
    from june.creations import bare_open, creation_request, open_request, restyle_request
    from june.daily_assistant import agenda_intent, briefing_intent, music_command, weather_intent
    from june.library_chat import INVENTORY
    from june.project_commands import command_request
    from june.quick_actions import quick_request
    from june.timers import timer_intent
    from june.websites import publish_request
    if re.match(r"\s*(?:(?:hey\s+)?june[,!:\s]+)?(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?remind me\b.+\bto\b", text, re.I):
        return 'set_reminder'
    if re.match(r"\s*(?:what|which|show|list|any)\b.*\breminders?\b", text, re.I) and not re.search(r'\bremind me\b', text, re.I):
        return 'list_reminders'
    timer = timer_intent(text)
    if timer:
        return {'create': 'set_timer', 'cancel': 'cancel_timer', 'list': 'timer_left', 'status': 'timer_left'}.get(timer.get('operation'), 'timer')
    if briefing_intent(text):
        return 'briefing'
    if event_request(text, NOW, 'Asia/Kolkata'):
        return 'add_event'
    agenda = agenda_intent(text)
    if agenda:
        return 'calendar_tomorrow' if agenda[0] == 1 else 'calendar_today'
    if weather_intent(text) is not None:
        return 'weather'
    music = music_command(text)
    if music:
        op = music[1] if music[0] == 'control' else music[0]
        return {'pause': 'pause_music', 'resume': 'resume_music', 'next': 'next_song', 'previous': 'previous_song', 'status': 'now_playing',
                'play': 'play_music', 'playlist': 'play_music', 'library': 'play_named'}.get(op, 'music:' + str(op))
    if open_request(text) or bare_open(text):
        return 'open_creation'
    if restyle_request(text) is not None:
        return 'restyle'
    if creation_request(text):
        return 'create_document'
    if publish_request(text):
        return 'publish_site'
    from june.screen import screen_request
    if screen_request(text):
        return 'read_screen'
    from june.websites import withdraw_request
    withdrawn = withdraw_request(text)
    if withdrawn:
        return 'unpublish_site' if withdrawn == 'unpublish' else 'rollback_site'
    from june.jobs import jobs_request
    from june.mail_tools import mail_request
    mailed = mail_request(text)
    if mailed:
        return {'check': 'check_email', 'from': 'check_email', 'read': 'read_email', 'write': 'write_email', 'reply': 'reply_email'}[mailed[0]]
    job = jobs_request(text)
    if job:
        return {'find': 'find_jobs', 'apply': 'apply_job', 'applied': 'list_applications'}[job[0]]
    project = command_request(text, SAVED)
    if project:
        return {'project-pull': 'project_pull', 'project-push': 'project_push', 'project-command': 'run_saved_command', 'project-stop': 'stop_command',
                'project-recipe': 'project_test' if project[1].get('recipe') == 'test' else 'project_build'}[project[0]]
    quick = quick_request(text)
    if quick:
        return {'coding-session': 'coding_session', 'design-workspace': 'design_workspace', 'keep-awake': 'keep_awake', 'allow-sleep': 'allow_sleep',
                'appearance': 'appearance', 'free-port': 'free_port', 'git-status': 'git_status', 'open-github': 'open_github', 'convert-images': 'convert_images',
                'open-app': 'open_app'}[quick[0]]
    from june.actions import action_intent
    if app_request(text) or side_request(text) or action_intent(text):
        return 'open_app'
    if INVENTORY.match(text):
        return 'list_documents'
    return None
