import { error, json, type RequestHandler } from '@sveltejs/kit';
import { isUserSettingKey, settingsDefinitions } from '$lib/settings/userSettings';
import { updateSettingForUser } from '$lib/server/userSettingsStore';
import { THEME_COOKIE_OPTIONS, themeCookieName } from '$lib/server/themePreferenceCookie';

export const PATCH: RequestHandler = async ({ cookies, locals, params, request }) => {
	if (!locals.currentUser) {
		throw error(401, 'Not authenticated.');
	}

	const settingKey = params.key;
	if (!settingKey || !isUserSettingKey(settingKey)) {
		throw error(400, `Unknown setting key: ${settingKey}`);
	}

	const body = (await request.json()) as Partial<{ value: unknown }>;
	const value = body.value;

	if (!settingsDefinitions[settingKey].validate(value)) {
		throw error(400, `Invalid value for setting: ${settingKey}`);
	}

	const settings = await updateSettingForUser(locals.currentUser, settingKey, value);
	if (settingKey === 'themePreference') {
		cookies.set(
			themeCookieName(locals.currentUser.id),
			settings.themePreference,
			THEME_COOKIE_OPTIONS
		);
	}
	return json({ ok: true, settings });
};
