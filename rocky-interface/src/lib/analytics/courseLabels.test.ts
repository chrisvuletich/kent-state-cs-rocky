import { describe, expect, it } from 'vitest';
import { analyticsCourseLabel } from './courseLabels';
import type { Course } from '$lib/types/course';

const course = {
	id: 1,
	code: 'SE 3010',
	name: 'Software Engineering',
	instructor: 'Instructor',
	instructorId: null,
	instructorEmail: null,
	taIds: [],
	taEmails: [],
	semester: 'Fall 2026',
	isActive: true,
	color: '#000000',
	instructorKeyLimit: 2,
	instructorHandoutLimit: 2,
	hasApiKey: false,
	apiKeyOwnerType: null,
	apiKeyOwnerId: null,
	apiKeyGroupCreatedBy: null,
	apiKeyCreated: null,
	members: []
} satisfies Course;

describe('analyticsCourseLabel', () => {
	it('uses a real telemetry code when one is available', () => {
		expect(analyticsCourseLabel({ id: '1', label: 'CS 10001' }, [course])).toBe('CS 10001');
	});

	it('resolves an id-only telemetry row through loaded courses', () => {
		expect(analyticsCourseLabel({ id: '1', label: '1' }, [course])).toBe('SE 3010');
	});

	it('uses a readable final fallback', () => {
		expect(analyticsCourseLabel({ id: '99', label: '' }, [course])).toBe('Course 99');
	});
});
