import type {SavedConversation} from './memory-types';

// Chat and the library share this counter so navigation invalidates work
// synchronously, before React has rendered the new conversation or scope.
export async function openLatestConversation(
  generation: {current:number},
  load: () => Promise<SavedConversation>,
  apply: (chat:SavedConversation, token:number) => void,
  fail: (error:unknown) => void,
) {
  const token=++generation.current;
  try {
    const chat=await load();
    if(token!==generation.current)return;
    apply(chat,token);
  } catch(error) {
    if(token===generation.current)fail(error);
  }
}
