import { render } from 'svelte/server';
import { describe, expect, it } from 'vitest';
import ChatMarkdown from './ChatMarkdown.svelte';

describe('ChatMarkdown', () => {
	it('does not render raw interactive HTML from a model response', () => {
		const { body } = render(ChatMarkdown, {
			props: {
				source:
					'# Safe heading\n\n<iframe src="https://example.invalid"></iframe><form><button>Submit</button></form>'
			}
		});

		expect(body).toContain('Safe heading');
		expect(body).not.toContain('<iframe');
		expect(body).not.toContain('<form');
		expect(body).not.toContain('<button');
	});
});
