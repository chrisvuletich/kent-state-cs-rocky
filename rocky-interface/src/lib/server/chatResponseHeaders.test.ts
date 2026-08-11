import { describe, expect, it } from 'vitest';
import { forwardedChatResponseHeaders } from './chatResponseHeaders';

describe('forwardedChatResponseHeaders', () => {
	it('forwards only retry, request ID, and request-limit headers', () => {
		const upstream = new Headers({
			'Retry-After': '17',
			'X-Request-Id': 'req_synthetic',
			'X-Rocky-Request-Id': 'req_synthetic',
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
			'x-rocky-request-id': 'req_synthetic'
		});
		expect(forwarded.has('set-cookie')).toBe(false);
		expect(forwarded.has('authorization')).toBe(false);
	});
});
