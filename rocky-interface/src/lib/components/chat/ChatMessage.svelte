<script lang="ts">
	import { IconCheck, IconCopy } from '@tabler/icons-svelte';
	import { onDestroy } from 'svelte';
	import ChatMarkdown from '$lib/components/chat/ChatMarkdown.svelte';
	import type { ChatMessage } from '$lib/types/chat';

	export let message: ChatMessage;

	let copied = false;
	let copyTimer: ReturnType<typeof setTimeout> | undefined;

	async function copyResponse() {
		try {
			await navigator.clipboard.writeText(message.content);
			copied = true;
			clearTimeout(copyTimer);
			copyTimer = setTimeout(() => (copied = false), 1500);
		} catch {
			copied = false;
		}
	}

	onDestroy(() => clearTimeout(copyTimer));
</script>

<article
	class:chat-message-user={message.role === 'user'}
	class:chat-message-assistant={message.role === 'assistant'}
	class:chat-message-failed={message.state === 'failed'}
	class="chat-message"
>
	{#if message.role === 'assistant'}
		<div class="chat-avatar" aria-hidden="true">
			<img src="/rocky.svg" alt="" />
		</div>
		<div class="chat-message-content">
			<ChatMarkdown source={message.content} />
			<div class="chat-message-actions">
				<button
					type="button"
					onclick={copyResponse}
					aria-label={copied ? "Rocky's response copied" : "Copy Rocky's response"}
				>
					{#if copied}<IconCheck size={16} />{:else}<IconCopy size={16} />{/if}
					<span aria-live="polite">{copied ? 'Copied' : 'Copy'}</span>
				</button>
			</div>
		</div>
	{:else}
		<div class="chat-user-bubble">
			{message.content}
			{#if message.state === 'failed'}
				<span class="chat-message-state">Not answered</span>
			{/if}
		</div>
	{/if}
</article>
