import { beforeEach, describe, expect, it, vi } from 'vitest';

function routeEvent(mockFetch: ReturnType<typeof vi.fn>, query = '') {
	return {
		fetch: mockFetch,
		url: new URL(`http://rocky.example.invalid/api/server-health${query}`)
	};
}

describe('public Rocky server health route', () => {
	beforeEach(() => vi.resetModules());

	it('returns 200 when every downstream service is healthy', async () => {
		const { GET } = await import('./+server');
		const mockFetch = vi.fn().mockResolvedValue(new Response(null, { status: 200 }));
		const response = await GET(routeEvent(mockFetch) as unknown as Parameters<typeof GET>[0]);
		const body = await response.json();

		expect(mockFetch).toHaveBeenCalledTimes(4);
		expect(response.status).toBe(200);
		expect(response.headers.get('cache-control')).toBe('no-store');
		expect(body.ok).toBe(true);
		expect(body.services).toEqual([
			expect.objectContaining({ name: 'web', ok: true }),
			expect.objectContaining({ name: 'backend', ok: true }),
			expect.objectContaining({ name: 'granite', ok: true }),
			expect.objectContaining({ name: 'chat-api', ok: true }),
			expect.objectContaining({ name: 'ollama', ok: true })
		]);
	});

	it('reuses a recent probe and allows an explicit refresh', async () => {
		const { GET } = await import('./+server');
		const mockFetch = vi.fn().mockResolvedValue(new Response(null, { status: 200 }));

		await GET(routeEvent(mockFetch) as unknown as Parameters<typeof GET>[0]);
		await GET(routeEvent(mockFetch) as unknown as Parameters<typeof GET>[0]);
		expect(mockFetch).toHaveBeenCalledTimes(4);

		await GET(routeEvent(mockFetch, '?refresh=1') as unknown as Parameters<typeof GET>[0]);
		expect(mockFetch).toHaveBeenCalledTimes(8);
	});

	it('returns 503 when one downstream service is unhealthy', async () => {
		const { GET } = await import('./+server');
		const mockFetch = vi
			.fn()
			.mockResolvedValueOnce(new Response(null, { status: 200 }))
			.mockResolvedValueOnce(new Response(null, { status: 503 }))
			.mockResolvedValueOnce(new Response(null, { status: 200 }))
			.mockResolvedValueOnce(new Response(null, { status: 200 }));

		const response = await GET(routeEvent(mockFetch) as unknown as Parameters<typeof GET>[0]);
		const body = await response.json();

		expect(mockFetch).toHaveBeenCalledTimes(4);
		expect(response.status).toBe(503);
		expect(body.ok).toBe(false);
		expect(body.services.find((service: { name: string }) => service.name === 'granite')).toEqual(
			expect.objectContaining({ name: 'granite', ok: false })
		);
	});

	it('returns 503 without exposing downstream connection failures', async () => {
		const { GET } = await import('./+server');
		const mockFetch = vi
			.fn()
			.mockResolvedValueOnce(new Response(null, { status: 200 }))
			.mockRejectedValueOnce(new Error('synthetic connection failure'))
			.mockResolvedValueOnce(new Response(null, { status: 200 }))
			.mockResolvedValueOnce(new Response(null, { status: 200 }));

		const response = await GET(routeEvent(mockFetch) as unknown as Parameters<typeof GET>[0]);
		const body = await response.json();

		expect(mockFetch).toHaveBeenCalledTimes(4);
		expect(response.status).toBe(503);
		expect(body.ok).toBe(false);
		expect(body.services.find((service: { name: string }) => service.name === 'granite')).toEqual(
			expect.objectContaining({ name: 'granite', ok: false })
		);
		expect(JSON.stringify(body)).not.toContain('synthetic connection failure');
	});
});
