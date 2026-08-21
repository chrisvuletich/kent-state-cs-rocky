import type { UserSettingKey, UserSettings } from '$lib/settings/userSettings';
import { showErrorFeedback, showSuccessFeedback } from '$lib/stores/feedbackStore';

const USER_SAFE_ACTION_FAILURE = 'Action failed. Please try again.';

async function parseResponse<T>(response: Response, action: string): Promise<T> {
	if (!response.ok) {
		const raw = await response.text().catch(() => '');
		console.error('[user settings api] request failed', { action, status: response.status, raw });
		throw new Error(USER_SAFE_ACTION_FAILURE);
	}

	return (await response.json()) as T;
}

export async function updateCurrentUserSetting<K extends UserSettingKey>(
	key: K,
	value: UserSettings[K]
): Promise<UserSettings> {
	try {
		const response = await fetch(`/api/user-settings/${key}`, {
			method: 'PATCH',
			headers: {
				'Content-Type': 'application/json',
				Accept: 'application/json'
			},
			body: JSON.stringify({ value })
		});

		const payload = await parseResponse<{ settings: UserSettings }>(
			response,
			`Update user setting "${key}"`
		);
		showSuccessFeedback('Setting updated successfully.');
		return payload.settings;
	} catch (err) {
		const message =
			err instanceof Error && err.message.trim() ? err.message : 'Unable to update setting.';
		showErrorFeedback(message);
		throw err;
	}
}
