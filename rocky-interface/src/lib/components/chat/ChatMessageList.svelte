<script lang="ts">
	import { IconChevronDown } from '@tabler/icons-svelte';
	import ChatMessage from '$lib/components/chat/ChatMessage.svelte';
	import type { ChatMessage as ChatMessageType } from '$lib/types/chat';

	export let messages: ChatMessageType[];
	export let sending = false;

	let container: HTMLDivElement;
	let showJumpToLatest = false;

	function updateScrollState() {
		if (!container) return;
		const distanceFromBottom =
			container.scrollHeight - container.scrollTop - container.clientHeight;
		showJumpToLatest = distanceFromBottom > 180;
	}

	export function isNearBottom(): boolean {
		if (!container) return true;
		return container.scrollHeight - container.scrollTop - container.clientHeight < 180;
	}

	export function scrollToBottom(behavior: ScrollBehavior = 'smooth') {
		if (!container) return;
		container.scrollTo({ top: container.scrollHeight, behavior });
		showJumpToLatest = false;
	}

	export function scrollToTop() {
		if (!container) return;
		container.scrollTo({ top: 0, behavior: 'auto' });
		showJumpToLatest = false;
	}
</script>

<div class="chat-message-scroll" bind:this={container} onscroll={updateScrollState}>
	<div class="chat-message-column" aria-busy={sending}>
		{#each messages as message (message.id)}
			<ChatMessage {message} />
		{/each}

		{#if sending}
			<div class="chat-generating" role="status">
				<div class="chat-avatar" aria-hidden="true"><img src="/rocky.svg" alt="" /></div>
				<div class="chat-thinking-dots" aria-label="Rocky is generating a response">
					<span></span><span></span><span></span>
				</div>
			</div>
		{/if}
	</div>
	<p class="sr-only" aria-live="polite">
		{sending
			? 'Rocky is generating a response.'
			: messages.at(-1)?.role === 'assistant'
				? 'Rocky added a response.'
				: ''}
	</p>

	{#if showJumpToLatest}
		<button class="chat-jump-latest" type="button" onclick={() => scrollToBottom()}>
			<IconChevronDown size={18} />
			<span>Latest</span>
		</button>
	{/if}
</div>
