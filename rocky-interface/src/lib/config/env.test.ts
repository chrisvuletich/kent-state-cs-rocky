import { describe, expect, it } from 'vitest';
import { parseApiBaseUrl } from './env';

describe('parseApiBaseUrl', () => {
	it('normalizes a composable absolute backend URL', () => {
		expect(parseApiBaseUrl('https://backend.example.edu/rocky/')).toBe(
			'https://backend.example.edu/rocky'
		);
	});

	it.each([
		'https://backend.example.edu?tenant=one',
		'https://backend.example.edu#internal',
		'https://user:password@backend.example.edu'
	])('rejects a backend URL that cannot safely have routes appended: %s', (value) => {
		expect(() => parseApiBaseUrl(value)).toThrow(/PUBLIC_API_BASE_URL/);
	});
});
