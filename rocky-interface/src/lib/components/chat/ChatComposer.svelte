<script lang="ts">
	import { tick } from 'svelte';
	import { IconPaperclip, IconPlayerStop, IconSend2, IconX } from '@tabler/icons-svelte';
	import type { ChatImage } from '$lib/types/chat';

	export let value = '';
	export let sending = false;
	export let disabled = false;
	export let disabledReason = '';
	export let images: ChatImage[] = [];
	export let imageInputEnabled = false;
	export let addingImages = false;
	export let maxImages = 0;
	export let onSend: () => void;
	export let onStop: () => void;
	export let onAddImages: (files: File[]) => void;
	export let onRemoveImage: (imageId: string) => void;

	let textarea: HTMLTextAreaElement;
	let fileInput: HTMLInputElement;
	let dragActive = false;

	function resize() {
		if (!textarea) return;
		textarea.style.height = 'auto';
		textarea.style.height = `${Math.min(textarea.scrollHeight, 184)}px`;
	}

	function handleInput() {
		resize();
	}

	function handleKeydown(event: KeyboardEvent) {
		if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return;
		event.preventDefault();
		if (!sending && !disabled && !addingImages && (value.trim() || images.length > 0)) onSend();
	}

	function addFiles(files: FileList | null) {
		if (!imageInputEnabled || sending || !files?.length) return;
		onAddImages(Array.from(files));
	}

	function handleFileSelection(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		addFiles(input.files);
		input.value = '';
	}

	function handlePaste(event: ClipboardEvent) {
		const imageFiles = Array.from(event.clipboardData?.files || []).filter((file) =>
			file.type.startsWith('image/')
		);
		if (!imageInputEnabled || sending || imageFiles.length === 0) return;
		event.preventDefault();
		onAddImages(imageFiles);
	}

	function handleDragOver(event: DragEvent) {
		if (!imageInputEnabled || sending || !event.dataTransfer?.types.includes('Files')) {
			return;
		}
		event.preventDefault();
		dragActive = true;
	}

	function handleDragLeave(event: DragEvent) {
		const composer = event.currentTarget as HTMLElement;
		if (!composer.contains(event.relatedTarget as Node | null)) dragActive = false;
	}

	function handleDrop(event: DragEvent) {
		if (!imageInputEnabled || sending || !event.dataTransfer?.files.length) return;
		event.preventDefault();
		dragActive = false;
		onAddImages(Array.from(event.dataTransfer.files));
	}

	export async function focus() {
		await tick();
		textarea?.focus();
		resize();
	}

	export async function resetHeight() {
		await tick();
		resize();
	}
</script>

<div class="chat-composer-region">
	<p id="rocky-chat-logging-notice" class="chat-privacy-note">
		Rocky AI is an academic system with no expectation of privacy. All prompts, attached images, and
		responses are logged and may be reviewed by university administrators. Do not share sensitive
		personal information.
	</p>
	<div
		class:chat-composer-dragging={dragActive}
		class="chat-composer"
		role="group"
		aria-label="Message composer"
		ondragover={handleDragOver}
		ondragleave={handleDragLeave}
		ondrop={handleDrop}
	>
		{#if images.length > 0}
			<div class="chat-attachment-previews" aria-label="Attached images">
				{#each images as image (image.id)}
					<figure class="chat-attachment-preview">
						<img
							src={image.imageUrl}
							alt={image.name ? `Preview of ${image.name}` : 'Image preview'}
						/>
						<button
							type="button"
							onclick={() => onRemoveImage(image.id)}
							disabled={sending || addingImages}
							aria-label={`Remove ${image.name || 'attached image'}`}
							title="Remove image"
						>
							<IconX size={15} />
						</button>
						<figcaption>{image.name || 'Image'}</figcaption>
					</figure>
				{/each}
			</div>
		{/if}
		<label class="sr-only" for="rocky-chat-input">Ask Rocky a question</label>
		<textarea
			id="rocky-chat-input"
			bind:this={textarea}
			bind:value
			rows="1"
			placeholder="Ask Rocky a question"
			aria-describedby="rocky-chat-logging-notice"
			oninput={handleInput}
			onkeydown={handleKeydown}
			onpaste={handlePaste}
		></textarea>
		<div class="chat-composer-footer">
			<div class="chat-composer-tools">
				{#if imageInputEnabled}
					<input
						bind:this={fileInput}
						class="sr-only"
						type="file"
						accept="image/jpeg,image/png,image/webp"
						multiple
						disabled={sending || addingImages || images.length >= maxImages}
						onchange={handleFileSelection}
					/>
					<button
						class="chat-attach-button"
						type="button"
						onclick={() => fileInput?.click()}
						disabled={sending || addingImages || images.length >= maxImages}
						aria-label="Attach images"
						title={`Attach JPEG, PNG, or WebP images (${images.length}/${maxImages})`}
					>
						<IconPaperclip size={18} />
					</button>
				{/if}
				<span class="chat-composer-guidance">
					{addingImages ? 'Preparing images…' : 'Enter to send · Shift+Enter for a new line'}
				</span>
			</div>
			<button
				class:chat-stop-button={sending}
				type="button"
				onclick={sending ? onStop : onSend}
				disabled={!sending && (disabled || addingImages || (!value.trim() && images.length === 0))}
				aria-label={sending
					? 'Stop waiting for response'
					: disabled && disabledReason
						? `Send message unavailable: ${disabledReason}`
						: 'Send message'}
				title={sending
					? 'Stop waiting'
					: disabled
						? disabledReason || 'Sending is unavailable'
						: 'Send message'}
			>
				{#if sending}<IconPlayerStop size={20} />{:else}<IconSend2 size={20} />{/if}
			</button>
		</div>
	</div>
</div>
