import { get } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
	clearFeedback,
	feedbackMessage,
	showErrorFeedback,
	showFeedback,
	showSuccessFeedback
} from './feedbackStore';

beforeEach(() => {
	vi.useFakeTimers();
	clearFeedback();
});

afterEach(() => {
	clearFeedback();
	vi.useRealTimers();
});

describe('feedback store', () => {
	it('publishes trimmed success and error messages', () => {
		showSuccessFeedback('  Saved successfully.  ');
		expect(get(feedbackMessage)).toMatchObject({
			kind: 'success',
			message: 'Saved successfully.'
		});

		showErrorFeedback('Unable to save.');
		expect(get(feedbackMessage)).toMatchObject({
			kind: 'error',
			message: 'Unable to save.'
		});
	});

	it('ignores blank messages without clearing the current feedback', () => {
		showSuccessFeedback('Current message');
		const current = get(feedbackMessage);

		showFeedback('error', '   ');
		expect(get(feedbackMessage)).toEqual(current);
	});

	it('clears feedback after its duration', () => {
		showErrorFeedback('Temporary error', 1000);

		vi.advanceTimersByTime(999);
		expect(get(feedbackMessage)?.message).toBe('Temporary error');
		vi.advanceTimersByTime(1);
		expect(get(feedbackMessage)).toBeNull();
	});

	it('restarts the timer when a newer message replaces an older one', () => {
		showSuccessFeedback('First', 1000);
		vi.advanceTimersByTime(750);
		showSuccessFeedback('Second', 1000);
		vi.advanceTimersByTime(250);

		expect(get(feedbackMessage)?.message).toBe('Second');
		vi.advanceTimersByTime(750);
		expect(get(feedbackMessage)).toBeNull();
	});

	it('can be cleared immediately without leaving an active timer', () => {
		showSuccessFeedback('Saved', 1000);
		clearFeedback();

		expect(get(feedbackMessage)).toBeNull();
		expect(vi.getTimerCount()).toBe(0);
	});
});
