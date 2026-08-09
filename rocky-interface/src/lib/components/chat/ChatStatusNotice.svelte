<script lang="ts">
	import { IconAlertCircle, IconInfoCircle, IconRefresh, IconX } from '@tabler/icons-svelte';

	export let message: string;
	export let canRetry = false;
	export let tone: 'error' | 'info' = 'error';
	export let onRetry: () => void;
	export let onDismiss: () => void;
</script>

{#if message}
	<div
		class:chat-status-info={tone === 'info'}
		class="chat-error-notice"
		role={tone === 'error' ? 'alert' : 'status'}
	>
		{#if tone === 'info'}<IconInfoCircle size={20} aria-hidden="true" />{:else}<IconAlertCircle
				size={20}
				aria-hidden="true"
			/>{/if}
		<p>{message}</p>
		{#if canRetry}
			<button type="button" onclick={onRetry}><IconRefresh size={16} />Edit and try again</button>
		{/if}
		<button
			class="chat-error-dismiss"
			type="button"
			onclick={onDismiss}
			aria-label={tone === 'error' ? 'Dismiss error' : 'Dismiss notice'}><IconX size={17} /></button
		>
	</div>
{/if}
