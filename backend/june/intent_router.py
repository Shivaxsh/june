"""A safety net for requests about June's own tools that her fixed grammars did not recognise.

The model only chooses one intent from a closed list and copies details from the request. June then
builds a standard command herself and runs it through the same strict grammars, plans and checks as
any typed command. The model never writes a command, a path or a reply here, and any detail it returns
that the person did not say is refused.
"""
import json
import re

from .app_info import nonliteral_request
from .chat import MODEL_KEEP_ALIVE
from .knowledge import bounded_json

# Words that suggest the request is about something June can do.
FILE_KIND = (r"web\s?sites?|sites?|web\s?pages?|landing\s+page|home\s?page|portfolio|presentations?|power\s?points?|slides?|slide\s?deck|decks?|pdfs?|"
             r"documents?|docs?|docx|word\s+(?:doc|document|file)|reports?|write-?ups?|brochures?|flyers?|posters?|invitations?|invites?|newsletters?|handouts?|"
             r"cvs?|resumes?|résumés?|proposals?|letters?|cards?")
DOMAIN = re.compile(
    r"\b(?:open|launch|app|apps|music|songs?|tracks?|playlist|play|playing|pause|skip|timer|timers|countdown|remind(?:er|ers)?|"
    r"calendar|events?|meetings?|appointments?|schedule|agenda|weather|temperature|files|briefing|listen|listening|tunes|figma|chrome|browser|terminal|notes|excel|"
    r"powerpoint|word|claude|chatgpt|affinity|mail|email|vs\s?code|app\s+store|" + FILE_KIND + r"|publish|unpublish|deploy|put\s+it\s+online|make\s+it\s+live|go\s+live|offline|roll\s+back|revert|previous\s+version|old\s+version|screen|"
    r"style|design|(?:different|new|another)\s+look|colou?rs?|theme|aesthetics?|awake|(?:mac|computer|laptop)\s+(?:to\s+)?sleep|dark\s+mode|light\s+mode|appearance|"
    r"port\s+\d+|git|github|repo|repository|push|commit|tests|run\s+the\s+build|(?:convert|resize)\s+(?:\w+\s+){0,2}(?:images?|pictures?|photos?)|screenshot|"
    r"coding\s+(?:session|mode)|dev\s+server|lint|inbox|e-?mails?|naukri|jobs?|recruiters?|appl(?:y|ied|ications?)|openings?|"
    # timers, alarms and times of day
    r"\d+\s*(?:seconds?|secs?|minutes?|mins?|hours?|hrs?)|alarm|count\s*down|time\s+left|\d{1,2}(?::\d{2})?\s*(?:am|pm)|tomorrow|tonight|"
    r"(?:mon|tues|wednes|thurs|fri|satur|sun)day|calls?|weather|cold|hot|warm|rain(?:ing|y)?|sunny|outside|brief|my\s+day|mac|computer|laptop|"
    # changing the look of what June just made, or seeing it
    r"(?:it|this|that)\b.{0,30}\b(?:darker|lighter|brighter|calmer|warmer|bolder|softer|modern|fun|playful|elegant|professional|colou?rful|minimal|retro|magazine|cute|pretty)|"
    r"serif|fonts?|feel|(?:it|this|that)\s+look|see\s+(?:it|the\s+\w+)|(?:test|build)\s+june|more\s+(?:colou?rful|elegant|modern|fun|playful|professional|minimal|bold|calm))\b", re.I)
# Only files June builds: "write a report" is a document; "write a letter" or "a card" is writing for chat.
_FILES = re.compile(r"\b(?:web\s?sites?|sites?|web\s?pages?|landing\s+page|home\s?page|portfolio|presentations?|power\s?points?|ppt|slides?|decks?|pdfs?|"
                    r"documents?|docs?|docx|reports?|brochures?|flyers?|posters?|newsletters?|handouts?)\b", re.I)
