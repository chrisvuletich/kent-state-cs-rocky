import { describe, expect, it } from 'vitest';
import { chatExceptionFailure, chatHttpFailure, isAbortError } from './errors';

describe('chat failure feedback', () => {
	it('distinguishes authentication failures', () => {
		expect(chatHttpFailure(401, { error: { code: 'invalid_api_key' } })).toMatchObject({
			kind: 'authentication',
			markUnavailable: false
		});
	});

	it('distinguishes timeout, busy, and required logging failures', () => {
		expect(chatHttpFailure(504, { error: { code: 'model_timeout' } }).kind).toBe('timeout');
		expect(chatHttpFailure(503, { error: { code: 'model_busy' } }).kind).toBe('busy');
		expect(chatHttpFailure(503, { error: { code: 'request_logging_unavailable' } }).kind).toBe(
			'logging'
		);
	});

	it('uses the API message for ordinary request errors', () => {
		expect(chatHttpFailure(400, { error: { message: 'The message is invalid.' } }).message).toBe(
			'The message is invalid.'
		);
	});

	it('uses retry timing and request IDs for rate-limit feedback', () => {
		expect(
			chatHttpFailure(
				429,
				{ error: { code: 'rate_limit_exceeded' } },
				{ retryAfter: '17', requestId: 'req_synthetic' }
			)
		).toEqual({
			kind: 'rate_limit',
			message:
				"Rocky's request limit was reached. Try again in 17 seconds. Request ID: req_synthetic",
			markUnavailable: false,
			retryAfterSeconds: 17
		});
	});

	it('reports browser aborts as a stopped response without changing availability', () => {
		const error = new Error('aborted');
		error.name = 'AbortError';

		expect(isAbortError(error)).toBe(true);
		expect(chatExceptionFailure(error)).toMatchObject({
			kind: 'stopped',
			markUnavailable: false
		});
	});

	it('reports other fetch failures as a lost network connection', () => {
		expect(chatExceptionFailure(new TypeError('fetch failed'))).toMatchObject({
			kind: 'network',
			markUnavailable: true
		});
	});
});
