import { writable } from 'svelte/store';

/** A conversation selected outside the chat view and waiting to be opened. */
export const pendingChatConversationId = writable<string | null>(null);
