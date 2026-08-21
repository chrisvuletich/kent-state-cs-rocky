import { describe, expect, it } from 'vitest';

import { getDefaultUserSettings, isUserSettingKey, sanitizeUserSettings } from './userSettings';

describe('user settings validation', () => {
	it('returns the application defaults', () => {
		expect(getDefaultUserSettings()).toEqual({
			themePreference: 'light',
			profilePicture: '/batch_dog.svg'
		});
	});

	it('recognizes only supported setting keys', () => {
		expect(isUserSettingKey('themePreference')).toBe(true);
		expect(isUserSettingKey('profilePicture')).toBe(true);
		expect(isUserSettingKey('unknownSetting')).toBe(false);
		expect(isUserSettingKey('toString')).toBe(false);
	});

	it('accepts valid stored settings', () => {
		expect(
			sanitizeUserSettings({
				themePreference: 'dark',
				profilePicture: '/batch_cat.svg'
			})
		).toEqual({
			themePreference: 'dark',
			profilePicture: '/batch_cat.svg'
		});
	});

	it('replaces missing or invalid stored values with defaults', () => {
		expect(sanitizeUserSettings(null)).toEqual(getDefaultUserSettings());
		expect(sanitizeUserSettings('not an object')).toEqual(getDefaultUserSettings());
		expect(
			sanitizeUserSettings({ themePreference: 'system', profilePicture: '/unknown.svg' })
		).toEqual(getDefaultUserSettings());
		expect(sanitizeUserSettings({ themePreference: 'dark' })).toEqual({
			themePreference: 'dark',
			profilePicture: '/batch_dog.svg'
		});
	});
});
