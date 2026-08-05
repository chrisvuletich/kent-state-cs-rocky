import { describe, expect, it, vi } from 'vitest';
import { GET } from './+server';

describe('public Rocky server health route', () => {
	it('returns 200 when every downstream service is healthy', async () => {
		const mockFetch = vi.fn().mockResolvedValue(
			new Response(null, {
				status: 200
			})
		);

		const event = {
			fetch: mockFetch
		} as unknown as Parameters<typeof GET>[0];

		const response = await GET(event);
		const body = await response.json();

		expect(mockFetch).toHaveBeenCalledTimes(4);
		expect(response.status).toBe(200);
		expect(body.ok).toBe(true);

		expect(body.services).toEqual([
			expect.objectContaining({
				name: 'web',
				ok: true
			}),
			expect.objectContaining({
				name: 'backend',
				ok: true
			}),
			expect.objectContaining({
				name: 'granite',
				ok: true
			}),
			expect.objectContaining({
				name: 'chat-api',
				ok: true
			}),
			expect.objectContaining({
				name: 'ollama',
				ok: true
			})
		]);
	});
});

it('returns 503 when one downstream service is unhealthy', async () => {
	const mockFetch = vi
		.fn()
		.mockResolvedValueOnce(new Response(null, { status: 200 }))
		.mockResolvedValueOnce(new Response(null, { status: 503 }))
		.mockResolvedValueOnce(new Response(null, { status: 200 }))
		.mockResolvedValueOnce(new Response(null, { status: 200 }));

	const event = {
		fetch: mockFetch
	} as unknown as Parameters<typeof GET>[0];

	const response = await GET(event);
	const body = await response.json();

	expect(mockFetch).toHaveBeenCalledTimes(4);
	expect(response.status).toBe(503);
	expect(body.ok).toBe(false);

	const granite = body.services.find((service: { name: string }) => service.name === 'granite');

	expect(granite).toEqual(
		expect.objectContaining({
			name: 'granite',
			ok: false
		})
	);
});

it('returns 503 when one downstream service cannot be reached', async () => {
	const mockFetch = vi
		.fn()
		.mockResolvedValueOnce(new Response(null, { status: 200 }))
		.mockRejectedValueOnce(new Error('synthetic connection failure'))
		.mockResolvedValueOnce(new Response(null, { status: 200 }))
		.mockResolvedValueOnce(new Response(null, { status: 200 }));

	const event = {
		fetch: mockFetch
	} as unknown as Parameters<typeof GET>[0];

	const response = await GET(event);
	const body = await response.json();

	expect(mockFetch).toHaveBeenCalledTimes(4);
	expect(response.status).toBe(503);
	expect(body.ok).toBe(false);

	const granite = body.services.find((service: { name: string }) => service.name === 'granite');

	expect(granite).toEqual(
		expect.objectContaining({
			name: 'granite',
			ok: false
		})
	);

	expect(JSON.stringify(body)).not.toContain('synthetic connection failure');
});