# A direct request or a question about the person's own things, not a general-knowledge or writing task.
_DIRECT = re.compile(
    r"^\s*(?:(?:ok(?:ay)?|so|well|now|and|oh|um|uh|hey|hi|please|alright|yes|yeah|great|cool)[,\s]+)*(?:june[,!:\s]+)?(?:please\s+)?(?:(?:can|could|would|will)\s+you\s+|i\s+(?:want|need|wanna)\s+|i['’]d\s+like\s+|"
    r"let['’]?s\s+|(?:can|could)\s+i\s+(?:get|have)\s+|i\s+(?:don['’]?t|do\s+not)\s+like\b|don['’]?t\s+let\b|"
    r"(?:open|launch|start|play|put|pause|stop|skip|resume|continue|set|cancel|show|check|tell|give|turn|switch|bring|pull|fire|next|previous|change|read|get|run|begin|kill|"
    r"make|create|build|write|draft|design|generate|prepare|produce|whip|throw|knock|redo|restyle|redesign|remake|try|publish|deploy|upload|add|schedule|book|remind|keep|"
    r"free|clear|convert|resize|push|commit|go|use|do|help|need|want|hold|test|count|let\s+me|can\s+i|can\s+it|could\s+it|is\s+it|"
    r"answer|reply|respond|email|mail|send|shoot|drop|apply|find|search|look|refresh|summari[sz]e|how\s+(?:are|is)\s+my|did\s+\w+\s+(?:email|mail|reply)|"
    r"what['’]?s|what\s+is|what\s+are|what\s+do\s+i|what\s+have\s+i|what\s+\w+\s+(?:do|have|are|is)|which|any|anything|is\s+there|are\s+there|is\s+it|do\s+i|have\s+i|how\s+(?:much|long|hot|cold|warm)|who['’]?s|who\s+is)\b)", re.I)
# "Don't open Chrome" is refused; "don't let my Mac sleep" and "I don't like the colours, change them" are requests.
# "That website was great", "my friend has a website": talk about things, not requests.
_STATEMENT = re.compile(r"^\s*(?:my|that|this|the|it|his|her|our|their|your|i)\b(?!\s+(?:want|need|wanna|would\s+like|['’]d\s+like))(?:\s+\w+){0,4}?\s+(?:was|were|went|is|are|has|have|had|looks?|seems?|did|got)\b", re.I)
_NEGATED = re.compile(r"^\s*(?:(?:hey\s+)?june[,!:\s]+)?(?:please\s+)?(?:do\s+not|don['’]?t|never|not)\b(?!\s+let\b)", re.I)
_KNOWLEDGE = re.compile(r"^\s*(?:(?:hey|hi|ok(?:ay)?|so)[,\s]+)*(?:june[,!:\s]+)?(?:how\s+(?:do|to|can|does|would|should)|why|explain|define|translate|summari[sz]e|compare|describe|"
                        r"what\s+(?:is|are)\s+(?:a|an)\b|what\s+does|tell\s+me\s+about|teach|what\s+makes|what\s+should|"
                        r"how\s+(?:many|long|much|big|often)\b(?!.*\bleft\b)(?:\s+\w+){0,3}\s+(?:should|does|do|would|can|could|is\s+a|are)\b|give\s+me\s+(?:some\s+)?(?:ideas|tips|advice)|"
                        # "what is github", "what is the theme of hamlet": definitions; "what is the weather", "what is on my calendar": requests
                        r"what\s+(?:is|are)\s+(?!(?:the\s+)?(?:weather|temperature|time\s+left|git\s+status\s+(?:of|for)|forecast)\b|on\b|my\b|playing\b|this\s+song|that\s+song|left\b|there\b)(?:the\s+)?\w+)\b", re.I)
# "That pdf was nice", "I love the website", "thanks for the slides": a remark to June, not a question about the library.
REMARK = re.compile(
    r"^(?!.*\b(?:change|redo|make|try|fix|use|restyle|redesign|swap|switch|open|publish|next|skip|stop|pause|another|can\s+you|could\s+you|please)\b)"  # "…, change them" is a request
    r"\s*(?:(?:wow|oh|ok(?:ay)?|great|nice|cool|aw+|thanks?|thank\s+you|haha)[,!.\s]+)*(?:june[,!.\s]+)?"
    r"(?:(?:that|this|the|your|my|these|those)\s+(?:\w+\s+){0,3}?(?:was|is|are|were|looks?|looked|seems?|seemed|turned\s+out|came\s+out)\s+"
    r"(?:really\s+|very\s+|so\s+|quite\s+|pretty\s+|super\s+|a\s+bit\s+|kind\s+of\s+)?(?:nice|great|good|lovely|amazing|awesome|beautiful|perfect|cool|fine|"
    r"gorgeous|cute|stunning|helpful|useful|bad|ugly|wrong|weird|boring|okay|ok)"
    r"|i\s+(?:really\s+)?(?:love|like|loved|liked|hate|hated|don['’]?t\s+like)\s+(?:the|that|this|your|my|it)\b"
    r"|thanks?\s+(?:you\s+)?for\s+(?:the|that|this|my|your)\s+\w+)[^?]*$", re.I)


