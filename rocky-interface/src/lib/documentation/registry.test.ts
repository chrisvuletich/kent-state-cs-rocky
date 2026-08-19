import { describe, expect, it } from 'vitest';
import { canViewDocumentation, documentation } from './registry';

const documentById = (id: string) => {
	const document = documentation.find((candidate) => candidate.id === id);
	if (!document) throw new Error(`Missing documentation fixture: ${id}`);
	return document;
};

describe('documentation audiences', () => {
	it('keeps developer guides available to every signed-in role', () => {
		expect(canViewDocumentation(documentById('intro'), { role: 'student' })).toBe(true);
	});

	it('shows course workflow guidance to instructors without exposing admin-only guides', () => {
		const instructor = { role: 'instructor' };
		expect(canViewDocumentation(documentById('course-roster'), instructor)).toBe(true);
		expect(canViewDocumentation(documentById('user-management'), instructor)).toBe(false);
		expect(canViewDocumentation(documentById('api-key-management'), instructor)).toBe(false);
		expect(canViewDocumentation(documentById('admin-dashboard'), instructor)).toBe(false);
	});

	it('allows administrators to open every administration guide', () => {
		const administrator = { role: 'admin', isAdmin: true };
		for (const document of documentation.filter(({ category }) => category === 'administration')) {
			expect(canViewDocumentation(document, administrator)).toBe(true);
		}
	});
});
