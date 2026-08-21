import { get } from 'svelte/store';
import { beforeEach, describe, expect, it } from 'vitest';

import {
	closeCourseComposer,
	courseComposerState,
	openCourseComposer
} from './courseComposerStore';

beforeEach(() => {
	closeCourseComposer();
});

describe('course composer store', () => {
	it('opens with an explicit return-focus target', () => {
		const returnFocusTo = {} as HTMLElement;

		openCourseComposer(returnFocusTo);
		expect(get(courseComposerState)).toEqual({ isOpen: true, returnFocusTo });
	});

	it('opens without a focus target when no document is available', () => {
		openCourseComposer();
		expect(get(courseComposerState)).toEqual({ isOpen: true, returnFocusTo: null });
	});

	it('closes and clears the previous focus target', () => {
		openCourseComposer({} as HTMLElement);
		closeCourseComposer();

		expect(get(courseComposerState)).toEqual({ isOpen: false, returnFocusTo: null });
	});
});
