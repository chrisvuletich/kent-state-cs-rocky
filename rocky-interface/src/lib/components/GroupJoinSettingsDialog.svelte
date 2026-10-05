<script lang="ts">
	import { focusScope } from '$lib/actions/focusScope';
	import type { CourseGroup } from '$lib/types/course';
	import type { GroupJoinSettings } from '$lib/api/courses';
	import '$lib/styles/components/modules/popup.css';

	export let group: CourseGroup;
	export let onSave: (settings: GroupJoinSettings) => Promise<void>;
	export let onClose: () => void;
	let enabled = group.selfJoinEnabled;
	let maxMembers: number | undefined = group.maxMembers ?? undefined;
	let busy = false;
	let error: string | null = null;

	function close() {
		if (!busy) onClose();
	}
	async function save(event: SubmitEvent) {
		event.preventDefault();
		if (busy) return;
		const limit = maxMembers ?? null;
		if (limit !== null && (!Number.isSafeInteger(limit) || limit < 1)) {
			error = 'Enter a positive whole number, or leave the size limit blank.';
			return;
		}
		busy = true;
		error = null;
		try {
			await onSave({ selfJoinEnabled: enabled, maxMembers: limit });
		} catch (err) {
			error = err instanceof Error ? err.message : 'Unable to save group settings.';
		} finally {
			busy = false;
		}
	}
</script>

<div
	class="popup-backdrop join-settings-backdrop"
	role="presentation"
	onclick={(event) => {
		if (event.target === event.currentTarget) close();
	}}
>
	<div
		class="popup-card join-settings-dialog"
		role="dialog"
		aria-modal="true"
		aria-labelledby="join-settings-title"
		tabindex="-1"
		use:focusScope={{ initialFocus: '#group-self-join', onEscape: close }}
	>
		<h3 id="join-settings-title">Joining settings: {group.name}</h3>
		<form onsubmit={save}>
			<label class="join-toggle"
				><input id="group-self-join" type="checkbox" bind:checked={enabled} disabled={busy} /> Allow students
				to join themselves</label
			>
			<p>
				Only students on this course's roster can join. Turning this off does not remove existing
				members.
			</p>
			<label for="group-size-limit">Maximum students (optional)</label>
			<input
				id="group-size-limit"
				class="text-input"
				type="number"
				min="1"
				step="1"
				placeholder="No limit"
				bind:value={maxMembers}
				readonly={busy}
				aria-describedby="group-size-help"
			/>
			<p id="group-size-help">
				Leave blank for no limit. The limit also applies when staff add students. Current members: {group
					.memberIds.length}.
			</p>
			{#if error}<p class="popup-error" role="alert">{error}</p>{/if}
			<span class="save-status" role="status">{busy ? 'Saving settings…' : ''}</span>
			<div class="popup-actions">
				<button type="button" class="view-btn" disabled={busy} onclick={close}>Cancel</button>
				<button type="submit" class="view-btn" disabled={busy}
					>{busy ? 'Saving…' : 'Save settings'}</button
				>
			</div>
		</form>
	</div>
</div>

<style>
	.join-settings-backdrop {
		padding: var(--space-md);
	}
	.join-settings-dialog {
		max-width: 520px;
		max-height: calc(100dvh - 2 * var(--space-md));
		overflow-y: auto;
		box-sizing: border-box;
	}
	h3,
	p {
		overflow-wrap: anywhere;
	}
	p:not(.popup-error) {
		color: var(--color-text-secondary);
		font-size: var(--font-size-sm);
	}
	.join-toggle {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
	}
	.join-toggle input {
		flex-shrink: 0;
		width: 18px;
		height: 18px;
	}
	.text-input {
		width: 100%;
		box-sizing: border-box;
		margin-top: var(--space-xs);
	}
	.save-status {
		font-size: var(--font-size-sm);
	}
	.popup-actions {
		flex-wrap: wrap;
	}
</style>
