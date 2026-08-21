export type ThemePreference = 'light' | 'dark';
export const profilePictureOptions = [
	{ value: '/batch_squirrel.svg', label: 'Gold profile picture' },
	{ value: '/batch_dog.svg', label: 'Purple profile picture' },
	{ value: '/batch_duck.svg', label: 'Green profile picture' },
	{ value: '/batch_fish.svg', label: 'Blue profile picture' },
	{ value: '/batch_penguin.svg', label: 'Lime profile picture' },
	{ value: '/batch_cat.svg', label: 'Orange profile picture' }
] as const;

export type ProfilePicture = (typeof profilePictureOptions)[number]['value'];

export type UserSettings = {
	themePreference: ThemePreference;
	profilePicture: ProfilePicture;
};

export type UserSettingKey = keyof UserSettings;

type SettingDefinition<K extends UserSettingKey> = {
	defaultValue: UserSettings[K];
	validate: (value: unknown) => value is UserSettings[K];
};

export const settingsDefinitions: { [K in UserSettingKey]: SettingDefinition<K> } = {
	themePreference: {
		defaultValue: 'light',
		validate: (value): value is ThemePreference => value === 'light' || value === 'dark'
	},
	profilePicture: {
		defaultValue: '/batch_dog.svg',
		validate: (value): value is ProfilePicture =>
			typeof value === 'string' && profilePictureOptions.some((option) => option.value === value)
	}
};

export function isUserSettingKey(value: string): value is UserSettingKey {
	return Object.hasOwn(settingsDefinitions, value);
}

export function getDefaultUserSettings(): UserSettings {
	return {
		themePreference: settingsDefinitions.themePreference.defaultValue,
		profilePicture: settingsDefinitions.profilePicture.defaultValue
	};
}

export function sanitizeUserSettings(raw: unknown): UserSettings {
	const defaults = getDefaultUserSettings();
	if (!raw || typeof raw !== 'object') {
		return defaults;
	}

	const input = raw as Partial<Record<UserSettingKey, unknown>>;
	const output: UserSettings = { ...defaults };

	if (settingsDefinitions.themePreference.validate(input.themePreference)) {
		output.themePreference = input.themePreference;
	}
	if (settingsDefinitions.profilePicture.validate(input.profilePicture)) {
		output.profilePicture = input.profilePicture;
	}

	return output;
}
