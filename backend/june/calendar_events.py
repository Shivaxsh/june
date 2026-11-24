"""Turn "add an event tomorrow at 5 pm called Dentist" into one exact event, or one question.

Nothing here touches Calendar. The parsed event becomes a plan the person reviews.
"""
from datetime import date, datetime, timedelta
import re
from zoneinfo import ZoneInfo

from .errors import JuneError
from .reminders import local_timestamp
from .timers import number

_LEAD = (r"\s*(?:(?:ok(?:ay)?|so|now|and|well|um|uh|oh)[,\s]+)*(?:(?:hey\s+)?june[,!:\s]+)?"
         r"(?:(?:can|could|would|will)\s+you\s+|i\s+(?:want|need)\s+(?:you\s+)?to\s+|i['’]d\s+like\s+(?:you\s+)?to\s+)?(?:please\s+)?")
_REQUEST = re.compile(_LEAD + r"(?P<verb>add|create|schedule|put|make|set\s+up)\s+(?P<rest>.+?)(?:\s+please)?[\s.!]*", re.I | re.S)
_KIND = r"(?:event|meeting|appointment|call)"
_ON_CALENDAR = r"\b(?:to|on|in|into)\s+(?:my|the)\s+calendar\b"
_OBJECT = re.compile(r"(?:an?\s+|the\s+|my\s+)?(?:new\s+)?(?:all[- ]day\s+)?(?:calendar\s+)?" + _KIND + r"\b", re.I)
_NOT_AN_EVENT = re.compile(r"\b(?:listener|handler|loop|script|function|code|python|javascript|agenda|notes?|minutes of|list|template|invite email)\b", re.I)
_DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
_MONTHS = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december']
_MONTH = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_CLOCK = r"(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?"
EXAMPLE = 'For example: add an event tomorrow at 5 PM called Dentist.'


def _take(pattern, text):
    """(match, text without it) for the first match, else (None, text)."""
    match = re.search(pattern, text, re.I)
    if not match:
        return None, text
    return match, (text[:match.start()] + ' ' + text[match.end():])


def _hour(hour, minute, period, evening=False):
    """(hour, minute) in 24-hour time, 'ask' when AM/PM is missing, or None when invalid."""
    h, m = int(hour), int(minute or 0)
    if period:
        if not 1 <= h <= 12:
            return None
        h = h % 12 + (12 if period.lower().startswith('p') else 0)
    elif h <= 12 and minute is None:
        if not evening:
            return 'ask'
        h = h % 12 + 12
    return (h, m) if 0 <= h <= 23 and 0 <= m <= 59 else None


