"""Truth owned by the application, not guessed by its language model.

Replies are explicitly labelled and persisted with that label. No fabricated
model output, provider fallback, purchase or web lookup is implied.
"""
import re

PREFIX = 'June app information:\n'
CONFIRMATION = re.compile(r'\s*(?:are you sure(?: about that)?|is that (?:right|correct|true)|really)\s*[?.!]*\s*', re.I)


# One application-owned capability description is also supplied to inference.
CONNECTED_CAPABILITIES = (
    'I can chat, explain topics, help with code, draft text, plan from information you share, '
    'and offer everyday advice, including clothing suggestions. The voice interface is available; '
    'persistent chats can suggest facts for your approval in Memory. '
    'Web browsing, accounts, calendars, reminders, bookings, purchasing, payments and device control '
    'are not connected to June. I can draft instructions or messages for you to use yourself.'
)


def nonliteral_request(query):
    """Quoted examples and fictional/instruction prose are model tasks, not app commands."""
    return bool(re.search(
        r'["“”`]|(?:^|\s)[\'‘]|\b(?:fictional|pretend|role.?play|hypothetical|imagine|'
        r'ignore|disregard|override)\b|\b(?:said|says|wrote|writes|example|quote|transcript|message|email|text)\s*:|\bfor (?:a |an )?(?:story|exercise|scenario)\b|'
        r'^\s*(?:translate|explain (?:the )?(?:phrase|sentence)|quote|rewrite|summari[sz]e)\b',
        query, re.I))


def request_words(query):
    q = re.sub(r"what['’]s\b", 'what is', query.lower())
    q = re.sub(r'[^\w\s]', ' ', q)
    q = re.sub(r'\s+', ' ', q).strip()
    return re.sub(r'^(?:(?:okay|ok|so|please|just|hi|hello|hey june|june|but|and|well|uh|um|now|alright|wait|stop|hold on|hang on|actually|sorry)\s+)+', '', q)


def _single_recall_field(query):
    """Recognise direct recall, including spoken false starts, without routing quotations."""
    if nonliteral_request(query):
        return None
    q = request_words(query)
    q = re.sub(r'\bmy (?:approved|saved) (?=(?:name|age|location|city|gender|project|favo(?:u)?rite colou?r)\b)', 'my ', q)
    if re.fullmatch(r'(?:what (?:else |details )?do you (?:know|remember) about me|what (?:are )?my (?:saved|approved) (?:details|facts|memories)|(?:do you )?have (?:any |other |any other )?(?:saved |approved )?(?:details|information|facts) (?:of mine|about me))', q):
        return 'details'
    subject = r'my (?:name|age|location|city|project|gender|favo(?:u)?rite colou?r)'
    # A spoken acknowledgement can precede the actual recall request.
    q = re.sub(r'^you (?:do )?know (?:what )?' + subject + r'(?: is)? right (?:so )?', '', q)
    if re.fullmatch(r'(?:how do you know (?:that|this)|where did you get (?:that|this)(?: from)?|what is (?:your|the) source)', q):
        return 'source'
    q = re.sub(r'^(?:how do you know |where did you get |what is the source of )', '', q)
    q = re.sub(r' from$', '', q)
    q = re.sub(r'^(?:(?:(?:can|could|will|would|do) you )(?:tell me )?(?:just |still )?|tell me (?:one thing )?|remind me (?:of )?|remember |know )+', '', q)
    q = re.sub(r'^(?:what is |what |where is )', '', q)
    q = re.sub(r' is$', '', q)
    fields = {
        'name': r'my name', 'color': r'my favo(?:u)?rite colou?r', 'age': r'my age|how old am i',
        'location': r'my (?:location|city)|(?:my )?(?:place )?where (?:do )?i live',
        'project': r'my project', 'work': r'where (?:do )?i work',
        'gender': r'my gender|am i (?:a )?(?:boy|man|male) or (?:a )?(?:girl|woman|female)|(?:if )?i (?:am|m) (?:a )?(?:boy|man|male) or (?:a )?(?:girl|woman|female)',
        'details': (r'(?:what (?:else )?(?:do you )?)?(?:know|remember)(?: about me)?|'
                    r'what (?:else )?do you (?:know|remember) about me|'
                    r'(?:list|show|tell me)(?: all)? (?:my )?(?:saved|approved) (?:details|facts|memories)|'
                    r'what (?:are )?my (?:saved|approved) (?:details|facts|memories)|'
                    r'(?:have other details like my name or anything else )?'
                    r'(?:do you )?have (?:any |other |any other )?(?:details|information|facts) (?:of mine|about me)')
    }
    # The standard prefix removal leaves "about me" for do-you-remember wording.
    if q == 'about me':
        return 'details'
    for field, pattern in fields.items():
        if re.fullmatch(pattern, q):
            return field
    return None


