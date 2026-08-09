<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		children?: Snippet;
	}

	const { children }: Props = $props();
</script>

<!-- svelte-ignore a11y_no_noninteractive_tabindex: keyboard users need to focus horizontally scrollable tables -->
<div
	class="markdown-table-scroll"
	role="region"
	aria-label="Scrollable documentation table"
	tabindex="0"
>
	<table>{@render children?.()}</table>
</div>
