import type { ChatConversation, ConversationGroup, ConversationGroupLabel } from '$lib/types/chat';

const GROUP_ORDER: ConversationGroupLabel[] = ['Today', 'Yesterday', 'This Week', 'Older'];

function parseDate(value?: string): Date | null {
	if (!value) return null;
	const parsed = new Date(value);
	return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function localDayNumber(value: Date): number {
	return Math.floor(Date.UTC(value.getFullYear(), value.getMonth(), value.getDate()) / 86_400_000);
}

export function conversationLabel(conversation: ChatConversation): string {
	return conversation.title?.trim() || 'Untitled chat';
}

export function conversationGroupLabel(
	conversation: ChatConversation,
	now = new Date()
): ConversationGroupLabel {
	const updatedAt = parseDate(conversation.updated_at || conversation.created_at);
	if (!updatedAt) return 'Older';

	const dayDifference = localDayNumber(now) - localDayNumber(updatedAt);

	if (dayDifference <= 0) return 'Today';
	if (dayDifference === 1) return 'Yesterday';
	if (dayDifference < 7) return 'This Week';
	return 'Older';
}

export function formatConversationTime(conversation: ChatConversation, now = new Date()): string {
	const updatedAt = parseDate(conversation.updated_at || conversation.created_at);
	if (!updatedAt) return '';

	const group = conversationGroupLabel(conversation, now);
	if (group === 'Today') {
		return new Intl.DateTimeFormat(undefined, {
			hour: 'numeric',
			minute: '2-digit'
		}).format(updatedAt);
	}

	if (group === 'Yesterday') return 'Yesterday';
	if (group === 'This Week') {
		return new Intl.DateTimeFormat(undefined, { weekday: 'short' }).format(updatedAt);
	}

	return new Intl.DateTimeFormat(undefined, {
		month: 'short',
		day: 'numeric'
	}).format(updatedAt);
}

export function groupConversations(
	conversations: ChatConversation[],
	query = '',
	now = new Date()
): ConversationGroup[] {
	const normalizedQuery = query.trim().toLocaleLowerCase();
	const buckets = new Map<ConversationGroupLabel, ChatConversation[]>(
		GROUP_ORDER.map((label) => [label, []])
	);

	for (const conversation of conversations) {
		if (
			normalizedQuery &&
			!conversationLabel(conversation).toLocaleLowerCase().includes(normalizedQuery)
		) {
			continue;
		}
		buckets.get(conversationGroupLabel(conversation, now))?.push(conversation);
	}

	return GROUP_ORDER.map((label) => ({
		label,
		conversations: buckets.get(label) || []
	})).filter((group) => group.conversations.length > 0);
}
