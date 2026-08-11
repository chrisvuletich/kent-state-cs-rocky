<script lang="ts">
	import { tick } from 'svelte';
	import { IconPlayerStop, IconSend2 } from '@tabler/icons-svelte';

	export let value = '';
	export let sending = false;
	export let disabled = false;
	export let onSend: () => void;
	export let onStop: () => void;

	let textarea: HTMLTextAreaElement;

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
		if (!sending && !disabled && value.trim()) onSend();
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
	<p class="chat-privacy-note">
		All Rocky AI prompts and responses are logged and may be reviewed by university administrators.
		Do not share sensitive personal information.
	</p>
	<div class="chat-composer">
		<label class="sr-only" for="rocky-chat-input">Ask Rocky a question</label>
		<textarea
			id="rocky-chat-input"
			bind:this={textarea}
			bind:value
			rows="1"
			placeholder="Ask Rocky a question"
			oninput={handleInput}
			onkeydown={handleKeydown}
		></textarea>
		<div class="chat-composer-footer">
			<span>Enter to send <span aria-hidden="true">·</span> Shift+Enter for a new line</span>
			<button
				class:chat-stop-button={sending}
				type="button"
				onclick={sending ? onStop : onSend}
				disabled={!sending && (disabled || !value.trim())}
				aria-label={sending ? 'Stop waiting for response' : 'Send message'}
				title={sending ? 'Stop waiting' : disabled ? 'Wait before retrying' : 'Send message'}
			>
				{#if sending}<IconPlayerStop size={20} />{:else}<IconSend2 size={20} />{/if}
			</button>
		</div>
	</div>
</div>
