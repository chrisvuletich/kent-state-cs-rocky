import { beforeEach, describe, expect, it, vi } from 'vitest';

const syntheticUser = {
	id: 'student-synthetic',
	firstName: 'Synthetic',
	lastName: 'Student',
	displayName: 'Synthetic Student',
	email: 'student@example.invalid',
	apiKeyOwnerId: 'student-synthetic',
	isAdmin: false,
	role: 'student',
	isActive: true
};

vi.mock('$lib/server/chatProxy', () => ({
	CHAT_API_URL: 'http://chat.example.invalid/v1/responses',
	CHAT_MODEL: 'synthetic-model',
	CHAT_STREAMING_ENABLED: true,
	chatApiPayload: (value: Record<string, unknown>) => value,
	chatRequestHeaders: () => ({ Authorization: 'Bearer synthetic-hidden-key' }),
	requireChatUser: () => syntheticUser
}));

import { POST } from './+server';

function requestEvent(mockFetch: ReturnType<typeof vi.fn>, request: Request) {
	return {
		request,
		fetch: mockFetch,
		locals: { currentUser: syntheticUser }
	} as unknown as Parameters<typeof POST>[0];
}

function routeEvent(mockFetch: ReturnType<typeof vi.fn>, body: Record<string, unknown>) {
	return requestEvent(
		mockFetch,
		new Request('http://rocky.example.invalid/api/chat', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify(body)
		})
	);
}

describe('streaming chat proxy route', () => {
	beforeEach(() => vi.clearAllMocks());

	it('requests streaming and relays the upstream body without buffering', async () => {
		const frame =
			'event: response.created\ndata: {"type":"response.created","sequence_number":0}\n\n';
		const upstream = new Response(frame, {
			status: 200,
			headers: {
				'Content-Type': 'text/event-stream',
				'X-Request-Id': 'req_stream',
				'X-Rocky-Conversation-Id': 'conversation-stream',
				'X-Rocky-Message-Stored': 'true',
				'Set-Cookie': 'must-not-be-forwarded=true'
			}
		});
		const mockFetch = vi.fn().mockResolvedValue(upstream);

		const response = await POST(
			routeEvent(mockFetch, { message: 'Hello', conversation_id: 'existing-conversation' })
		);
		const request = mockFetch.mock.calls[0][1] as RequestInit;
		const payload = JSON.parse(String(request.body));

		expect(payload).toEqual({
			model: 'synthetic-model',
			input: 'Hello',
			stream: true,
			store: true,
			conversation_id: 'existing-conversation'
		});
		expect(request.headers).toMatchObject({
			Accept: 'text/event-stream',
			Authorization: 'Bearer synthetic-hidden-key'
		});
		expect(response.headers.get('content-type')).toBe('text/event-stream; charset=utf-8');
		expect(response.headers.get('x-accel-buffering')).toBe('no');
		expect(response.headers.get('x-rocky-conversation-id')).toBe('conversation-stream');
		expect(response.headers.has('set-cookie')).toBe(false);
		expect(await response.text()).toBe(frame);
	});

	it('constructs Responses content blocks for text and Base64 image input', async () => {
		const frame =
			'event: response.created\ndata: {"type":"response.created","sequence_number":0}\n\n';
		const mockFetch = vi
			.fn()
			.mockResolvedValue(new Response(frame, { headers: { 'Content-Type': 'text/event-stream' } }));
		const imageUrl = 'data:image/png;base64,iVBORw0KGgo=';

		await POST(
			routeEvent(mockFetch, {
				message: 'What is shown?',
				images: [{ image_url: imageUrl, detail: 'auto' }]
			})
		);

		const payload = JSON.parse(String((mockFetch.mock.calls[0][1] as RequestInit).body));
		expect(payload.input).toEqual([
			{
				role: 'user',
				content: [
					{ type: 'input_text', text: 'What is shown?' },
					{ type: 'input_image', image_url: imageUrl, detail: 'auto' }
				]
			}
		]);
	});

	it('supports image-only input and rejects unsupported image sources locally', async () => {
		const mockFetch = vi.fn().mockResolvedValue(
			new Response('event: response.created\n\n', {
				headers: { 'Content-Type': 'text/event-stream' }
			})
		);
		const accepted = await POST(
			routeEvent(mockFetch, {
				message: '',
				images: [{ image_url: 'data:image/jpeg;base64,/9j/2Q==' }]
			})
		);
		expect(accepted.status).toBe(200);

		const rejectedFetch = vi.fn();
		const rejected = await POST(
			routeEvent(rejectedFetch, {
				message: 'Inspect this',
				images: [{ image_url: 'https://example.invalid/image.png' }]
			})
		);
		expect(rejected.status).toBe(400);
		expect((await rejected.json()).error.code).toBe('invalid_image');
		expect(rejectedFetch).not.toHaveBeenCalled();
	});

	it('keeps malformed JSON distinct from an empty chat request', async () => {
		const mockFetch = vi.fn();
		const response = await POST(
			requestEvent(
				mockFetch,
				new Request('http://rocky.example.invalid/api/chat', {
					method: 'POST',
					headers: { 'Content-Type': 'application/json' },
					body: '{'
				})
			)
		);

		expect(response.status).toBe(400);
		expect((await response.json()).error.code).toBe('invalid_json');
		expect(mockFetch).not.toHaveBeenCalled();
	});

	it('preserves the adapter payload-too-large status and error code', async () => {
		const mockFetch = vi.fn();
		const request = new Request('http://rocky.example.invalid/api/chat', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: '{}'
		});
		vi.spyOn(request, 'json').mockRejectedValue(
			Object.assign(new Error('Payload Too Large'), { status: 413 })
		);

		const response = await POST(requestEvent(mockFetch, request));

		expect(response.status).toBe(413);
		expect((await response.json()).error.code).toBe('request_too_large');
		expect(mockFetch).not.toHaveBeenCalled();
	});

	it('keeps pre-stream API failures as JSON with their real status', async () => {
		const upstream = Response.json(
			{
				error: {
					message: 'Streaming is not enabled.',
					type: 'invalid_request_error',
					param: 'stream',
					code: 'unsupported_parameter'
				}
			},
			{ status: 400, headers: { 'X-Request-Id': 'req_failure' } }
		);
		const response = await POST(routeEvent(vi.fn().mockResolvedValue(upstream), { message: 'Hi' }));

		expect(response.status).toBe(400);
		expect(response.headers.get('x-request-id')).toBe('req_failure');
		expect((await response.json()).error.code).toBe('unsupported_parameter');
	});

	it('propagates downstream cancellation to the upstream response body', async () => {
		const cancelled = vi.fn();
		const upstream = new Response(
			new ReadableStream<Uint8Array>({
				start(controller) {
					controller.enqueue(new TextEncoder().encode('event: response.created\n'));
				},
				cancel: cancelled
			}),
			{ status: 200, headers: { 'Content-Type': 'text/event-stream' } }
		);
		const response = await POST(
			routeEvent(vi.fn().mockResolvedValue(upstream), { message: 'Cancel this' })
		);

		await response.body?.cancel('student stopped');

		expect(cancelled).toHaveBeenCalledOnce();
	});

	it('fails closed when a successful upstream response is not SSE', async () => {
		const response = await POST(
			routeEvent(vi.fn().mockResolvedValue(Response.json({ output_text: 'buffered reply' })), {
				message: 'Hi'
			})
		);

		expect(response.status).toBe(502);
		expect((await response.json()).error.code).toBe('invalid_model_response');
	});
});
