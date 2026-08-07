import { API_BASE_URL } from '$lib/config/env';
import { sanitizeUserSettings, type UserSettingKey, type UserSettings } from '$lib/settings/userSettings';
import type { User } from '$lib/types/user';
import { internalProxyHeaders } from '$lib/server/backendSecurity';

function buildIdentity(user: User): { userId: string; email: string } {
	return {
		userId: user.id,
		email: user.email
	};
}

function buildHeaders(user: User): HeadersInit {
	return {
		Accept: 'application/json',
		'Content-Type': 'application/json',
		'X-Rocky-User-Email': user.email,
		'X-Rocky-User-Is-Admin': String(user.isAdmin),
		...internalProxyHeaders()
	};
}

async function parseRemoteSettingsResponse(response: Response): Promise<UserSettings> {
	if (!response.ok) {
		throw new Error(`Remote user-settings request failed (${response.status}).`);
	}

	const payload = (await response.json()) as Partial<{ settings: unknown }>;
	return sanitizeUserSettings(payload.settings);
}

export async function getSettingsForUser(user: User): Promise<UserSettings> {
	const identity = buildIdentity(user);
	const query = new URLSearchParams(identity);
	const response = await fetch(`${API_BASE_URL}/user-settings?${query.toString()}`, {
		method: 'GET',
		headers: buildHeaders(user),
		cache: 'no-store'
	});

	return parseRemoteSettingsResponse(response);
}

export async function updateSettingForUser<K extends UserSettingKey>(
	user: User,
	key: K,
	value: UserSettings[K]
): Promise<UserSettings> {
	const identity = buildIdentity(user);
	const response = await fetch(`${API_BASE_URL}/user-settings/${key}`, {
		method: 'PATCH',
		headers: buildHeaders(user),
		body: JSON.stringify({ ...identity, value })
	});

	return parseRemoteSettingsResponse(response);
}

export async function updateSettingsPatchForUser(user: User, patch: Partial<UserSettings>): Promise<UserSettings> {
	const identity = buildIdentity(user);
	const response = await fetch(`${API_BASE_URL}/user-settings`, {
		method: 'PATCH',
		headers: buildHeaders(user),
		body: JSON.stringify({ ...identity, patch })
	});

	return parseRemoteSettingsResponse(response);
}
