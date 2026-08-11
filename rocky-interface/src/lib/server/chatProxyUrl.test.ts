import { describe, expect, it } from 'vitest';
import { deriveChatApiBaseUrl, resolveChatApiUrls } from './chatProxyUrl';

describe('resolveChatApiUrls', () => {
	it.each([
		'http://127.0.0.1:5003',
		'http://127.0.0.1:5003/',
		'http://127.0.0.1:5003/v1/responses',
		'http://127.0.0.1:5003/v1/responses/'
	])('normalizes a service base or generation endpoint: %s', (value) => {
		expect(resolveChatApiUrls(value)).toEqual({
			generationUrl: 'http://127.0.0.1:5003/v1/responses',
			baseUrl: 'http://127.0.0.1:5003'
		});
	});

	it('supports a reverse-proxy base path', () => {
		expect(resolveChatApiUrls('https://rocky.example.edu/chat')).toEqual({
			generationUrl: 'https://rocky.example.edu/chat/v1/responses',
			baseUrl: 'https://rocky.example.edu/chat'
		});
		expect(deriveChatApiBaseUrl('https://rocky.example.edu/chat/v1/responses')).toBe(
			'https://rocky.example.edu/chat'
		);
	});

	it.each([
		'',
		'localhost:5003/v1/responses',
		'ftp://localhost/v1/responses',
		'http://user:password@localhost:5003/v1/responses',
		'http://localhost:5003/v1/responses?tenant=one',
		'http://localhost:5003/v1/responses#internal',
		'http://localhost:70000/v1/responses',
		'http://[invalid/v1/responses'
	])('rejects an invalid private Chat API URL: %s', (value) => {
		expect(() => resolveChatApiUrls(value)).toThrow(/ROCKY_CHAT_API_URL/);
	});
});
