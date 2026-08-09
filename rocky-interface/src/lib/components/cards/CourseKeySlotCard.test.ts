import { render } from 'svelte/server';
import { describe, expect, it } from 'vitest';
import CourseKeySlotCard from './CourseKeySlotCard.svelte';

describe('CourseKeySlotCard', () => {
	it('renders an empty slot without a fake masked key or removal control', () => {
		const { body } = render(CourseKeySlotCard, {
			props: {
				title: 'Personal Key 1',
				keyName: 'key-1',
				hasExistingKey: false,
				maskedPreview: ''
			}
		});

		expect(body).toContain('No key exists for this slot yet.');
		expect(body).not.toContain('sk_kent_');
		expect(body).not.toContain('Remove Key');
	});

	it('renders masked state and management controls for an existing key', () => {
		const { body } = render(CourseKeySlotCard, {
			props: {
				title: 'Instructor Key 1',
				keyName: 'key-1',
				hasExistingKey: true,
				maskedPreview: 'sk_kent_******************************',
				showToggleActive: true
			}
		});

		expect(body).toContain('sk_kent_******************************');
		expect(body).toContain('Remove Key');
		expect(body).toContain('Deactivate Key');
	});

	it('renders a custom read-only explanation without key management controls', () => {
		const { body } = render(CourseKeySlotCard, {
			props: {
				title: 'Team Alpha Key 1',
				keyName: 'key-1',
				hasExistingKey: true,
				maskedPreview: 'sk_kent_******************************',
				readOnly: true,
				readOnlyMessage: 'Group keys are managed by your course instructor or teaching assistant.'
			}
		});

		expect(body).toContain(
			'Group keys are managed by your course instructor or teaching assistant.'
		);
		expect(body).not.toContain('Regenerate Key');
		expect(body).not.toContain('Remove Key');
	});
});
