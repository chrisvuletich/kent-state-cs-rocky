import { writable } from 'svelte/store';

export type FeedbackKind = 'success' | 'error';

export type FeedbackMessage = {
	id: number;
	kind: FeedbackKind;
	message: string;
};

const DEFAULT_DURATION_MS = 3500;

let nextId = 1;
let clearTimer: ReturnType<typeof setTimeout> | null = null;

export const feedbackMessage = writable<FeedbackMessage | null>(null);

export function clearFeedback(): void {
	if (clearTimer) {
		clearTimeout(clearTimer);
		clearTimer = null;
	}

	feedbackMessage.set(null);
}

export function showFeedback(
	kind: FeedbackKind,
	message: string,
	durationMs = DEFAULT_DURATION_MS
): void {
	if (!message.trim()) {
		return;
	}

	if (clearTimer) {
		clearTimeout(clearTimer);
		clearTimer = null;
	}

	feedbackMessage.set({
		id: nextId++,
		kind,
		message: message.trim()
	});

	clearTimer = setTimeout(() => {
		feedbackMessage.set(null);
		clearTimer = null;
	}, durationMs);
}

export function showSuccessFeedback(message: string, durationMs?: number): void {
	showFeedback('success', message, durationMs);
}

export function showErrorFeedback(message: string, durationMs?: number): void {
	showFeedback('error', message, durationMs);
}
