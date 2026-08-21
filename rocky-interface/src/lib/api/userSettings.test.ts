import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const feedbackMocks = vi.hoisted(() => ({
	showErrorFeedback: vi.fn(),
	showSuccessFeedback: vi.fn()
}));

vi.mock('$lib/stores/feedbackStore', () => feedbackMocks);

import { updateCurrentUserSetting } from './userSettings';

beforeEach(() => {
	feedbackMocks.showErrorFeedback.mockReset();
	feedbackMocks.showSuccessFeedback.mockReset();
});

afterEach(() => {
	vi.restoreAllMocks();
	vi.unstubAllGlobals();
});

describe('updateCurrentUserSetting', () => {
	it('patches one setting and reports success', async () => {
		const settings = { themePreference: 'dark', profilePicture: '/batch_dog.svg' } as const;
		const fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			json: async () => ({ settings })
		});
		vi.stubGlobal('fetch', fetchMock);

		await expect(updateCurrentUserSetting('themePreference', 'dark')).resolves.toEqual(settings);
		expect(fetchMock).toHaveBeenCalledWith('/api/user-settings/themePreference', {
			method: 'PATCH',
			headers: {
				'Content-Type': 'application/json',
				Accept: 'application/json'
			},
			body: JSON.stringify({ value: 'dark' })
		});
		expect(feedbackMocks.showSuccessFeedback).toHaveBeenCalledWith('Setting updated successfully.');
		expect(feedbackMocks.showErrorFeedback).not.toHaveBeenCalled();
	});

	it('reports a safe feedback message when an update fails', async () => {
		vi.spyOn(console, 'error').mockImplementation(() => undefined);
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue({
				ok: false,
				status: 400,
				text: async () => 'invalid value'
			})
		);

		await expect(updateCurrentUserSetting('themePreference', 'dark')).rejects.toThrow(
			'Action failed. Please try again.'
		);
		expect(feedbackMocks.showErrorFeedback).toHaveBeenCalledWith(
			'Action failed. Please try again.'
		);
		expect(feedbackMocks.showSuccessFeedback).not.toHaveBeenCalled();
	});

	it('uses the fallback feedback message for non-Error failures', async () => {
		vi.stubGlobal('fetch', vi.fn().mockRejectedValue('offline'));

		await expect(updateCurrentUserSetting('profilePicture', '/batch_dog.svg')).rejects.toBe(
			'offline'
		);
		expect(feedbackMocks.showErrorFeedback).toHaveBeenCalledWith('Unable to update setting.');
	});
});
