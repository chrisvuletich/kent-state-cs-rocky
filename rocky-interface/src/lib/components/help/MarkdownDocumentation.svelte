<script lang="ts">
	import { onMount } from 'svelte';
	import SvelteMarkdown from '@humanspeak/svelte-markdown';

	export let sourcePath: string;

	let content = '';
	let error = '';
	let loading = true;

	onMount(async () => {
		try {
			const response = await fetch(sourcePath);
			if (!response.ok) throw new Error(`Unable to load documentation (${response.status}).`);
			content = await response.text();
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
	<article class="api-doc markdown-documentation">
		<SvelteMarkdown source={content} />
	</article>
{/if}
