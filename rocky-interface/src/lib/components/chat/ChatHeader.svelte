<script lang="ts">
	import { IconDownload, IconHistory } from '@tabler/icons-svelte';
	import type { ChatAvailability } from '$lib/types/chat';

	export let conversationTitle = '';
	export let availability: ChatAvailability = 'checking';
	export let canExport = false;
	export let exporting = false;
	export let onOpenHistory: () => void;
	export let onExport: () => void;
	let historyButton: HTMLButtonElement;

	$: statusLabel =
		availability === 'available'
			? 'Available'
			: availability === 'unavailable'
				? 'Temporarily unavailable'
				: 'Checking availability';

	export function focusHistoryButton() {
		historyButton?.focus();
	}
</script>

<header class="chat-workspace-header">
	<div class="chat-header-identity">
		<button
			bind:this={historyButton}
			class="chat-icon-button chat-mobile-history-button"
			type="button"
			onclick={onOpenHistory}
			aria-label="Open chat history"
		>
			<IconHistory size={20} />
		</button>
		<div class="chat-header-avatar" aria-hidden="true"><img src="/rocky.svg" alt="" /></div>
		<div class="chat-header-copy">
			<div class="chat-header-title-row">
				<h1>{conversationTitle || 'Rocky AI'}</h1>
				{#if conversationTitle}<span>Rocky AI</span>{/if}
			</div>
			<p>Kent State Computer Science Assistant</p>
			<div
				class:available={availability === 'available'}
				class:unavailable={availability === 'unavailable'}
				class="chat-availability"
				role="status"
				aria-live="polite"
			>
				<span aria-hidden="true"></span>{statusLabel}
			</div>
		</div>
	</div>

	{#if canExport}
		<button
			class="chat-header-action"
			type="button"
			onclick={onExport}
			disabled={exporting}
			aria-label={exporting ? 'Exporting conversation' : 'Export conversation'}
		>
			<IconDownload size={18} />
			<span>{exporting ? 'Exporting…' : 'Export'}</span>
		</button>
	{/if}
</header>
