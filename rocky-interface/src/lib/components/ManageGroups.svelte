<script lang="ts">
	import { tick } from 'svelte';
	import type { CourseGroup, CourseMember } from '$lib/types/course';
	export let groups: CourseGroup[];
	export let members: CourseMember[];
	export let courseClosed: boolean;
	export let selectedGroupId = '';
	export let refreshing: boolean;
	export let refreshError: string | null;
	export let onRefresh: () => void;
	export let onCreate: (name: string) => Promise<void>;
	export let onSettings: (group: CourseGroup) => void;
	export let onAdd: (group: CourseGroup) => void;
	export let onJoining: (group: CourseGroup) => void;
	export let onPause: (group: CourseGroup) => void;
	export let onDelete: (group: CourseGroup) => void;
	export let onRemove: (group: CourseGroup, memberId: string) => void;
	let newName = '';
	let creating = false;
	let createError: string | null = null;
	$: selected = groups.find((group) => group.id === selectedGroupId) || null;
	function memberLabel(id: string) {
		const normalized = id.toLowerCase();
		const member = members.find((m) =>
			[m.id?.toLowerCase(), m.email.toLowerCase()].includes(normalized)
		);
		return { name: member?.name || member?.email || id, email: member?.name ? member.email : '' };
	}
	async function open(group: CourseGroup) {
		selectedGroupId = group.id;
		await tick();
		document.getElementById('group-detail-title')?.focus();
	}
	async function back() {
		const previous = selectedGroupId;
		selectedGroupId = '';
		await tick();
		(
			document.getElementById(`view-group-${previous}`) ||
			document.getElementById('group-list-summary')
		)?.focus();
	}
	async function create(event: SubmitEvent) {
		event.preventDefault();
		if (creating || courseClosed || !newName.trim()) return;
		creating = true;
		createError = null;
		try {
			await onCreate(newName.trim());
			newName = '';
		} catch (err) {
			createError = err instanceof Error ? err.message : 'Unable to create group.';
		} finally {
			creating = false;
		}
	}
</script>

