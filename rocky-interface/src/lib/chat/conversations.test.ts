import { describe, expect, it } from 'vitest';
import { conversationGroupLabel, conversationLabel, groupConversations } from './conversations';

const now = new Date('2026-08-07T16:00:00-04:00');

describe('chat conversation helpers', () => {
	it('uses a readable fallback for missing titles', () => {
		expect(conversationLabel({ conversation_id: '1' })).toBe('Untitled chat');
	});

	it('groups conversations by their updated date', () => {
		expect(
			conversationGroupLabel({ conversation_id: '1', updated_at: '2026-08-07T14:00:00-04:00' }, now)
		).toBe('Today');
		expect(
			conversationGroupLabel({ conversation_id: '2', updated_at: '2026-08-06T14:00:00-04:00' }, now)
		).toBe('Yesterday');
		expect(
			conversationGroupLabel({ conversation_id: '3', updated_at: '2026-08-03T14:00:00-04:00' }, now)
		).toBe('This Week');
	});

	it('does not misclassify yesterday across a daylight-saving boundary', () => {
		const afterSpringForward = new Date('2026-03-09T00:30:00-04:00');
		expect(
			conversationGroupLabel(
				{ conversation_id: 'dst', updated_at: '2026-03-08T00:30:00-05:00' },
				afterSpringForward
			)
		).toBe('Yesterday');
	});

	it('filters titles without changing group order', () => {
		const groups = groupConversations(
			[
				{ conversation_id: '1', title: 'Python lists', updated_at: '2026-08-07T14:00:00-04:00' },
				{ conversation_id: '2', title: 'Java queues', updated_at: '2026-08-06T14:00:00-04:00' }
			],
			'python',
			now
		);

		expect(groups).toHaveLength(1);
		expect(groups[0].label).toBe('Today');
		expect(groups[0].conversations.map((conversation) => conversation.conversation_id)).toEqual([
			'1'
		]);
	});
});
