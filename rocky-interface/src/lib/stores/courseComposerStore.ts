import { writable } from 'svelte/store';

export type CourseComposerState = {
	isOpen: boolean;
	returnFocusTo: HTMLElement | null;
};

const DEFAULT_STATE: CourseComposerState = {
	isOpen: false,
	returnFocusTo: null
};

export const courseComposerState = writable<CourseComposerState>(DEFAULT_STATE);

export function openCourseComposer(returnFocusTo?: HTMLElement | null): void {
	courseComposerState.set({
		isOpen: true,
		returnFocusTo:
			returnFocusTo ??
			(typeof document !== 'undefined' && document.activeElement instanceof HTMLElement
				? document.activeElement
				: null)
	});
}

export function closeCourseComposer(): void {
	courseComposerState.set(DEFAULT_STATE);
}
