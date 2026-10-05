<script lang="ts">
	import { focusScope } from '$lib/actions/focusScope';
	import '$lib/styles/components/modules/popup.css';
	export let title: string;
	export let description: string;
	export let confirmLabel: string;
	export let onConfirm: () => Promise<void>;
	export let onClose: () => void;
	let busy = false;
	let error: string | null = null;
	function close() {
		if (!busy) onClose();
	}
	async function confirm() {
		if (busy) return;
		busy = true;
		error = null;
		try {
			await onConfirm();
		} catch (err) {
			error = err instanceof Error ? err.message : 'Unable to save. Please try again.';
		} finally {
			busy = false;
		}
	}
</script>

<div
	class="popup-backdrop"
	role="presentation"
	onclick={(event) => {
		if (event.target === event.currentTarget) close();
	}}
>
	<div
		class="popup-card"
		role="dialog"
		aria-modal="true"
		aria-labelledby="group-action-title"
		aria-describedby="group-action-description"
		tabindex="-1"
		use:focusScope={{ initialFocus: '#group-action-cancel', onEscape: close }}
	>
		<h3 id="group-action-title">{title}</h3>
		<p id="group-action-description">{description}</p>
		{#if error}<p class="popup-error" role="alert">{error}</p>{/if}
		<div class="popup-actions">
			<button
				id="group-action-cancel"
				type="button"
				class="view-btn"
				disabled={busy}
				onclick={close}>Cancel</button
			>
			<button type="button" class="view-btn" disabled={busy} onclick={confirm}
				>{busy ? 'Saving…' : confirmLabel}</button
			>
		</div>
		<span role="status">{busy ? 'Saving changes…' : ''}</span>
	</div>
</div>

<style>
	.popup-backdrop {
		padding: var(--space-md);
	}
	.popup-card {
		max-width: 520px;
		max-height: calc(100dvh - 2 * var(--space-md));
		overflow-y: auto;
		box-sizing: border-box;
	}
	h3,
	p {
		overflow-wrap: anywhere;
	}
	.popup-actions {
		flex-wrap: wrap;
	}
</style>
