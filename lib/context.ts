import { MAX_CONTEXT_LENGTH, MAX_CONTEXT_MESSAGES, MAX_MESSAGE_LENGTH, type ChatMessage } from './chat-types';

/** Keep recent complete turns within the local model's existing request budget.
 * The full conversation stays on screen; this is not persistent memory.
 */
/** A partial reply (cut off at the length limit) is continued from its end, so its tail is what the model needs. */
export type ContextMessage = ChatMessage & { partial?: boolean };
const OMITTED = '[Earlier part omitted]\n';

export function prepareContext(history: readonly ContextMessage[], current: ChatMessage) {
  const messages: ChatMessage[] = [{ ...current }];
  const suffix = '\n[Shortened for context]';
  let length = current.content.length;
  let shortened = false;
  const compact = (message: ContextMessage): ChatMessage => {
    if (message.content.length <= MAX_MESSAGE_LENGTH) return { role: message.role, content: message.content };
    if (message.partial) {
      let start = message.content.length - (MAX_MESSAGE_LENGTH - OMITTED.length);
      if (/[\uDC00-\uDFFF]/.test(message.content[start]) && /[\uD800-\uDBFF]/.test(message.content[start - 1])) start++;
      return { role: message.role, content: OMITTED + message.content.slice(start) };
    }
    let end = MAX_MESSAGE_LENGTH - suffix.length;
    // JS counts UTF-16 units; keep an emoji's surrogate pair together.
    if (/[\uD800-\uDBFF]/.test(message.content[end - 1]) && /[\uDC00-\uDFFF]/.test(message.content[end])) end--;
    return { role: message.role, content: message.content.slice(0, end) + suffix };
  };

  for (let index = history.length - 2; index >= 0; index -= 2) {
    const user = compact(history[index]), assistant = compact(history[index + 1]);
    if (user.role !== 'user' || assistant.role !== 'assistant') break;
    const size = user.content.length + assistant.content.length;
    if (messages.length + 2 > MAX_CONTEXT_MESSAGES || length + size > MAX_CONTEXT_LENGTH) break;
    shortened ||= user.content !== history[index].content || assistant.content !== history[index + 1].content;
    messages.unshift(user, assistant);
    length += size;
  }
  return { messages, limited: shortened || messages.length - 1 < history.length };
}
