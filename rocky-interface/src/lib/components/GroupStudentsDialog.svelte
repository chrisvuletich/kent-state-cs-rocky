<script lang="ts">
	import { focusScope } from '$lib/actions/focusScope';
	import '$lib/styles/components/modules/popup.css';

	export let groupName: string;
	export let students: Array<{ id: string; name: string; email: string; alreadyMember: boolean }>;
	export let onAdd: (memberIds: string[]) => Promise<void>;
	export let onClose: () => void;

	let query = '';
	let selected = new Set<string>();
	let busy = false;
	let error: string | null = null;

	$: search = query.trim().toLowerCase();
	$: matches = students.filter((student) =>
		`${student.name} ${student.email}`.toLowerCase().includes(search)
	);
	$: eligibleMatches = matches.filter((student) => !student.alreadyMember);
	$: allMatchesSelected = eligibleMatches.every((student) => selected.has(student.id));

	function toggle(id: string, checked: boolean) {
		if (busy) return;
		const next = new Set(selected);
		if (checked) next.add(id);
		else next.delete(id);
		selected = next;
	}

	function close() {
		if (!busy) onClose();
	}

	async function submit() {
		if (busy || !selected.size) return;
		busy = true;
		error = null;
		try {
			await onAdd([...selected]);
		} catch (err) {
			error = err instanceof Error ? err.message : 'Unable to add students. Please try again.';
		} finally {
			busy = false;
		}
	}
</script>

<div
	class="popup-backdrop group-students-backdrop"
	role="presentation"
	onclick={(event) => {
		if (event.target === event.currentTarget) close();
	}}
>
	<div
		class="popup-card group-students-dialog"
		role="dialog"
		aria-modal="true"
		aria-labelledby="group-students-title"
		aria-describedby="group-students-description"
		tabindex="-1"
		use:focusScope={{ initialFocus: '#group-students-search', onEscape: close }}
	>
		<h3 id="group-students-title">Add students to {groupName}</h3>
		<p id="group-students-description">
			Select students from this course's roster. Students can belong to more than one group.
		</p>
		<label for="group-students-search">Search students</label>
		<input
			id="group-students-search"
			class="text-input"
			type="search"
			placeholder="Search by name or email"
			bind:value={query}
			readonly={busy}
		/>
		<div class="selection-toolbar">
			<button
				type="button"
				class="list-go-btn"
				disabled={busy || allMatchesSelected}
				onclick={() =>
					(selected = new Set([...selected, ...eligibleMatches.map((student) => student.id)]))}
				>Select all matching</button
			>
			<button
				type="button"
				class="list-go-btn"
				disabled={busy || !selected.size}
				onclick={() => (selected = new Set())}>Clear selection</button
			>
			<span role="status">{busy ? 'Adding students…' : `${selected.size} selected`}</span>
		</div>
		<div class="student-list">
			{#each matches as student (student.id)}
				<label class="student-row">
					<input
						type="checkbox"
						value={student.id}
						checked={student.alreadyMember || selected.has(student.id)}
						disabled={busy || student.alreadyMember}
						onchange={(event) => toggle(student.id, event.currentTarget.checked)}
					/>
					<span class="student-identity"
						><span>{student.name}</span><small>{student.email}</small></span
					>
					{#if student.alreadyMember}<small class="membership-note">Already in group</small>{/if}
				</label>
			{:else}
				<p class="empty-students">
					{students.length
						? 'No students match your search.'
						: 'No students are on this course roster yet. Add students in Edit Roster first.'}
				</p>
			{/each}
		</div>
		{#if error}<p class="popup-error" role="alert">{error}</p>{/if}
		<div class="popup-actions">
			<button type="button" class="view-btn" disabled={busy} onclick={close}>Cancel</button>
			<button type="button" class="view-btn" disabled={busy || !selected.size} onclick={submit}>
				{busy
					? 'Adding students…'
					: `Add ${selected.size} ${selected.size === 1 ? 'student' : 'students'}`}
			</button>
		</div>
	</div>
</div>

<style>
	.group-students-backdrop {
		padding: var(--space-md);
	}
	.group-students-dialog {
		max-width: 640px;
		max-height: calc(100dvh - 2 * var(--space-md));
		display: flex;
		flex-direction: column;
		overflow-y: auto;
		box-sizing: border-box;
	}
	h3,
	p {
		overflow-wrap: anywhere;
	}
	#group-students-description {
		margin: 0 0 var(--space-lg);
	}
	#group-students-search {
		width: 100%;
		margin-top: var(--space-xs);
		box-sizing: border-box;
	}
	.selection-toolbar {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: var(--space-sm);
		padding: var(--space-md) 0;
	}
	.selection-toolbar span {
		margin-left: auto;
		font-size: var(--font-size-sm);
	}
	.student-list {
		overflow-y: auto;
		overscroll-behavior: contain;
		min-height: 96px;
		max-height: 340px;
		border-block: 1px solid var(--color-gray-300);
	}
	.student-row {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		padding: var(--space-md) 0;
		border-bottom: 1px solid var(--color-gray-300);
		cursor: pointer;
	}
	.student-row:last-child {
		border-bottom: 0;
	}
	.student-row:has(input:disabled) {
		cursor: default;
	}
	.student-row input {
		flex-shrink: 0;
		width: 18px;
		height: 18px;
	}
	.student-identity {
		display: flex;
		flex-direction: column;
		min-width: 0;
		overflow-wrap: anywhere;
	}
	.student-identity small,
	.membership-note {
		color: var(--color-text-secondary);
	}
	.membership-note {
		margin-left: auto;
		text-align: right;
	}
	.empty-students {
		padding: var(--space-md) 0;
	}
	.popup-actions {
		flex-wrap: wrap;
	}
</style>
