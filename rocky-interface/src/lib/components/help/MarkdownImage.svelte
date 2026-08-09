<script lang="ts">
	import { tick } from 'svelte';

	interface Props {
		href?: string;
		title?: string;
		text?: string;
	}

	const { href = '', title = undefined, text = '' }: Props = $props();
	let expanded = $state(false);
	let aspectRatio = $state('16 / 9');
	let previewButton = $state<HTMLButtonElement>();
	let closeButton = $state<HTMLButtonElement>();

	async function openImage() {
		expanded = true;
		await tick();
		closeButton?.focus();
	}

	async function closeImage() {
		expanded = false;
		await tick();
		previewButton?.focus();
	}

	function rememberImageDimensions(event: Event) {
		const image = event.currentTarget;
		if (image instanceof HTMLImageElement && image.naturalWidth > 0 && image.naturalHeight > 0) {
			aspectRatio = `${image.naturalWidth} / ${image.naturalHeight}`;
		}
	}

	function closeOnBackdrop(event: MouseEvent) {
		if (event.target === event.currentTarget) {
			void closeImage();
		}
	}

	function handleKeydown(event: KeyboardEvent) {
		if (expanded && event.key === 'Escape') {
			void closeImage();
		}
	}
</script>

<svelte:window onkeydown={handleKeydown} />

<figure class="markdown-image-figure">
	<button
		bind:this={previewButton}
		type="button"
		class="markdown-image-preview"
		style={`aspect-ratio: ${aspectRatio};`}
		aria-label={`Open full-size image: ${text || title || 'documentation image'}`}
		aria-expanded={expanded}
		onclick={openImage}
	>
		<img src={href} {title} alt={text} loading="lazy" onload={rememberImageDimensions} />
		<span class="markdown-image-hint" aria-hidden="true">View full size</span>
	</button>
	{#if text}
		<figcaption>{text}</figcaption>
	{/if}
</figure>

{#if expanded}
	<dialog
		open
		class="markdown-image-dialog"
		aria-modal="true"
		aria-label={text || title || 'Full-size documentation image'}
		onclick={closeOnBackdrop}
	>
		<div class="markdown-image-dialog-content">
			<button
				bind:this={closeButton}
				type="button"
				class="markdown-image-close"
				aria-label="Close full-size image"
				onclick={closeImage}>×</button
			>
			<img src={href} {title} alt={text} />
		</div>
	</dialog>
{/if}
