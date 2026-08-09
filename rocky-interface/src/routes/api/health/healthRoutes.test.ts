import { describe, expect, it } from 'vitest';
import { GET } from './+server';

describe('public Rocky health routes', () => {
	it('returns 200 from the shallow health route', async () => {
		const response = await GET({} as Parameters<typeof GET>[0]);
		const body = await response.json();

		expect(response.status).toBe(200);
		expect(body).toEqual({
			ok: true,
			service: 'rocky-web'
		});
	});
});
