"""Conservative transcript cleanup and a narrow model-identity streaming guard.

These safeguards do not guess what an ambiguous number was meant to be and do
not establish current product facts. Unfamiliar products stay unfamiliar.
"""
import re

DIGITS = dict(zip('zero one two three four five six seven eight nine'.split(), '0123456789'))
DIGIT_SEQUENCE = re.compile(r'\b(?:' + '|'.join(DIGITS) + r')(?:\s+(?:' + '|'.join(DIGITS) + r')){2,}\b', re.I)
NOISE = r'(?:cough(?:ing)?|clears?\s+throat|throat\s+clearing|music|silence|blank[_ ]audio|breathing|noise|inaudible|laughter)'
ANNOTATION = re.compile(r'(?:\*\s*' + NOISE + r'\s*\*|\[\s*' + NOISE + r'\s*\]|\(\s*' + NOISE + r'\s*\))', re.I)
MODEL_ID = re.compile(r'\b(?:(RTX|GTX|RX)\s*)?(\d{4})(?!\d)(?:\s*(Ti(?:\s+Super)?|Super|XTX|XT))?\b', re.I)


def clean_transcript(text):
    text = ANNOTATION.sub('', text)
    text = DIGIT_SEQUENCE.sub(lambda match: ''.join(DIGITS[word.lower()] for word in match.group().split()), text)
    text = ' '.join(text.split())
    return text if any(character.isalnum() for character in text) else ''


def model_ids(text, explicit=False):
    found = set()
    for match in MODEL_ID.finditer(text):
        prefix, number, suffix = match.groups()
        if not explicit or prefix or suffix:
            found.add((number, ' '.join((suffix or '').lower().split())))
    return found


def model_label(identity):
    number, suffix = identity
    return number + (' ' + {'ti': 'Ti', 'super': 'Super', 'ti super': 'Ti Super', 'xt': 'XT', 'xtx': 'XTX'}[suffix] if suffix else '')


class ReplyIdentityGuard:
    """Delay GPU sentences until their stated model identity can be checked.

    A sentence explicitly comparing cards is allowed. A sentence substituting
    another GPU for the latest requested one becomes an honest clarification.
    Other chats retain their original delta chunks without extra buffering.
    """
    def __init__(self, messages):
        latest = messages[-1]['content'] if messages else ''
        context = ' '.join(item['content'] for item in messages)
        self.focus = set()
        if re.search(r'\b(?:GPU|graphics? cards?|RTX|GTX|Radeon|GeForce|Nvidia)\b', context, re.I):
            # A price or year elsewhere in a GPU conversation is not a model.
            for pattern in (r'\b(?:RTX|GTX|RX)\s*(\d{4})(?!\d)',
                            r'(?<!\d)(\d{4})\s*(?:Ti|Super|XT|XTX)\b',
                            r'\b(?:about|meant|mean|said|saying|model|GPU|card)\s+(?:the\s+|is\s+)?(\d{4})(?!\d)',
                            r'^\s*(\d{4})\s*[.!?]?\s*$'):
                self.focus.update(re.findall(pattern, latest, re.I))
            self.focus = {identity for identity in model_ids(latest) if identity[0] in self.focus}
            excluded = set()
            for negative in re.finditer(r'\bnot\s+(?:the\s+)?(?:(?:RTX|GTX|RX)\s*)?\d{4}(?!\d)(?:\s*(?:Ti(?:\s+Super)?|Super|XTX|XT))?\b', latest, re.I):
                excluded.update(model_ids(negative.group()))
            self.focus.difference_update(excluded)
            # Bare numbers inherit GPU context only within a connected list
            # containing an already identified card, in either list order.
            groups, end = [], None
            for match in MODEL_ID.finditer(latest):
                if end is None or not re.fullmatch(r'\s*(?:,\s*(?:(?:and|or)\s+)?|(?:and|or|vs\.?|versus)\s+|/\s*)(?:the\s+)?', latest[end:match.start()], re.I):
                    groups.append(set())
                prefix, number, suffix = match.groups()
                if not (prefix or suffix) and (
                        re.fullmatch(r'(?:19|20)\d{2}', number)
                        or re.match(r'\s*(?:rupees|dollars|euros|pounds|INR|USD|EUR|GBP|prices?|budget|Rs)\b', latest[match.end():], re.I)):
                    end = None
                    continue
                groups[-1].update(model_ids(match.group()))
                end = match.end()
            for group in groups:
                group.difference_update(excluded)
                if group.intersection(self.focus):
                    self.focus.update(group)
        self.buffer = ''
        self.rejected = False

    def check(self, sentence):
        identities = model_ids(sentence, explicit=True)
        if identities and not identities.intersection(self.focus):
            self.rejected = True
            target = ', '.join(model_label(identity) for identity in sorted(self.focus))
            return f'You asked about {target}. I cannot verify its specifications or current price, so I should not substitute a different graphics card.'
        return sentence

    def push(self, text):
        if not self.focus: return [text]
        if self.rejected: return []
        self.buffer += text
        output = []
        while match := re.search(r'[.!?]\s+|\n', self.buffer):
            boundary = match.end()
            sentence, self.buffer = self.buffer[:boundary], self.buffer[boundary:]
            output.append(self.check(sentence))
            if self.rejected:
                self.buffer = ''
                break
        # The model is limited to short replies. Keep even malformed, unbroken
        # output bounded; validate it before releasing a larger fragment.
        if len(self.buffer) > 2048 and not self.rejected:
            output.append(self.check(self.buffer)); self.buffer = ''
        return output

    def finish(self):
        if not self.buffer or self.rejected: return []
        text, self.buffer = self.buffer, ''
        return [self.check(text)]