# Writing tasks June answers in chat. With a file word ("write a report document") they are document requests.
_WRITING = re.compile(r"^\s*(?:(?:can|could|would)\s+you\s+)?(?:please\s+)?(?:write|draft)\b|\b(?:python|javascript|(?<!vs\s)code|function|script|essay|poem|story|history of|meaning of)\b", re.I)

INTENTS = {
    'none': 'not one of these, or a question, advice, explanation or writing task',
    'create_document': 'make a new file: kind is word, presentation, pdf or website; name = what it is about, copied; detail = style words said (e.g. dark minimal); number = slides or sections if said',
    'restyle': 'change the look of the file or website June just made (make it darker, calmer, other colours or fonts); detail = style words said',
    'open_creation': 'open or preview the file or site June just made',
    'publish_site': 'put the website June made online',
    'unpublish_site': 'take the website June published off the internet',
    'read_screen': 'look at or read what is on their screen now and answer about it',
    'rollback_site': 'undo the last publish: put back the earlier published version of the website',
    'open_app': 'name = the app, copied', 'play_music': 'start their music, no name', 'play_named': 'name = artist, album or song, copied',
    'pause_music': '', 'resume_music': '', 'next_song': 'skip or change the song', 'previous_song': '', 'now_playing': 'which song is on',
    'set_timer': 'name = the length as said, e.g. ten minutes', 'cancel_timer': '', 'timer_left': '',
    'set_reminder': 'name = what to remember, copied; detail = when, copied (e.g. tomorrow at 5 pm)', 'list_reminders': '',
    'add_event': 'add to their calendar: name = event title, copied; detail = when, copied (e.g. tomorrow at 5 pm)',
    'calendar_today': 'their events today', 'calendar_tomorrow': 'their events tomorrow', 'weather': '', 'briefing': 'their daily briefing',
    'list_documents': 'which files June holds',
    'coding_session': 'start a coding session', 'design_workspace': 'start a design session', 'keep_awake': 'number = how long; detail = minutes or hours',
    'allow_sleep': 'let the Mac sleep again', 'appearance': 'the Mac’s own dark or light mode, only when they say mode or the Mac; detail = dark, light or toggle', 'free_port': 'number = the port',
    'git_status': 'name = project if said', 'open_github': 'open a project on GitHub; name = project if said', 'convert_images': 'detail = png or jpeg',
    'project_pull': 'git pull; name = project if said', 'project_push': 'commit and push code; name = project if said; detail = commit message, copied',
    'project_test': 'run tests; name = project if said', 'project_build': 'run a build; name = project if said',
    'run_saved_command': 'start a saved command; name = its name, copied', 'stop_command': 'stop a running saved command; name = its name, copied',
    'check_email': 'look at their inbox or new emails', 'read_email': 'read or summarise one email; name = the sender if said, copied',
    'write_email': 'send a new email from their Mail; name = recipient name or address, copied; detail = what to say, copied',
    'reply_email': 'reply to an email; name = who to reply to, copied; detail = what to say, copied',
    'find_jobs': 'find or refresh job openings on Naukri', 'apply_job': 'apply to jobs June found; number = how many top jobs; name = the company, copied',
    'list_applications': 'which jobs they applied to, or recruiter replies',
}
KINDS = ('none', 'word', 'presentation', 'pdf', 'website')
# The model writes fields in alphabetical order, so the names put the decision first.
SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['step1_intent', 'step2_kind', 'step3_name', 'step4_detail', 'step5_number'], 'properties': {
    'step1_intent': {'type': 'string', 'enum': list(INTENTS)}, 'step2_kind': {'type': 'string', 'enum': list(KINDS)},
    'step3_name': {'type': 'string', 'maxLength': 120}, 'step4_detail': {'type': 'string', 'maxLength': 80}, 'step5_number': {'type': 'string', 'maxLength': 12}}}
PROMPT = ('You route one request to June, a personal assistant on a Mac. Choose exactly one intent. Choose "none" unless the person clearly asks June to do it now '
          'or asks about their own calendar, reminders, timers, music, weather or files. Questions about how to do something, explanations and writing tasks '
          '(a poem, an email, code) are "none". Copy name and detail word for word from the request; leave them empty when not said. JSON only.\nIntents: '
          + '; '.join(f'{k} ({v})' if v else k for k, v in INTENTS.items()))
