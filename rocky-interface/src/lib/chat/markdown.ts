import {
	buildUnsupportedHTML,
	defaultRenderers,
	type Renderers
} from '@humanspeak/svelte-markdown';
import MarkdownCodeBlock from '$lib/components/help/MarkdownCodeBlock.svelte';
import ChatMarkdownLink from '$lib/components/chat/ChatMarkdownLink.svelte';

export const chatMarkdownRenderers: Renderers = {
	...defaultRenderers,
	code: MarkdownCodeBlock,
	link: ChatMarkdownLink,
	html: buildUnsupportedHTML()
};