class RepetitionGuard:
    """Stop unrequested loops across stream chunks, without retracting sent text.

    Keep a bounded suffix for checking word/phrase and joined-character loops.
    Explicit repetition/copy tasks bypass this guard, not other validation.
    """
    def __init__(self, messages):
        latest = messages[-1]['content'] if messages else ''
        request = re.sub(r'^\s*(?:(?:please|okay|ok|so)[\s,.!]+)*(?:(?:can|could|would|will) you\s+)?', '', latest, flags=re.I)
        self.allowed = bool(re.match(r'(?:repeat|copy|quote|transcribe|recite)\b', request, re.I)
                            or (re.match(r'(?:say|write|print|output|give|list)\b', request, re.I)
                                and re.search(r'\b(?:verbatim|repeatedly|twice|thrice|(?:\d+|\w+) times)\b', request, re.I)))
        self.tail = ''
        self.stopped = False

    def push(self, text):
        if self.stopped:
            return ''
        if self.allowed:
            return text
        combined = self.tail + text
        previous = len(self.tail)
        tokens = []
        boundary = None
        # Scan each new word once. Retokenise only the bounded old suffix so
        # words split across model chunks are recognised without double counts.
        for match in re.finditer(r'\w+', combined.casefold()):
            word = match.group()
            tokens.append(word)
            tokens = tokens[-96:]
            if match.end() <= previous:
                continue
            for width in range(1, min(12, len(tokens) // 4) + 1):
                count = max(4, (12 + width - 1) // width)
                if len(tokens) >= width * count and tokens[-width:] * count == tokens[-width * count:]:
                    boundary = match.end()
                    break
            # Joined loops need no whitespace. Bound regex work per window,
            # overlapping enough to detect an eight-copy, 24-character unit.
            for offset in range(max(0, previous - match.start() - 192), len(word), 256):
                start = max(0, offset - 192)
                joined = re.search(r'(\w{2,24})\1{7,}', word[start:offset + 256])
                if joined:
                    end = match.start() + start + joined.end()
                    boundary = min(boundary, end) if boundary else end
                    break
            if boundary is not None:
                break
        if boundary is not None:
            self.stopped = True
            # Never retract old deltas, and do not release the looping suffix
            # from this frame. The completion flag lets the caller stop speech.
            return text[:max(0, boundary - previous - 1)]
        self.tail = combined[-2048:]
        return text
