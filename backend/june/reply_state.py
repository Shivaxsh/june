"""Application-owned completeness, never a model claim of code correctness."""
import re

CONTINUE = re.compile(r'\s*(?:please\s+)?(?:continue|go on|carry on|keep going)(?:\s+please)?[.!?\s]*',re.I)
CHECK_COMPLETE = re.compile(r'\b(?:complete|finished|done|enough)\b',re.I)
FENCE = re.compile(r'^ {0,3}(`{3,}|~{3,})(.*)$',re.M)
COMPLETENESS_NOTICE = ('The previous reply was cut off or has an unfinished code block. '
    'I cannot call it complete or verified. Continue it before using it, then check the assembled result.')


def open_fence(text):
    marker=None
    for match in FENCE.finditer(text):
        run,tail=match.groups()
        if marker is None:
            marker=run
        elif run[0]==marker[0] and len(run)>=len(marker) and not tail.strip():
            marker=None
    return marker is not None


def output_state(reply, limited=False):
    return {'limited':bool(limited),'incomplete':bool(limited or open_fence(reply))}


def resumable_turn(turns, revision):
    if any(t['status']=='pending' for t in turns):
        return None
    latest=next((t for t in reversed(turns) if t['status']=='complete' and t['assistant']!=COMPLETENESS_NOTICE),None)
    if (latest and latest['revision']==revision and latest.get('provenance') in ('general','memory')
            and (latest.get('limited') or latest.get('incomplete'))):
        return latest['id']
    return None


def completeness_reply(question,turns):
    superseded={t.get('continuedFrom') for t in turns if t['status']=='complete' and t.get('continuedFrom')}
    latest=next((t for t in reversed(turns) if t['status']=='complete'
                 and t['id'] not in superseded and (t.get('limited') or t.get('incomplete'))),None)
    if not latest or not (latest.get('limited') or latest.get('incomplete')):
        return None
    asks_status = re.match(r'\s*(?:is|are|was|were|has|have|does|did|do)\b',question,re.I)
    stopping = re.search(r'\b(?:enough for now|stop here|stop writing)\b',question,re.I)
    if (asks_status or stopping) and CHECK_COMPLETE.search(question) and re.search(r'\b(?:it|that|this|program|code|reply|answer)\b',question,re.I):
        return COMPLETENESS_NOTICE
    return None


def continuation_source(turns, source_id, revision):
    from .errors import JuneError
    latest=next((t for t in reversed(turns) if t['status']=='complete' and t['assistant']!=COMPLETENESS_NOTICE),None)
    if not latest or resumable_turn(turns,revision)!=source_id:
        raise JuneError('continuation-stale','Only the latest unfinished general reply can be continued. Reopen the chat and try again.',409)
    chain=[];seen=set();current=latest;by_id={t['id']:t for t in turns}
    while current:
        if current['id'] in seen or len(chain)>=32 or current['revision']!=revision:
            raise JuneError('continuation-stale','This continuation is no longer available. Start a fresh request.',409)
        seen.add(current['id']);chain.append(current)
        parent=current.get('continuedFrom')
        current=by_id.get(parent) if parent else None
        if parent and current is None:
            raise JuneError('continuation-stale','The original reply is unavailable.',409)
    chain.reverse()
    prefix=''.join(t['assistant'] for t in chain)
    if len(prefix)>32000:
        raise JuneError('continuation-limit','This reply is too long to continue safely. Ask for a smaller, self-contained section.',409)
    return {'id':source_id,'question':chain[0]['user'],'prefix':prefix}
