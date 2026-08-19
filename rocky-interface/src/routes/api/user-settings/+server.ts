import { error, json, type RequestHandler } from '@sveltejs/kit';
import { sanitizeUserSettingsPatch } from '$lib/settings/userSettings';
import { getSettingsForUser, updateSettingsPatchForUser } from '$lib/server/userSettingsStore';
import { THEME_COOKIE_OPTIONS, themeCookieName } from '$lib/server/themePreferenceCookie';

export const GET: RequestHandler = async ({ locals }) => {
	if (!locals.currentUser) {
		throw error(401, 'Not authenticated.');
	}

	const settings = await getSettingsForUser(locals.currentUser);
	return json({ settings });
};

export const PATCH: RequestHandler = async ({ cookies, locals, request }) => {
	if (!locals.currentUser) {
		throw error(401, 'Not authenticated.');
	}

	const body = (await request.json()) as unknown;
	const patch = sanitizeUserSettingsPatch(body);

	if (Object.keys(patch).length === 0) {
		throw error(400, 'No valid settings were provided.');
	}

	const settings = await updateSettingsPatchForUser(locals.currentUser, patch);
	if (patch.themePreference) {
		cookies.set(
			themeCookieName(locals.currentUser.id),
			settings.themePreference,
			THEME_COOKIE_OPTIONS
		);
	}
	return json({ ok: true, settings });
};
