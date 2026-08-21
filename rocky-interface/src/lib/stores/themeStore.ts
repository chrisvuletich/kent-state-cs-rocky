import { browser } from '$app/environment';
import { updateCurrentUserSetting } from '$lib/api/userSettings';
import { type ThemePreference } from '$lib/settings/userSettings';

export function applyThemePreference(preference: ThemePreference): void {
	if (!browser) {
		return;
	}

	document.documentElement.setAttribute('data-theme', preference);
}

export async function setThemePreference(preference: ThemePreference): Promise<void> {
	if (!browser) {
		return;
	}

	applyThemePreference(preference);
	await updateCurrentUserSetting('themePreference', preference);
}
