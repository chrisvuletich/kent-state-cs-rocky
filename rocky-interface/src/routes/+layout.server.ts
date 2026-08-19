import { redirect } from '@sveltejs/kit';
import { appHref, isAccessibleRequestedFrame, resolveAppFrame } from '$lib/navigation/appRoute';
import { getSettingsForUser } from '$lib/server/userSettingsStore';
import { THEME_COOKIE_OPTIONS, themeCookieName } from '$lib/server/themePreferenceCookie';
import type { LayoutServerLoad } from './$types';

const FRAME_COOKIE_NAME = 'rocky_current_frame';
const FRAME_COOKIE_MAX_AGE_SECONDS = 60 * 60;

export const load: LayoutServerLoad = async ({ cookies, locals, url }) => {
	const requestedDocumentation = url.searchParams.get('doc')?.trim();
	const requestedFrame = url.searchParams.get('frame');
	const isAdmin = locals.currentUser?.isAdmin ?? false;

	if (
		url.pathname === '/' &&
		locals.currentUser &&
		!requestedDocumentation &&
		!isAccessibleRequestedFrame(requestedFrame, isAdmin)
	) {
		throw redirect(303, appHref(url, { frame: 'dashboard' }));
	}

	if (url.pathname === '/' && locals.currentUser?.isActive) {
		const settings = await getSettingsForUser(locals.currentUser);
		locals.themePreference = settings.themePreference;
		locals.userSettings = settings;
		cookies.set(
			themeCookieName(locals.currentUser.id),
			settings.themePreference,
			THEME_COOKIE_OPTIONS
		);
	}

	const initialFrame = resolveAppFrame(url.searchParams, locals.initialFrame, isAdmin);
	if (url.pathname === '/' && locals.currentUser) {
		cookies.set(FRAME_COOKIE_NAME, initialFrame, {
			path: '/',
			maxAge: FRAME_COOKIE_MAX_AGE_SECONDS,
			sameSite: 'lax'
		});
	}

	return {
		currentUser: locals.currentUser,
		themePreference: locals.themePreference,
		userSettings: locals.userSettings,
		initialFrame
	};
};
