<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		href?: string;
		title?: string;
		children?: Snippet;
	}

	let { href, title, children }: Props = $props();
	let external = $derived(Boolean(href && /^(https?:)?\/\//i.test(href)));
</script>

<a
	{href}
	{title}
	target={external ? '_blank' : undefined}
	rel={external ? 'noopener noreferrer' : undefined}
>
	{@render children?.()}
</a>
