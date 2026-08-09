<script lang="ts">
	import {
		IconChevronLeft,
		IconChevronRight,
		IconMessagePlus,
		IconPlus,
		IconSearch,
		IconX
	} from '@tabler/icons-svelte';
	import {
		conversationLabel,
		formatConversationTime,
		groupConversations
	} from '$lib/chat/conversations';
	import type { ChatConversation } from '$lib/types/chat';

	export let conversations: ChatConversation[];
	export let activeConversationId: string;
	export let loading = false;
	export let loadingConversationId = '';
	export let busy = false;
	export let error = '';
	export let collapsed = false;
	export let mobile = false;
	export let onNewChat: () => void;
	export let onSelectConversation: (conversationId: string) => void;
	export let onToggle: () => void;

	let query = '';
	let closeButton: HTMLButtonElement;
	let panel: HTMLElement;
	$: groups = groupConversations(conversations, query);

	export function focusCloseButton() {
		closeButton?.focus();
	}

	function trapFocus(event: KeyboardEvent) {
		if (!mobile || collapsed || event.key !== 'Tab' || !panel) return;
		const focusable = Array.from(
			panel.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled)')
		).filter((element) => element.offsetParent !== null);
		if (focusable.length === 0) return;
		const first = focusable[0];
		const last = focusable[focusable.length - 1];
		if (event.shiftKey && document.activeElement === first) {
			event.preventDefault();
			last.focus();
		} else if (!event.shiftKey && document.activeElement === last) {
			event.preventDefault();
			first.focus();
		}
	}
</script>

{#if !collapsed}
	<button
		class="chat-history-backdrop"
		type="button"
		onclick={onToggle}
		tabindex="-1"
		aria-hidden="true"
	></button>
{/if}

<aside
	bind:this={panel}
	class:chat-history-collapsed={collapsed}
	class:chat-history-open={!collapsed}
	class="chat-history"
	role={mobile && !collapsed ? 'dialog' : undefined}
	aria-modal={mobile && !collapsed ? 'true' : undefined}
	aria-label="Chat history"
	onkeydown={trapFocus}
>
	<div class="chat-history-heading">
		{#if !collapsed}<strong>Chat History</strong>{/if}
		<button
			bind:this={closeButton}
			class="chat-icon-button chat-history-toggle"
			type="button"
			onclick={onToggle}
			aria-label={collapsed ? 'Open chat history' : 'Close chat history'}
			title={collapsed ? 'Open chat history' : 'Close chat history'}
		>
			{#if collapsed}<IconChevronRight size={19} />{:else}<IconChevronLeft size={19} />{/if}
		</button>
	</div>

	{#if collapsed}
		<button
			class="chat-collapsed-new"
			type="button"
			onclick={onNewChat}
			disabled={busy}
			aria-label="New chat"
			title="New chat"
		>
			<IconMessagePlus size={20} />
		</button>
	{:else}
		<button class="chat-new-button" type="button" onclick={onNewChat} disabled={busy}>
			<IconPlus size={18} />
			<span>New chat</span>
		</button>

		<div class="chat-history-search">
			<label class="sr-only" for="rocky-conversation-search">Search conversations</label>
			<IconSearch size={17} aria-hidden="true" />
			<input
				id="rocky-conversation-search"
				bind:value={query}
				type="search"
				placeholder="Search conversations"
			/>
			{#if query}
				<button type="button" onclick={() => (query = '')} aria-label="Clear conversation search"
					><IconX size={15} /></button
				>
			{/if}
		</div>

		<div class="chat-history-list">
			{#if loading}
				<div class="chat-history-state" role="status">Loading conversations…</div>
			{:else if error}
				<div class="chat-history-state chat-history-error">{error}</div>
			{:else if groups.length === 0}
				<div class="chat-history-state">
					{query ? 'No conversations match your search.' : 'Your conversations will appear here.'}
				</div>
			{:else}
				{#each groups as group}
					<section
						class="chat-history-group"
						aria-labelledby={`chat-group-${group.label.replaceAll(' ', '-').toLowerCase()}`}
					>
						<h2 id={`chat-group-${group.label.replaceAll(' ', '-').toLowerCase()}`}>
							{group.label}
						</h2>
						<div>
							{#each group.conversations as conversation (conversation.conversation_id)}
								<button
									class:active={conversation.conversation_id === activeConversationId}
									class="chat-history-item"
									type="button"
									onclick={() => onSelectConversation(conversation.conversation_id)}
									disabled={busy || loadingConversationId === conversation.conversation_id}
									aria-busy={loadingConversationId === conversation.conversation_id}
									aria-current={conversation.conversation_id === activeConversationId
										? 'true'
										: undefined}
								>
									<span class="chat-history-item-title" title={conversationLabel(conversation)}
										>{conversationLabel(conversation)}</span
									>
									<span class="chat-history-item-time">{formatConversationTime(conversation)}</span>
								</button>
							{/each}
						</div>
					</section>
				{/each}
			{/if}
		</div>
	{/if}
</aside>
