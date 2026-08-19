import { APP_ENV } from '$lib/config/env';
import { settingsDefinitions, type ThemePreference } from '$lib/settings/userSettings';

const THEME_COOKIE_PREFIX = 'rocky_theme_';

export const THEME_COOKIE_OPTIONS = {
	path: '/',
	httpOnly: true,
	sameSite: 'lax' as const,
	secure: APP_ENV === 'production',
	maxAge: 60 * 60 * 24 * 365
};

export function themeCookieName(userId: string): string {
	const safeUserId = userId
		.trim()
		.replace(/[^a-zA-Z0-9_-]/g, '_')
		.slice(0, 80);
	return `${THEME_COOKIE_PREFIX}${safeUserId || 'current'}`;
}

export function parseThemeCookie(value: string | undefined): ThemePreference | null {
	return settingsDefinitions.themePreference.validate(value) ? value : null;
}
