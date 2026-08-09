<script lang="ts">
	import SvelteMarkdown from '@humanspeak/svelte-markdown';
	import { chatMarkdownRenderers } from '$lib/chat/markdown';

	export let source: string;
</script>

<div class="chat-markdown">
	<SvelteMarkdown {source} renderers={chatMarkdownRenderers} />
</div>
