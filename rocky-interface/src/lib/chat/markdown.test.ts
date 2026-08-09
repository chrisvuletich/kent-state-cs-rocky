import { describe, expect, it } from 'vitest';
import { defaultRenderers } from '@humanspeak/svelte-markdown';
import { chatMarkdownRenderers } from './markdown';

describe('chat markdown renderers', () => {
	it('blocks raw interactive HTML while preserving normal markdown renderers', () => {
		expect(chatMarkdownRenderers.code).toBeDefined();
		expect(chatMarkdownRenderers.link).toBeDefined();
		expect(chatMarkdownRenderers.html?.iframe).toBeDefined();
		expect(chatMarkdownRenderers.html?.form).toBeDefined();
		expect(chatMarkdownRenderers.html?.iframe).not.toBe(defaultRenderers.html?.iframe);
		expect(chatMarkdownRenderers.html?.form).not.toBe(defaultRenderers.html?.form);
	});
});