<div class="manage-groups">
	{#if courseClosed}<p role="status">This course is closed. Group management is read-only.</p>{/if}
	{#if refreshError}<p role="alert">{refreshError}</p>{/if}
	{#if selected}
		<div class="group-toolbar">
			<button type="button" class="view-btn" onclick={back}>Back to groups</button>
			<button type="button" class="view-btn" disabled={refreshing} onclick={onRefresh}
				>{refreshing ? 'Refreshing…' : 'Refresh groups'}</button
			>
		</div>
		<h3 id="group-detail-title" tabindex="-1">{selected.name}</h3>
		<p>
			{selected.memberIds.length}{selected.maxMembers !== null ? ` / ${selected.maxMembers}` : ''} students
			· {selected.isActive ? 'Shared-key access active' : 'Paused — shared keys disabled'} · Self-join
			{selected.selfJoinEnabled ? 'on' : 'off'}
		</p>
		{#if !selected.isActive}<p>
				Students cannot join while paused. Staff can still manage membership and settings. Personal
				keys and normal chat are unaffected.
			</p>{/if}
		<section aria-labelledby="group-members-title">
			<div class="group-toolbar">
				<h4 id="group-members-title">Members</h4>
				<button
					type="button"
					class="view-btn"
					disabled={courseClosed}
					aria-label={`Add students to ${selected.name}`}
					onclick={() => onAdd(selected!)}>Add students</button
				>
			</div>
			{#if !selected.memberIds.length}<p>No students assigned yet.</p>{/if}
			<ul class="group-members">
				{#each selected.memberIds as id}
					{@const label = memberLabel(id)}
					<li>
						<span
							>{label.name}{#if label.email}<small>{label.email}</small>{/if}</span
						><button
							type="button"
							class="list-go-btn"
							disabled={courseClosed}
							aria-label={`Remove ${label.name} from ${selected.name}`}
							onclick={() => onRemove(selected!, id)}>Remove</button
						>
					</li>
				{/each}
			</ul>
		</section>
		<section aria-labelledby="group-keys-title">
			<h4 id="group-keys-title">Shared API keys</h4>
			<p>
				Only staff can manage these keys. Share newly generated keys with group members securely.
			</p>
			<slot />
		</section>
		<section aria-labelledby="group-settings-title">
			<h4 id="group-settings-title">Settings</h4>
			<p>
				Rename this group, set its size and key allowance, or allow students to join themselves.
			</p>
			<div class="group-toolbar">
				<button
					type="button"
					class="view-btn"
					disabled={courseClosed}
					aria-label={`Group settings for ${selected.name}`}
					onclick={() => onSettings(selected!)}>Group settings</button
				>
				<button
					type="button"
					class="view-btn"
					disabled={courseClosed}
					onclick={() => onJoining(selected!)}
					>{selected.selfJoinEnabled ? 'Close joining' : 'Open joining'}</button
				>
				<button
					type="button"
					class="view-btn"
					disabled={courseClosed}
					onclick={() => onPause(selected!)}
					>{selected.isActive ? 'Pause group' : 'Resume group'}</button
				>
				<button
					type="button"
					class="view-btn"
					disabled={courseClosed}
					onclick={() => onDelete(selected!)}>Delete group</button
				>
			</div>
		</section>
	{:else}
		<form class="group-toolbar" onsubmit={create}>
			<input
				class="text-input"
				type="text"
				placeholder="New group name"
				aria-label="New group name"
				bind:value={newName}
				maxlength="120"
				required
				disabled={courseClosed || creating}
			/>
			<button type="submit" class="view-btn" disabled={courseClosed || creating || !newName.trim()}
				>{creating ? 'Creating…' : 'Create Group'}</button
			>
			<button type="button" class="view-btn" disabled={refreshing} onclick={onRefresh}
				>{refreshing ? 'Refreshing…' : 'Refresh groups'}</button
			>
		</form>
		{#if createError}<p role="alert">{createError}</p>{/if}
		<p id="group-list-summary" role="status" tabindex="-1">
			{groups.length}
			{groups.length === 1 ? 'group' : 'groups'}
		</p>
		{#if !groups.length}<p>
				No groups yet. Create a group to assign students and shared keys.
			</p>{/if}
		<ul class="group-list">
			{#each groups as group (group.id)}
				<li>
					<div class="group-description">
						<strong>{group.name}</strong><span
							>{group.memberIds.length}{group.maxMembers !== null ? ` / ${group.maxMembers}` : ''} students</span
						>
					</div>
					<div class="group-status">
						<span>{courseClosed ? 'Course closed' : group.isActive ? 'Active' : 'Paused'}</span
						><span
							>{!group.isActive || courseClosed
								? 'Joining unavailable'
								: !group.selfJoinEnabled
									? 'Joining closed'
									: group.maxMembers !== null && group.memberIds.length >= group.maxMembers
										? 'Full'
										: 'Open to join'}</span
						>
					</div>
					<div class="group-toolbar">
						<button
							id={`view-group-${group.id}`}
							type="button"
							class="view-btn"
							aria-label={`View ${group.name}`}
							onclick={() => open(group)}>View group</button
						>
						<button
							type="button"
							class="view-btn"
							aria-label={`Add students to ${group.name}`}
							disabled={courseClosed}
							onclick={() => onAdd(group)}>Add students</button
						>
						<button
							type="button"
							class="view-btn"
							aria-label={`Group settings for ${group.name}`}
							disabled={courseClosed}
							onclick={() => onSettings(group)}>Settings</button
						>
					</div>
				</li>
			{/each}
		</ul>
	{/if}
</div>

<style>
	.group-toolbar {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: var(--space-sm);
	}
	.group-toolbar input {
		min-width: 0;
		flex: 1 1 180px;
	}
	.group-list,
	.group-members {
		list-style: none;
		padding: 0;
		margin: 0;
	}
	.group-list > li {
		display: grid;
		grid-template-columns: minmax(0, 1fr) auto auto;
		align-items: center;
		gap: var(--space-lg);
		padding: var(--space-lg) 0;
		border-bottom: 1px solid var(--color-gray-300);
	}
	.group-description,
	.group-status {
		display: flex;
		flex-direction: column;
		gap: var(--space-xs);
	}
	.group-description span,
	.group-status,
	small {
		color: var(--color-text-secondary);
		font-size: var(--font-size-sm);
	}
	.group-members li {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-sm);
		padding: var(--space-sm) 0;
		border-bottom: 1px solid var(--color-gray-300);
	}
	.group-members span {
		min-width: 0;
	}
	small {
		display: block;
	}
	section {
		margin-top: var(--space-lg);
		padding-top: var(--space-lg);
		border-top: 1px solid var(--color-gray-300);
	}
	h3,
	h4,
	p,
	span,
	strong {
		overflow-wrap: anywhere;
	}
	h4 {
		margin: 0;
	}
	@media (max-width: 900px) {
		.group-list > li {
			grid-template-columns: minmax(0, 1fr) auto;
			gap: var(--space-sm);
		}
		.group-list .group-toolbar {
			grid-column: 1 / -1;
		}
	}
</style>