_FIXED = {'play_music': 'play some music', 'pause_music': 'pause the music', 'resume_music': 'resume the music', 'next_song': 'next song',
          'previous_song': 'previous song', 'now_playing': 'what’s playing', 'cancel_timer': 'cancel the timer',
          'timer_left': 'how much time is left on the timer', 'calendar_today': 'what’s on my calendar today',
          'calendar_tomorrow': 'what’s on my calendar tomorrow', 'weather': 'what’s the weather', 'list_reminders': 'what reminders do I have',
          'list_documents': 'what documents do I have', 'briefing': 'brief me', 'open_creation': 'open it', 'publish_site': 'publish it',
          'unpublish_site': 'take my website down', 'rollback_site': 'undo the last publish',
          'check_email': 'check my email', 'find_jobs': 'find me jobs on naukri', 'list_applications': 'what jobs did I apply to',
          'coding_session': 'start a coding session', 'design_workspace': 'start a design session', 'allow_sleep': 'let my mac sleep'}
_KIND_WORDS = {'word': 'Word document', 'presentation': 'presentation', 'pdf': 'PDF', 'website': 'website'}


def routable(text):
    """Whether an unrecognised message is worth one routing call: short, direct, and about June's tools."""
    if not isinstance(text, str) or not 3 <= len(text.strip()) <= 200 or '\n' in text.strip() or nonliteral_request(text):
        return False
    # Short noun-first commands count as direct too: "music please", "timer 2 minutes", "morning briefing".
    # Naming a kind of file June makes is enough, whatever the verb ("toss together a pdf on …"); questions are still excluded.
    direct = (_DIRECT.match(text) or (len(text.split()) <= 6 and DOMAIN.match(text.strip())) or len(text.split()) <= 3
              or (_FILES.search(text) and not text.rstrip().endswith('?') and not _STATEMENT.match(text)))
    if not DOMAIN.search(text) or not direct or _NEGATED.search(text) or _KNOWLEDGE.match(text) or REMARK.match(text):
        return False
    return not _WRITING.search(text) or bool(_FILES.search(text))


def _words(text):
    return re.findall(r"[a-z0-9]+", text.lower().replace('’', "'").replace("'", ''))


def _said(value, text, limit=120):
    """The value when every word in it was said by the person, else ''."""
    if not isinstance(value, str):
        return ''
    value = re.sub(r"\s+", ' ', value).strip(" .,!?\"“”'‘’")
    if not value or len(value) > limit or re.search(r'[;`$<>|\\{}]', value):
        return ''
    said = set(_words(text))
    said |= {w[:-1] for w in said if w.endswith('s')}
    wanted = _words(value)
    return value if wanted and all(w in said or w.rstrip('s') in said for w in wanted) else ''


def _number(value, text):
    value = _said(value, text, 12)
    return value if value and re.fullmatch(r"\d{1,5}|an?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|thirty|forty|forty-five|ninety", value, re.I) else ''


def _style(value, text):
    from .designs import pins_from
    words = [w for w in _words(value or '') if w in _words(text) and pins_from(w)]
    return ' and '.join(dict.fromkeys(words))


