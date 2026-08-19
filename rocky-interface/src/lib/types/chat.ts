export type ChatRole = 'user' | 'assistant';

export type ChatMessageState = 'sent' | 'sending' | 'streaming' | 'failed';

export type ChatImageMimeType = 'image/jpeg' | 'image/png' | 'image/webp';

export interface ChatImage {
	id: string;
	imageUrl: string;
	mimeType: ChatImageMimeType;
	byteLength: number;
	width?: number;
	height?: number;
	name?: string;
}

export interface ChatImageLimits {
	maxImages: number;
	maxImageBytes: number;
	maxTotalBytes: number;
	maxPixels: number;
	maxTotalPixels: number;
}

export interface ChatMessage {
	id: string;
	role: ChatRole;
	content: string;
	createdAt?: string;
	state?: ChatMessageState;
	persisted?: boolean;
	images?: ChatImage[];
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
