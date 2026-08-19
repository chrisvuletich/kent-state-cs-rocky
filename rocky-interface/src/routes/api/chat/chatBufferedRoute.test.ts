import { expect, it, vi } from 'vitest';

vi.mock('$lib/server/chatProxy', () => ({
	CHAT_API_URL: 'http://chat.example.invalid/v1/responses',
	CHAT_MODEL: 'synthetic-model',
	CHAT_STREAMING_ENABLED: false,
	chatApiPayload: (value: Record<string, unknown>) => value,
	chatRequestHeaders: () => ({ Authorization: 'Bearer synthetic-hidden-key' }),
	requireChatUser: () => ({ id: 'student-synthetic', isActive: true })
}));

import { POST } from './+server';

it('keeps buffered chat available while the streaming rollout flag is disabled', async () => {
	const mockFetch = vi.fn().mockResolvedValue(
		Response.json({
			id: 'resp_buffered',
			status: 'completed',
			output_text: 'Buffered reply',
			conversation_id: 'conversation-buffered',
			message_stored: true
		})
	);
	const response = await POST({
		request: new Request('http://rocky.example.invalid/api/chat', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ message: 'Hello' })
		}),
		fetch: mockFetch,
		locals: { currentUser: { id: 'student-synthetic', isActive: true } }
	} as unknown as Parameters<typeof POST>[0]);
	const request = mockFetch.mock.calls[0][1] as RequestInit;

	expect(request.headers).toMatchObject({ Accept: 'application/json' });
	expect(JSON.parse(String(request.body))).toEqual({
		model: 'synthetic-model',
		input: 'Hello',
		store: true
	});
	expect(response.status).toBe(200);
	expect((await response.json()).output_text).toBe('Buffered reply');
});

it('keeps image input available on the buffered fallback path', async () => {
	const mockFetch = vi.fn().mockResolvedValue(
		Response.json({
			id: 'resp_buffered_image',
			status: 'completed',
			output_text: 'Buffered image reply'
		})
	);
	const imageUrl = 'data:image/png;base64,iVBORw0KGgo=';

	await POST({
		request: new Request('http://rocky.example.invalid/api/chat', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ message: '', images: [{ image_url: imageUrl }] })
		}),
		fetch: mockFetch,
		locals: { currentUser: { id: 'student-synthetic', isActive: true } }
	} as unknown as Parameters<typeof POST>[0]);

	expect(JSON.parse(String((mockFetch.mock.calls[0][1] as RequestInit).body))).toEqual({
		model: 'synthetic-model',
		input: [
			{
				role: 'user',
				content: [{ type: 'input_image', image_url: imageUrl, detail: 'auto' }]
			}
		],
		store: true
	});
});
