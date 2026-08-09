import { browser } from '$app/environment';
import { fetchCurrentUserSettings, updateCurrentUserSetting } from '$lib/api/userSettings';
import { type ThemePreference } from '$lib/settings/userSettings';

function isThemePreference(value: string): value is ThemePreference {
	return value === 'light' || value === 'dark';
}

export function applyThemePreference(preference: ThemePreference): void {
	if (!browser) {
		return;
	}

	document.documentElement.setAttribute('data-theme', preference);
}

export async function getThemePreference(): Promise<ThemePreference> {
	if (!browser) {
		return 'light';
	}

	try {
		const settings = await fetchCurrentUserSettings();
		if (isThemePreference(settings.themePreference)) {
			return settings.themePreference;
		}
	} catch {
		return 'light';
	}

	return 'light';
}

export async function initThemePreference(): Promise<ThemePreference> {
	const preference = await getThemePreference();
	applyThemePreference(preference);
	return preference;
}

export async function setThemePreference(preference: ThemePreference): Promise<void> {
	if (!browser) {
		return;
	}

	applyThemePreference(preference);
	await updateCurrentUserSetting('themePreference', preference);
}
