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
