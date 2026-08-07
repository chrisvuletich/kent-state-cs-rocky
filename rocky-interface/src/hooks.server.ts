import { redirect, type Handle } from '@sveltejs/kit';
import { getUserByEmail, SESSION_COOKIE_NAME, SESSION_COOKIE_OPTIONS } from '$lib/server/mockAuth';
import { getSettingsForUser } from './lib/server/userSettingsStore';
import { getDefaultUserSettings } from '$lib/settings/userSettings';
import { framesForRole, type FrameName } from '$lib/types/frame';
import { readSessionEmail } from '$lib/server/sessionAuth';

const MUTATING_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);
const FRAME_COOKIE_NAME = 'rocky_current_frame';

function isPathAllowedForDeactivated(pathname: string): boolean {
	if (pathname === '/deactivated' || pathname === '/logout') {
		return true;
	}

	if (pathname.startsWith('/auth/') || pathname.startsWith('/api/')) {
		return true;
	}

	return false;
}

function readInitialFrameFromCookie(rawValue: string | undefined, isAdmin: boolean): FrameName {
	const allowedFrames = framesForRole(isAdmin);
	if (!rawValue) {
		return 'dashboard';
	}

	const value = rawValue.trim().toLowerCase();
	if (allowedFrames.includes(value as FrameName)) {
		return value as FrameName;
	}

	return 'dashboard';
}

function isRootActionRequest(pathname: string, method: string): boolean {
	return pathname === '/' && MUTATING_METHODS.has(method.toUpperCase());
}

export const handle: Handle = async ({ event, resolve }) => {
	const sessionToken = event.cookies.get(SESSION_COOKIE_NAME);
	const sessionEmail = readSessionEmail(sessionToken);
	let currentUser = null;

	if (sessionEmail) {
		currentUser = await getUserByEmail(sessionEmail);
		if (!currentUser) {
			event.cookies.delete(SESSION_COOKIE_NAME, SESSION_COOKIE_OPTIONS);
		}
	} else if (sessionToken) {
		event.cookies.delete(SESSION_COOKIE_NAME, SESSION_COOKIE_OPTIONS);
	}

	event.locals.currentUser = currentUser;
	event.locals.themePreference = 'light';
	event.locals.userSettings = getDefaultUserSettings();
	event.locals.initialFrame = readInitialFrameFromCookie(event.cookies.get(FRAME_COOKIE_NAME), currentUser?.isAdmin ?? false);

	if (currentUser) {
		const settings = await getSettingsForUser(currentUser);
		event.locals.themePreference = settings.themePreference;
		event.locals.userSettings = settings;
	}

	const isRootPath = event.url.pathname === '/';
	const isRootAction = isRootActionRequest(event.url.pathname, event.request.method);

	if ((isRootPath || isRootAction) && !currentUser) {
		throw redirect(303, '/login');
	}

	if (currentUser && !currentUser.isActive && !isPathAllowedForDeactivated(event.url.pathname)) {
		throw redirect(303, '/deactivated');
	}

	if (currentUser && currentUser.isActive && event.url.pathname === '/deactivated') {
		throw redirect(303, '/');
	}

	if (event.url.pathname.startsWith('/login') && currentUser) {
		throw redirect(303, '/');
	}

	return resolve(event, {
		transformPageChunk: ({ html }) => html.replace('<html lang="en">', `<html lang="en" data-theme="${event.locals.themePreference}">`)
	});
};
