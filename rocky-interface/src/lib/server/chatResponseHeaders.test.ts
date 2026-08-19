import { describe, expect, it } from 'vitest';
import { forwardedChatResponseHeaders, streamingChatResponseHeaders } from './chatResponseHeaders';

describe('forwardedChatResponseHeaders', () => {
	it('forwards only retry, request ID, and request-limit headers', () => {
		const upstream = new Headers({
			'Retry-After': '17',
			'X-Request-Id': 'req_synthetic',
			'X-Rocky-Request-Id': 'req_synthetic',
			'X-Rocky-Conversation-Id': 'conversation-synthetic',
			'X-Rocky-Message-Stored': 'true',
			'X-RateLimit-Limit-Requests': '10',
			'X-RateLimit-Remaining-Requests': '0',
			'X-RateLimit-Reset-Requests': '17s',
			'Set-Cookie': 'must-not-be-forwarded=true',
			Authorization: 'Bearer must-not-be-forwarded'
		});

		const forwarded = forwardedChatResponseHeaders(upstream);

		expect(Object.fromEntries(forwarded.entries())).toEqual({
			'retry-after': '17',
			'x-ratelimit-limit-requests': '10',
			'x-ratelimit-remaining-requests': '0',
			'x-ratelimit-reset-requests': '17s',
			'x-request-id': 'req_synthetic',
			'x-rocky-conversation-id': 'conversation-synthetic',
			'x-rocky-message-stored': 'true',
			'x-rocky-request-id': 'req_synthetic'
		});
		expect(forwarded.has('set-cookie')).toBe(false);
		expect(forwarded.has('authorization')).toBe(false);
	});

	it('sets stream-safe transport headers without forwarding arbitrary upstream headers', () => {
		const forwarded = streamingChatResponseHeaders(
			new Headers({
				'X-Request-Id': 'req_stream',
				'Content-Encoding': 'private-encoding',
				'Set-Cookie': 'must-not-be-forwarded=true'
			})
		);

		expect(Object.fromEntries(forwarded.entries())).toEqual({
			'cache-control': 'no-cache, no-transform',
			'content-type': 'text/event-stream; charset=utf-8',
			'x-accel-buffering': 'no',
			'x-request-id': 'req_stream'
		});
	});
});
