export type ChatRole = 'user' | 'assistant';

export type ChatMessageState = 'sent' | 'sending' | 'failed';

export interface ChatMessage {
	id: string;
	role: ChatRole;
	content: string;
	createdAt?: string;
	state?: ChatMessageState;
	persisted?: boolean;
}

export interface ChatConversation {
	conversation_id: string;
	title?: string;
	created_at?: string;
	updated_at?: string;
}

export type ChatAvailability = 'checking' | 'available' | 'unavailable';

export type ConversationGroupLabel = 'Today' | 'Yesterday' | 'This Week' | 'Older';

export interface ConversationGroup {
	label: ConversationGroupLabel;
	conversations: ChatConversation[];
}
