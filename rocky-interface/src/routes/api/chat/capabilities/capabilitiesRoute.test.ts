import { expect, it, vi } from 'vitest';

vi.mock('$lib/server/chatProxy', () => ({
	CHAT_API_BASE_URL: 'http://chat.example.invalid',
	requireChatUser: () => ({ id: 'student-synthetic', isActive: true })
}));

import { GET } from './+server';

function routeEvent(mockFetch: ReturnType<typeof vi.fn>) {
	return {
		request: new Request('http://rocky.example.invalid/api/chat/capabilities'),
		fetch: mockFetch,
		locals: { currentUser: { id: 'student-synthetic', isActive: true } }
	} as unknown as Parameters<typeof GET>[0];
}

it('returns only the safe image capability and limit subset', async () => {
	const mockFetch = vi.fn().mockResolvedValue(
		Response.json({
			ok: true,
			image_input: {
				rocky_enabled: true,
				granite_enabled: true,
				limits_match: true,
				rocky_limits: {
					max_images: 4,
					max_image_bytes: 4_194_304,
					max_total_bytes: 6_291_456,
					max_pixels: 20_000_000,
					max_total_pixels: 40_000_000
				},
				granite_limits: { secret_internal_detail: true }
			}
		})
	);

	const response = await GET(routeEvent(mockFetch));

	expect(response.status).toBe(200);
	expect(response.headers.get('cache-control')).toBe('no-store');
	expect(await response.json()).toEqual({
		imageInput: {
			enabled: true,
			limits: {
				maxImages: 4,
				maxImageBytes: 4_194_304,
				maxTotalBytes: 6_291_456,
				maxPixels: 20_000_000,
				maxTotalPixels: 40_000_000
			}
		}
	});
	expect(mockFetch).toHaveBeenCalledWith('http://chat.example.invalid/ready', {
		headers: { Accept: 'application/json' },
		signal: expect.any(AbortSignal),
		cache: 'no-store'
	});
});

it('fails closed when readiness does not expose valid limits', async () => {
	const response = await GET(routeEvent(vi.fn().mockResolvedValue(Response.json({}))));

	expect(response.status).toBe(502);
	expect(await response.json()).toEqual({ imageInput: { enabled: false, limits: null } });
});

it('fails closed when an unhealthy readiness response still reports matching image flags', async () => {
	const response = await GET(
		routeEvent(
			vi.fn().mockResolvedValue(
				Response.json(
					{
						ok: false,
						image_input: {
							rocky_enabled: true,
							granite_enabled: true,
							limits_match: true,
							rocky_limits: {
								max_images: 4,
								max_image_bytes: 4_194_304,
								max_total_bytes: 6_291_456,
								max_pixels: 20_000_000,
								max_total_pixels: 40_000_000
							}
						}
					},
					{ status: 503 }
				)
			)
		)
	);

	expect(response.status).toBe(502);
	expect(await response.json()).toEqual({ imageInput: { enabled: false, limits: null } });
});
