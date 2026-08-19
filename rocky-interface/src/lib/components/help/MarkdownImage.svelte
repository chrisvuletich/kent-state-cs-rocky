<script lang="ts">
	import { focusScope } from '$lib/actions/focusScope';

	interface Props {
		href?: string;
		title?: string;
		text?: string;
	}

	const { href = '', title = undefined, text = '' }: Props = $props();
	let expanded = $state(false);
	let aspectRatio = $state('16 / 9');
	let previewButton = $state<HTMLButtonElement>();

	function openImage() {
		expanded = true;
	}

	function closeImage() {
		expanded = false;
	}

	function rememberImageDimensions(event: Event) {
		const image = event.currentTarget;
		if (image instanceof HTMLImageElement && image.naturalWidth > 0 && image.naturalHeight > 0) {
			aspectRatio = `${image.naturalWidth} / ${image.naturalHeight}`;
		}
	}

	function closeOnBackdrop(event: MouseEvent) {
		if (event.target === event.currentTarget) {
			closeImage();
		}
	}
</script>

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
		tabindex="-1"
		onclick={closeOnBackdrop}
		use:focusScope={{ onEscape: closeImage, returnFocusTo: previewButton }}
	>
		<div class="markdown-image-dialog-content">
			<button
				type="button"
				class="markdown-image-close"
				data-autofocus
				aria-label="Close full-size image"
				onclick={closeImage}>×</button
			>
			<img src={href} {title} alt={text} />
		</div>
	</dialog>
{/if}
