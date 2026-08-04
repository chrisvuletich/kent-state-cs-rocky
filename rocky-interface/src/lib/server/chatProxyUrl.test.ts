import { describe, expect, it } from 'vitest';
import { deriveChatApiBaseUrl } from './chatProxyUrl';

describe('deriveChatApiBaseUrl', () => {
	it('removes the generation route', () => {
		expect(deriveChatApiBaseUrl('http://127.0.0.1:5003/v1/responses')).toBe(
			'http://127.0.0.1:5003'
		);
	});

	it('removes the generation route and its trailing slash', () => {
		expect(deriveChatApiBaseUrl('http://127.0.0.1:5003/v1/responses/')).toBe(
			'http://127.0.0.1:5003'
		);
	});

	it('preserves a plain origin', () => {
		expect(deriveChatApiBaseUrl('http://127.0.0.1:5003')).toBe('http://127.0.0.1:5003');
	});
});