def command(choice, text):
    """June's own standard command for the chosen intent, or None. Every detail must have been said by the person."""
    if not isinstance(choice, dict):
        return None
    intent = choice.get('step1_intent', choice.get('intent'))
    if intent not in INTENTS or intent == 'none':
        return None
    name = _said(choice.get('step3_name', choice.get('name')), text)
    detail = _said(choice.get('step4_detail', choice.get('detail')), text, 80)
    number = _number(choice.get('step5_number', choice.get('number')), text)
    # Opening or publishing what June made needs those words in the request, never a guess from "I love the website".
    if intent == 'open_creation' and not re.search(r"\b(?:open|see|show|preview|view|look\s+at|display)\b", text, re.I):
        return None
    if intent == 'publish_site' and not re.search(r"\b(?:publish|online|live|deploy|upload|github|internet|web)\b", text, re.I):
        return None
    if intent == 'read_screen':
        return f'look at my screen and tell me: {text.strip()[:180]}' if re.search(r"\bscreen\b", text, re.I) else None
    if intent == 'unpublish_site' and not re.search(r"\b(?:unpublish|down|offline|remove|delete|off)\b", text, re.I):
        return None
    if intent == 'rollback_site' and not re.search(r"\b(?:undo|revert|roll|back|previous|earlier|old|older|restore)\b", text, re.I):
        return None
    if intent in _FIXED:
        return _FIXED[intent]
    if intent == 'open_app':
        return f'open {name}' if name else None
    if intent == 'play_named':
        return f'play {name}' if name else None
    if intent == 'set_timer':
        return f'set a timer for {name}' if name else None
    if intent == 'create_document':
        kind = choice.get('step2_kind', choice.get('kind'))
        if kind not in _KIND_WORDS or not name:
            return None
        subject = re.sub(r"^(?:(?:a|an|the|some|my)\s+)?(?:(?:simple|short|new|small)\s+)?(?:web\s?site|site|web\s?page|landing\s+page|presentation|slides?|slide\s+deck|deck|ppt|pdf|"
                         r"document|word\s+(?:doc|document)|doc|report)\s+(?:about|on|for|of|explaining|covering)\s+", '', name, flags=re.I)
        subject = re.sub(r"^(?:a|an|the)\s+(?=(?:web\s?site|site|presentation|pdf|document|word\s+document)\b)", '', subject, flags=re.I)
        subject = re.sub(r"\s+(?:web\s?site|site|web\s?page|presentation|slides|slide\s+deck|deck|pdf|document|word\s+document|doc)$", '', subject, flags=re.I).strip()
        if len(subject) < 2:
            return None
        style = _style(choice.get('step4_detail', choice.get('detail')), text)
        line = f'make a {_KIND_WORDS[kind]} about {subject}'
        if number and number.isdigit() and 2 <= int(number) <= 12:
            line += f' with {number} {"slides" if kind == "presentation" else "sections"}'
        return line + (f' in a {style} style' if style else '')
    if intent == 'restyle':
        style = _style(choice.get('step4_detail', choice.get('detail')), text)
        return f'redo it in {style}' if style else 'make it in a different style'
    if intent == 'set_reminder':
        return f'remind me {detail} to {name}' if name and detail else None
    if intent == 'add_event':
        return f'add an event {detail} called {name}' if name and detail else None
    if intent == 'keep_awake':
        unit = 'hours' if re.search(r'\bhours?\b|\bhrs?\b', text, re.I) and not re.search(r'\bminutes?\b|\bmins?\b', text, re.I) else 'minutes'
        return f'keep my mac awake for {number} {unit}' if number else 'keep my mac awake'
    if intent == 'appearance':
        mode = (detail or '').lower()
        return 'dark mode' if mode == 'dark' else 'light mode' if mode == 'light' else 'toggle dark mode'
    if intent == 'free_port':
        return f'free port {number}' if number.isdigit() else None
    if intent == 'convert_images':
        fmt = 'jpeg' if re.search(r'\bjpe?g\b', text, re.I) else 'png'
        return f'convert my images to {fmt}'
    if intent == 'git_status':
        return f'git status of {name}' if name else 'git status'
    if intent == 'open_github':
        return f'open {name} on github' if name else 'open the github repo'
    if intent == 'project_pull':
        return f'pull the latest changes for {name}' if name else 'git pull'
    if intent == 'project_push' and not re.search(r"\b(?:push|commit|upload)\b.*\b(?:changes|code|patch|commits?|github|repo|repository|work|project|branch|june)\b|\bgit\s+push\b", text, re.I):
        return None  # "commit to the plan" is not about code
    if intent == 'project_push':
        target = f' {name}' if name else ' my changes'
        if not detail:
            return f'push{target}'
        return f'commit and push {name} with the message {detail}' if name else f'push my changes with message {detail}'
    if intent == 'project_test':
        return f'run tests in {name}' if name else 'run the tests'
    if intent == 'project_build':
        return f'build {name}' if name else 'run the build'
    if intent == 'read_email':
        return f'read the latest email from {name}' if name else 'read the latest email'
    if intent == 'write_email':
        return f'send an email to {name} about {detail}' if name and detail else None
    if intent == 'reply_email':
        return f'reply to {name} saying {detail}' if name and detail else None
    if intent == 'apply_job':
        # A position in the list June showed ("the second one", "job 2") is not "the top N".
        place = re.search(r"\b(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|last)\b|\b(?:job|number|no\.?|#)\s*([1-5])\b", text, re.I)
        if place:
            return f'apply to job {place[2]}' if place[2] else f'apply to the {place[1].lower()} one'
        if number.isdigit() and 1 <= int(number) <= 5:
            return f'apply to the top {number}'
        return f'apply to the {name} one' if name else None
    if intent == 'run_saved_command':
        return f'run {name}' if name else None
    if intent == 'stop_command':
        return f'stop the {name}' if name else None
    return None


