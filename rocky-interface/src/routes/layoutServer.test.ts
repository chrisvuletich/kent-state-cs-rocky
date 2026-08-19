import { afterEach, describe, expect, it, vi } from 'vitest';
import { getDefaultUserSettings } from '$lib/settings/userSettings';
import { themeCookieName } from '$lib/server/themePreferenceCookie';
import type { User } from '$lib/types/user';
import { load } from './+layout.server';

const ACTIVE_USER: User = {
	id: 'admin-1',
	firstName: 'Offline',
	lastName: 'Admin',
	displayName: 'Offline Admin',
	email: 'admin.local@kent.edu',
	apiKeyOwnerId: 'admin-1',
	isAdmin: true,
	role: 'admin',
	isActive: true
};

function layoutEvent(user: User | null = ACTIVE_USER) {
	return {
		cookies: {
			set: vi.fn()
		},
		locals: {
			currentUser: user,
			themePreference: 'light',
			userSettings: getDefaultUserSettings(),
			initialFrame: 'dashboard'
		},
		url: new URL('http://rocky.example.invalid/?frame=dashboard')
	};
}

describe('root layout user settings', () => {
	afterEach(() => vi.unstubAllGlobals());

	it('loads active-user settings at the page-rendering boundary', async () => {
		const settings = {
			themePreference: 'dark' as const,
			profilePicture: '/batch_cat.svg' as const
		};
		const backendFetch = vi.fn().mockResolvedValue(Response.json({ settings }));
		vi.stubGlobal('fetch', backendFetch);
		const event = layoutEvent();

		const data = await load(event as never);

		expect(backendFetch).toHaveBeenCalledOnce();
		expect(new URL(String(backendFetch.mock.calls[0][0])).pathname).toBe('/user-settings');
		expect(event.locals.themePreference).toBe('dark');
		expect(event.locals.userSettings).toEqual(settings);
		expect(event.cookies.set).toHaveBeenCalledWith(
			themeCookieName(ACTIVE_USER.id),
			'dark',
			expect.objectContaining({ httpOnly: true, path: '/' })
		);
		expect(data).toMatchObject({
			currentUser: ACTIVE_USER,
			themePreference: 'dark',
			userSettings: settings,
			initialFrame: 'dashboard'
		});
	});

	it('uses existing local defaults without a remote settings request for inactive users', async () => {
		const backendFetch = vi.fn();
		vi.stubGlobal('fetch', backendFetch);
		const event = layoutEvent({ ...ACTIVE_USER, isActive: false });
		event.locals.themePreference = 'dark';

		const data = await load(event as never);

		expect(backendFetch).not.toHaveBeenCalled();
		expect(event.cookies.set).toHaveBeenCalledWith(
			'rocky_current_frame',
			'dashboard',
			expect.objectContaining({ path: '/' })
		);
		expect(event.cookies.set).not.toHaveBeenCalledWith(
			themeCookieName(ACTIVE_USER.id),
			expect.anything(),
			expect.anything()
		);
		expect(data).toMatchObject({ themePreference: 'dark' });
	});

	it('does not load appearance settings for a non-app page', async () => {
		const backendFetch = vi.fn();
		vi.stubGlobal('fetch', backendFetch);
		const event = layoutEvent();
		event.url = new URL('http://rocky.example.invalid/credits');

		const data = await load(event as never);

		expect(backendFetch).not.toHaveBeenCalled();
		expect(event.cookies.set).not.toHaveBeenCalled();
		expect(data).toMatchObject({
			currentUser: ACTIVE_USER,
			themePreference: 'light',
			userSettings: getDefaultUserSettings()
		});
	});
});
