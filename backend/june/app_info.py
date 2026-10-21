"""Truth owned by the application, not guessed by its language model.

Replies are explicitly labelled and persisted with that label. No fabricated
model output, provider fallback, purchase or web lookup is implied.
"""
import re

PREFIX = 'June app information:\n'
CONFIRMATION = re.compile(r'\s*(?:are you sure(?: about that)?|is that (?:right|correct|true)|really)\s*[?.!]*\s*', re.I)


def personal_recall(query):
    """Recognise recall, including spoken false starts, not future save requests."""
    q = re.sub(r'[^\w\s]', ' ', query.lower())
    q = re.sub(r'\s+', ' ', q).strip()
    q = re.sub(r'^(?:(?:okay|ok|so|please|hey june|june)\s+)+', '', q)
    subject = r'(?:my (?:name|age|location|city|project|favo(?:u)?rite colou?r)(?: is)?|where i (?:live|work))'
    return bool(re.fullmatch(
        r'(?:(?:(?:can|could|will|would|do) you(?: tell me)? )+(?:still )?remember (?:what )?'
        + subject + r'|what is my (?:name|age|location|city|project|favo(?:u)?rite colou?r))', q))


def application_reply(model, query, memory_enabled):
    q = re.sub(r'^(?:(?:okay|ok|so|please|hey june|june)[\s,!.:]*)+', '', query.strip(), flags=re.I)
    if re.fullmatch(r"(?:tell me (?:something |a bit |more )?about (?:you|yourself)|who are you|what can you do(?: for me| today| right now)?|what (?:model|AI) (?:are you(?: using)?|do you use)|who (?:made|created|built) you|are you (?:Claude|ChatGPT))[\s?.!]*", q, re.I):
        return PREFIX + f'I’m June, your locally built assistant, running {model} on this Mac. I can chat, use the voice interface and suggest memories for your approval; browsing, purchasing, payments and device control are not connected yet.'
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