def event_request(text, now, where):
    """dict(title, start, end, allDay) | dict(ask=...) | None when the words are not a request to add an event."""
    if not isinstance(text, str) or len(text) > 300 or '?' in text and re.match(r"\s*(?:how|what|why|when|where|which|who|should|is|are|do|does|did)\b", text, re.I):
        return None
    if re.search(r"\b(?:do not|don['’]?t|never)\b", text, re.I):
        return None
    request = _REQUEST.fullmatch(text)
    if not request:
        return None
    rest, verb = request['rest'], request['verb'].lower()
    on_calendar = re.search(_ON_CALENDAR, rest, re.I)
    if _NOT_AN_EVENT.search(rest) or not (on_calendar or _OBJECT.match(rest) and (verb != 'make' or re.search(r"\bcalled\b|\bat\s+\d", rest, re.I))):
        return None
    if on_calendar:
        rest = rest[:on_calendar.start()] + ' ' + rest[on_calendar.end():]
    zone = ZoneInfo(where)
    today = datetime.fromtimestamp(now, zone).date()

    all_day, rest = _take(r"\ball[- ]day\b", rest)
    length, rest = _take(r"\bfor\s+(half\s+an|an?|\d+|[a-z]+(?:[- ][a-z]+)?)\s*(hours?|hrs?|minutes?|mins?)\b", rest)
    minutes = 60
    if length:
        count = 0.5 if length[1].lower().startswith('half') else number(length[1].lower())
        if count is None:
            return dict(ask='How long should the event be? ' + EXAMPLE)
        minutes = round(count * (60 if length[2].lower().startswith('h') else 1))
        if not 5 <= minutes <= 24 * 60:
            return dict(ask='Choose a length from 5 minutes to 24 hours. Nothing was prepared.')

    day, evening = None, False
    found, rest = _take(r"\b(?:on\s+)?(\d{4})-(\d{2})-(\d{2})\b", rest)
    if found:
        try:
            day = date(int(found[1]), int(found[2]), int(found[3]))
        except ValueError:
            return dict(ask='That date is not valid. ' + EXAMPLE)
    if day is None:
        found, rest = _take(r"\b(?:the\s+)?day\s+after\s+tomorrow\b", rest)
        if found: day = today + timedelta(days=2)
    if day is None:
        found, rest = _take(r"\b(today|tomorrow|tonight|this\s+evening)\b", rest)
        if found:
            word = found[1].lower()
            day = today + timedelta(days=1 if word == 'tomorrow' else 0)
            evening = word != 'today' and word != 'tomorrow'
    if day is None:
        found, rest = _take(r"\b(?:on\s+)?(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?" + _MONTH + r"\b", rest)
        other = None
        if not found:
            other, rest = _take(r"\b(?:on\s+)?" + _MONTH + r"\s+(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?\b", rest)
        if found or other:
            number_of_day, name = (int(found[1]), found[2]) if found else (int(other[2]), other[1])
            month = next(i + 1 for i, full in enumerate(_MONTHS) if full.startswith(name.lower()[:3]))
            try:
                day = date(today.year, month, number_of_day)
                if day < today: day = date(today.year + 1, month, number_of_day)
            except ValueError:
                return dict(ask='That date is not valid. ' + EXAMPLE)
    if day is None:
        found, rest = _take(r"\b(?:on\s+|this\s+|next\s+|coming\s+)?(" + '|'.join(_DAYS) + r")\b", rest)
        if found:
            ahead = (_DAYS.index(found[1].lower()) - today.weekday()) % 7 or 7
            day = today + timedelta(days=ahead)

    start_clock = end_clock = None
    found, rest = _take(r"\b(?:at|from)\s+(noon|midday|midnight)\b", rest)
    if found:
        start_clock = (0, 0) if found[1].lower() == 'midnight' else (12, 0)
    else:
        found, rest = _take(r"\b(?:at|from)\s+" + _CLOCK + r"(?:\s*o['’]?clock)?(?:\s*(?:to|till|until|-)\s*" + _CLOCK + r")?(?!\w)", rest)
        if not found:
            found, rest = _take(r"\b(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)(?:\s*(?:to|till|until|-)\s*" + _CLOCK + r")?(?!\w)", rest)
        if found:
            start_clock = _hour(found[1], found[2], found[3], evening)
            if found[4]:
                # "2 to 3 pm": the start takes the end's AM/PM when it has none.
                end_clock = _hour(found[4], found[5], found[6] or found[3], evening)
                if start_clock == 'ask' and found[6]:
                    start_clock = _hour(found[1], found[2], found[6])
            if start_clock == 'ask' or end_clock == 'ask':
                return dict(ask='Do you mean AM or PM? Nothing was prepared. ' + EXAMPLE)
            if start_clock is None or found[4] and end_clock is None:
                return dict(ask='That time is not valid. ' + EXAMPLE)

    named, rest = _take(r"\b(?:called|named|titled)\s+(.+)$", rest)
    title = named[1] if named else re.sub(r"^\s*(?:an?|the|my)\s+", '', re.sub(r"\s+", ' ', rest).strip(), flags=re.I)
    title = re.sub(r"^(?:new\s+)?(?:calendar\s+)?event\b\s*(?:for\s+|about\s+|with\s+)?", '', title, flags=re.I) if not named else title
    title = re.sub(r"\s+", ' ', title).strip(" \t.,;:!\"“”'‘")
    title = re.sub(r"\s+(?:on|at|for|from)$", '', title, flags=re.I)
    if not title or len(title) > 120 or re.search(r'[\x00-\x1f\x7f]', title):
        return dict(ask='What should I call it? ' + EXAMPLE)
    title = title[0].upper() + title[1:]

    try:
        if all_day:
            day = day or today
            start = local_timestamp(day.isoformat(), '00:00', where)
            end = local_timestamp((day + timedelta(days=1)).isoformat(), '00:00', where)
            if day < today:
                return dict(ask='That day has already passed. Nothing was prepared.')
        else:
            if start_clock is None:
                return dict(ask='What time? Say the full request again with a time, or say “all day”. ' + EXAMPLE)
            clock = f'{start_clock[0]:02}:{start_clock[1]:02}'
            first = day or today
            start = local_timestamp(first.isoformat(), clock, where)
            if day is None and start <= now:
                start = local_timestamp((today + timedelta(days=1)).isoformat(), clock, where)
            if start <= now:
                return dict(ask='That time has already passed. Nothing was prepared.')
            if end_clock:
                end = local_timestamp(datetime.fromtimestamp(start, zone).date().isoformat(), f'{end_clock[0]:02}:{end_clock[1]:02}', where)
                if end <= start:
                    return dict(ask='The end time must be after the start time. Nothing was prepared.')
            else:
                end = start + minutes * 60
    except JuneError:
        return dict(ask='That date or time is not valid. ' + EXAMPLE)
    if start - now > 366 * 86400:
        return dict(ask='Choose a date within a year. Nothing was prepared.')
    return dict(title=title, start=float(start), end=float(end), allDay=bool(all_day))


def valid_event(value, now):
    """The exact shape a plan may carry. No calendar name, notes, guests or location."""
    return (isinstance(value, dict) and set(value) == {'title', 'start', 'end', 'allDay'}
            and isinstance(value['title'], str) and 1 <= len(value['title'].strip()) <= 120 and not re.search(r'[\x00-\x1f\x7f]', value['title'])
            and type(value['allDay']) is bool and all(type(value[k]) in (int, float) for k in ('start', 'end'))
            and (value['start'] > now - 300 or value['allDay'] and value['start'] > now - 86400) and value['start'] - now <= 366 * 86400
            and 0 < value['end'] - value['start'] <= 7 * 86400)


def when_phrase(event, where):
    zone = ZoneInfo(where)
    start = datetime.fromtimestamp(event['start'], zone)
    day = start.strftime('%a ') + str(start.day) + start.strftime(' %b %Y')
    if event['allDay']:
        return day + ', all day'
    clock = lambda moment: moment.strftime('%I:%M %p').lstrip('0')
    return f"{day} at {clock(start)} to {clock(datetime.fromtimestamp(event['end'], zone))}"
