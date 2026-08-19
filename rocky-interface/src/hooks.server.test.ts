import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createSessionToken } from '$lib/server/sessionAuth';
import { themeCookieName } from '$lib/server/themePreferenceCookie';
import { handle } from './hooks.server';

const ACTIVE_USER = {
	first_name: 'Offline',
	last_name: 'Admin',
	email: 'admin.local@kent.edu',
	id: 'admin-1',
	api_key_owner_id: 'admin-1',
	is_admin: true,
	is_active: true,
	role: 'admin'
};

function requestEvent(user = ACTIVE_USER) {
	const sessionToken = createSessionToken(user.email);
	const values = new Map([
		['rocky_session', sessionToken],
		[themeCookieName(user.id), 'dark']
	]);

	return {
		cookies: {
			get: vi.fn((name: string) => values.get(name)),
			set: vi.fn(),
			delete: vi.fn()
		},
		locals: {},
		request: new Request('http://rocky.example.invalid/api/backend/courses'),
		url: new URL('http://rocky.example.invalid/api/backend/courses')
	};
}

describe('request hook performance boundary', () => {
	beforeEach(() => {
		vi.stubGlobal(
			'fetch',
			vi.fn(async (input: string | URL | Request) => {
				const url = new URL(input instanceof Request ? input.url : input);
				if (url.pathname === '/auth/session-user') {
					return Response.json(ACTIVE_USER);
				}
				throw new Error(`Unexpected backend request: ${url.pathname}`);
			})
		);
	});

	afterEach(() => vi.unstubAllGlobals());

	it('authenticates an API request without loading appearance settings', async () => {
		const event = requestEvent();
		const resolve = vi.fn(async () => new Response('ok'));
		const response = await handle({ event, resolve } as never);
		const backendFetch = vi.mocked(fetch);

		expect(response.status).toBe(200);
		expect(resolve).toHaveBeenCalledOnce();
		expect(event.locals).toMatchObject({
			currentUser: expect.objectContaining({ id: 'admin-1', isActive: true }),
			themePreference: 'dark'
		});
		expect(backendFetch).toHaveBeenCalledOnce();
		expect(new URL(String(backendFetch.mock.calls[0][0])).pathname).toBe('/auth/session-user');
	});

	it('still rejects API requests from an inactive authenticated account', async () => {
		const inactiveUser = { ...ACTIVE_USER, is_active: false };
		const event = requestEvent(inactiveUser);
		vi.mocked(fetch).mockResolvedValueOnce(Response.json(inactiveUser));
		const resolve = vi.fn(async () => new Response('unexpected'));

		const response = await handle({ event, resolve } as never);
		const body = await response.json();

		expect(response.status).toBe(403);
		expect(body.error.code).toBe('account_inactive');
		expect(resolve).not.toHaveBeenCalled();
		expect(fetch).toHaveBeenCalledOnce();
	});
});
