<script lang="ts">
	import { onMount } from 'svelte';
	import SvelteMarkdown, { defaultRenderers } from '@humanspeak/svelte-markdown';
	import MarkdownCodeBlock from '$lib/components/help/MarkdownCodeBlock.svelte';
	import MarkdownImage from '$lib/components/help/MarkdownImage.svelte';
	import MarkdownTable from '$lib/components/help/MarkdownTable.svelte';

	export let sourcePath: string;
	export let documentTitle: string;

	let content = '';
	let error = '';
	let loading = true;
	const renderers = {
		...defaultRenderers,
		code: MarkdownCodeBlock,
		image: MarkdownImage,
		table: MarkdownTable
	};

	function removeDuplicateDocumentTitle(markdown: string): string {
		return markdown.replace(/^\uFEFF?#\s+[^\r\n]+(?:\r?\n+|$)/, '');
	}

	onMount(async () => {
		try {
			const response = await fetch(sourcePath);
			if (!response.ok) throw new Error(`Unable to load documentation (${response.status}).`);
			content = removeDuplicateDocumentTitle(await response.text());
		} catch (reason) {
			error = reason instanceof Error ? reason.message : 'Unable to load documentation.';
		} finally {
			loading = false;
		}
	});
</script>

{#if loading}
	<div class="documentation-message">Loading documentation…</div>
{:else if error}
	<div class="documentation-message documentation-error">{error}</div>
{:else}
	<article class="api-doc markdown-documentation" aria-label={documentTitle}>
		<SvelteMarkdown source={content} {renderers} />
	</article>
{/if}