async def route(client, settings, text):
    """The standard command for an unrecognised request about June's tools, or None. Never raises."""
    if not routable(text):
        return None
    try:
        result = await bounded_json(client, settings.ollama + '/api/chat', {
            'model': settings.model, 'stream': False, 'think': False, 'format': SCHEMA, 'keep_alive': MODEL_KEEP_ALIVE,
            'messages': [{'role': 'system', 'content': PROMPT}, {'role': 'user', 'content': text.strip()}],
            # The same context size as chat: a different one makes Ollama reload the model, which takes minutes here.
            'options': {'temperature': 0, 'num_ctx': 4096, 'num_predict': 90},
        }, 8192, 60)
        return command(json.loads(result['message']['content']), text)
    except Exception:
        return None


# --- Second chance: June never tells the person she can't do something she can --------------------------------
REFUSAL = re.compile(r"^\W*(?:(?:sorry|unfortunately|hmm|oh)[,.!]?\s*)*(?:but\s+)?(?:i\s*(?:can['’]?t|cannot|am\s+(?:not\s+able|unable)\s+to|['’]m\s+(?:not\s+able|unable)\s+to|"
                     r"don['’]?t\s+have\s+(?:the\s+)?(?:ability|access|tools?)|do\s+not\s+have\s+(?:the\s+)?(?:ability|access|tools?))|as\s+an\s+ai|that['’]?s\s+not\s+something\s+i\s+can)"
                     r"[^.!?\n]{0,80}?\b(?:create|build|make|design|generate|open|launch|play|pause|set|add|schedule|remind|send|publish|host|deploy|access|control|run|"
                     r"push|commit|start|stop|convert|change|restyle|show|apply|submit|take\s+down|undo)\b", re.I)
_HINTS = (
    (_FILES, 'make that for you', '“make a website about a coffee shop in a dark style”, “make a presentation about solar power” or “write a Word document about my plan”'),
    (re.compile(r'\b(?:style|design|look|colou?rs?|theme|fonts?|darker|lighter)\b', re.I), 'change the look of what I just made', '“make it in a different style” or “redo it in dark”'),
    (re.compile(r'\b(?:publish|online|live|deploy|github\s+pages)\b', re.I), 'put a website I made online', '“publish it”'),
    (re.compile(r'\b(?:calendar|event|meeting|appointment|schedule)\b', re.I), 'add that to your calendar', '“add an event tomorrow at 5 pm called Dentist”'),
    (re.compile(r'\bremind', re.I), 'set that reminder', '“remind me tomorrow at 6 pm to stretch”'),
    (re.compile(r'\b(?:timer|alarm|count\s*down)\b', re.I), 'set that timer', '“set a timer for 10 minutes”'),
    (re.compile(r'\b(?:music|song|play|playlist|album|artist)\b', re.I), 'play that', '“play some music” or “play Imagine Dragons”'),
    (re.compile(r'\b(?:git|github|push|pull|commit|tests?|build|repo)\b', re.I), 'run that in your project', '“run the tests in June” or “push my changes with message Fix the menu”'),
    (re.compile(r'\b(?:e-?mails?|inbox|mail)\b', re.I), 'handle your email', '“check my email”, “read the latest email from Rahul” or “send an email to name@example.com about …”'),
    (re.compile(r'\b(?:naukri|jobs?|appl(?:y|ied|ication)|recruiters?)\b', re.I), 'help with Naukri jobs', '“find me jobs on Naukri”, “apply to the top 3” or “what jobs did I apply to”'),
    (re.compile(r'\b(?:open|launch|app)\b', re.I), 'open that', '“open Chrome” or “open Figma and Notes”'),
)


def watch_for_refusal(question):
    """Whether June should hold back the start of a general reply to check it is not a wrong refusal."""
    return isinstance(question, str) and bool(DOMAIN.search(question)) and not _KNOWLEDGE.match(question) and not nonliteral_request(question)


def wrong_refusal(question, opening):
    """A short clarification to show instead of a reply that refuses something June can do, else None."""
    if not watch_for_refusal(question) or not isinstance(opening, str) or not REFUSAL.search(opening[:240]):
        return None
    for pattern, what, example in _HINTS:
        if pattern.search(question):
            return f'I can {what}, but I didn’t catch it as a request. Say it like this: {example}.'
    return 'I may be able to do that, but I didn’t catch it as a request. Say what you want in a few words, for example “open Chrome”, “make a website about …” or “set a timer for 10 minutes”.'