SOURCE_REASON = re.compile(
    r'\s+(?:and|plus)\s+explain (?:how you (?:came|come) to (?:that|this|the) conclusion|how you know (?:that|this))$',re.I)


def recall_requests_source(query):
    q=request_words(query)
    return bool(SOURCE_REASON.search(q) or re.match(r'^(?:how do you know|where did you get|what is (?:your|the) source)',q))


def memory_check_followup(query):
    if nonliteral_request(query):return False
    q=request_words(query)
    return bool(re.fullmatch(
        r'(?:it s|it is|that s|that is) in my (?:saved |approved )?memory (?:please )?(?:check|read) (?:it|that)(?: and)? (?:tell|remind) me|'
        r'(?:check|read) my (?:saved |approved )?memory(?: and)? (?:tell|remind) me',q))


def recall_fields(query):
    """Parse a list of complete personal-recall clauses, not arbitrary keywords.

    Commas, conjunctions and a source explanation can join known fields.
    Every substantive clause must parse; unrelated drafting/explanation tasks
    and quoted scenarios still use the ordinary model path.
    """
    if nonliteral_request(query):return ()
    single=_single_recall_field(query)
    if single:return (single,)
    q=request_words(re.sub(r',\s*(?:and\s+)?',' and ',query,flags=re.I))
    q=SOURCE_REASON.sub('',q)
    q=re.sub(r'^(?:i (?:want|would like) to know|what are)\s+','',q)
    clauses=[c for c in re.split(r'\s+(?:(?:and|also|plus)\s+)+',q) if c]
    if not 1<=len(clauses)<=7:return ()
    fields=[]
    for i,clause in enumerate(clauses):
        field=_single_recall_field(clause)
        if field is None and i:field=_single_recall_field('my '+clause)
        if field is None or field in ('details','source'):return ()
        if field not in fields:fields.append(field)
    return tuple(fields)


def recall_field(query):
    fields = recall_fields(query)
    return fields[0] if len(fields) == 1 else 'multiple' if fields else None


def personal_recall(query):
    return memory_check_followup(query) or recall_field(query) is not None


def recall_query_for_turn(messages):
    """Resolve explicit memory checks back to the immediately referenced request.

    A prior incorrect model denial is not authoritative about stored data.
    Stop at a new topic rather than disclosing facts from an older question.
    """
    index=len(messages)-1
    while index>=0:
        query=messages[index]['content']
        check=memory_check_followup(query)
        source=recall_field(query)=='source'
        if not check and not source:break
        if index<2:return None
        if source and not messages[index-1]['content'].startswith('Saved memory:\n'):return None
        previous=messages[index-2]['content']
        if check and not (recall_fields(previous) or memory_check_followup(previous)):return None
        index-=2
    return messages[index]['content'] if index>=0 else None


def recall_field_for_turn(messages):
    query = recall_query_for_turn(messages)
    return recall_field(query) if query is not None else None


def fact_fields(value):
    """Classify explicit saved clauses, never infer identity from a name or age."""
    value = value.strip().rstrip('.!?')
    value = re.sub(r"\bi['’]m\b", 'I am', value, flags=re.I)
    value = re.sub(r"\bmy name['’]s\b", 'My name is', value, flags=re.I)
    patterns = {
        'name': r'my name is [^\n]+',
        'color': r'my favo(?:u)?rite colou?r is [^\n]+',
        'age': (r'my age is [^\n]+|i am (?:a |an )?\d{1,3}'
                r'(?:[ -]years?[ -]old| years of age)?'
                r'(?: (?:man|woman|guy|boy|girl|male|female|non[ -]?binary))?'),
        'location': r'(?:my (?:location|city) is|i live in|i am based in) [^\n]+',
        'project': r'my project is [^\n]+',
        'work': r'i work (?:at|in|as) [^\n]+',
        'gender': (r'my gender is [^\n]+|i (?:am|identify as) (?:a |an )?'
                   r'(?:\d{1,3}[ -](?:year|years)[ -]old[ -])?'
                   r'(?:man|woman|guy|boy|girl|male|female|non[ -]?binary|agender|genderfluid)')
    }
    return {field for field, pattern in patterns.items() if re.fullmatch(pattern, value, re.I)}


def application_reply(model, query, memory_enabled):
    if nonliteral_request(query):
        return None
    q = re.sub(r'^(?:(?:okay|ok|so|please|hey june|june)[\s,!.:]*)+', '', query.strip(), flags=re.I)
    if re.fullmatch(r"(?:tell me (?:something |a bit |more )?about (?:you|yourself)|who are you|what can you do(?: for me| today| right now)?|what can you help me with|how can you help me|what are your capabilities|what (?:model|AI) (?:are you(?: using)?|do you use)|who (?:made|created|built) you|are you (?:another|a different) (?:AI|assistant|chatbot))[\s?.!]*", q, re.I):
        return PREFIX + f'I’m June, your locally built assistant, running {model} on this Mac. ' + CONNECTED_CAPABILITIES
    if not personal_recall(q) and re.match(r'(?:can you |could you |would you )?(?:set (?:a |an )?(?:reminder|alarm)|remind me|open (?:my |the )?calendar|(?:check|update|access) my calendar|browse (?:the )?(?:web|internet)|search (?:the )?(?:web|internet))\b', q, re.I):
        return PREFIX + CONNECTED_CAPABILITIES
    recall = personal_recall(q)
    if not recall and (re.search(r'\b(?:can|will) you\b.*\bremember\b', q, re.I)
            or re.match(r'(?:how (?:does|do) (?:your |June.?s )?memory work|do you have (?:a )?(?:memory|saved memories))\b', q, re.I)):
        # Recall questions such as "do you remember where I live" stay model
        # requests supplied with real approved facts and recent user context.
        if not memory_enabled:
            return PREFIX + 'Saved memory is not enabled for this request. In a persistent June chat, Memory lets you review and approve facts; this request does not save them.'
        return PREFIX + 'I can suggest facts in Memory, but a fact becomes long-term memory only after you approve it. Saved chats stay on this Mac for 30 days and only recent messages fit the model’s context; approved memories persist until you edit or delete them.'
    if re.match(r'(?:can you |could you |would you )?(?:order|buy|purchase)\s+(?!of\b)', q, re.I) and not re.search(r'\b(?:numbers?|array|sort|ascending|descending|alphabetical|alphabetically)\b', q, re.I):
        return PREFIX + 'I can help you make a shopping list or draft an order, but June is not connected to checkout or payment services yet. I have not placed or paid for anything.'
    if re.match(r'(?:can you |could you |would you )?book\b.*\b(?:tickets?|movie|flights?|hotels?|appointment)\b', q, re.I):
        return PREFIX + 'I can help plan the details, but booking and payment services are not connected to June yet. I cannot check live availability, reserve a ticket or make a payment.'
    hardware = re.search(r'\b(?:gpus?|graphics cards?|cpus?|processors?|pcs?|computers?|laptops?)\b',q,re.I)
    shopping = re.search(r'\b(?:best|recommend\w*|buy|purchase)\b',q,re.I)
    supplied = re.search(r'\b(?:these|following|provided|supplied|listed)\b',q,re.I)
    if hardware and shopping and not supplied:
        return PREFIX + 'I can help compare hardware, but June has no live product or price lookup connected, so I cannot verify the best current purchase. Share a dated shortlist with prices and your workload, and I can compare the information you provide.'
    if re.search(r'\bgdp\b', q, re.I) and re.search(r'\b(?:top|highest|largest|most|rank(?:ing)? (?:of |the )?countries)\b', q, re.I):
        if re.search(r'\b(?:19|20)\d{2}\b', q) and re.search(r'\b(?:nominal|PPP|purchasing.power)\b', q, re.I):
            return PREFIX + 'The year and metric are specified, but I still need a dated source to verify the ranking. June has no web lookup connected; share the relevant dataset or figures for me to interpret.'
        if re.search(r'\bper capita\b', q, re.I):
            return PREFIX + 'I cannot verify that ranking from a dated dataset in this version of June. Do you want nominal or purchasing-power-adjusted GDP per capita, and for which year? You can share a dated source for me to interpret.'
        return PREFIX + 'I cannot verify a current GDP ranking without a dated source. The result also depends on whether you mean nominal GDP or purchasing-power-adjusted GDP; share the year and source you want to compare.'
    return None


def application_reply_for_turn(model, messages, memory_enabled):
    latest = messages[-1]['content'] if messages else ''
    answer = application_reply(model, latest, memory_enabled)
    if answer is not None:
        return answer
    if (len(messages) >= 3 and messages[-2]['role'] == 'assistant'
            and messages[-2]['content'].startswith(PREFIX) and CONFIRMATION.fullmatch(latest)):
        return application_reply(model,messages[-3]['content'],memory_enabled) or messages[-2]['content']
    # A short clarification of our own ranking question must not be treated as
    # permission to invent a dataset. A new topic or supplied prose uses the model.
    if (len(messages) >= 3 and messages[-2]['role'] == 'assistant'
            and messages[-2]['content'].startswith(PREFIX)
            and re.search(r'\b(?:GDP|ranking)\b', messages[-2]['content'], re.I)
            and re.fullmatch(r'[\s,.]*(?:(?:19|20)\d{2}|nominal|PPP|purchasing[ -]power(?:[ -]adjusted)?|and|for|in|please|yes|no|[\s,.])+[\s,.!?]*', latest, re.I)):
        return PREFIX + 'I still need a dated source to verify that ranking. June has no web lookup connected; share the relevant dataset or figures for me to interpret.'
    return None
