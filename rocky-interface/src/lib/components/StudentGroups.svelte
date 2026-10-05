<script lang="ts">
	import type { CourseGroup } from '$lib/types/course';
	export let groups: CourseGroup[];
	export let joinedGroupIds: Set<string>;
	export let courseClosed: boolean;
	export let pendingGroupId: string | null;
	export let refreshing: boolean;
	export let error: string | null;
	export let onJoin: (group: CourseGroup) => void;
	export let onOpen: (group: CourseGroup) => void;
	export let onRefresh: () => void;
</script>

<div class="student-groups">
	<div class="groups-intro">
		<div>
			<h3>Course groups</h3>
			<p>
				Join a group your instructor has opened. You can belong to more than one group. Contact your
				instructor to leave or switch groups.
			</p>
		</div>
		<button
			type="button"
			class="view-btn"
			disabled={refreshing || pendingGroupId !== null}
			onclick={onRefresh}>{refreshing ? 'Refreshing…' : 'Refresh groups'}</button
		>
	</div>
	{#if courseClosed}<p role="status">This course is closed. Joining is unavailable.</p>{/if}
	{#if error}<p class="join-error" role="alert">{error}</p>{/if}
	{#if !groups.length}<p>No groups are available for this course yet.</p>{/if}
	<ul class="joinable-groups">
		{#each groups as group (group.id)}
			{@const joined = joinedGroupIds.has(group.id)}
			{@const full = group.maxMembers !== null && group.memberIds.length >= group.maxMembers}
			<li>
				<div class="group-description">
					<strong>{group.name}</strong>
					<span
						>{group.memberIds.length}{group.maxMembers !== null ? ` / ${group.maxMembers}` : ''} students</span
					>
				</div>
				<span class="join-status"
					>{joined
						? 'You are a member'
						: courseClosed
							? 'Course closed'
							: !group.selfJoinEnabled
								? 'Instructor-assigned'
								: full
									? 'Full'
									: 'Open to join'}</span
				>
				<button
					type="button"
					class="view-btn"
					aria-label={joined ? `View ${group.name}` : `Join ${group.name}`}
					disabled={!joined &&
						(courseClosed ||
							!group.selfJoinEnabled ||
							full ||
							pendingGroupId !== null ||
							refreshing)}
					onclick={() => (joined ? onOpen(group) : onJoin(group))}
				>
					{joined ? 'View group' : pendingGroupId === group.id ? 'Joining…' : 'Join group'}
				</button>
			</li>
		{/each}
	</ul>
	<span role="status">{pendingGroupId ? 'Joining group…' : ''}</span>
</div>

<style>
	.groups-intro {
		display: flex;
		align-items: flex-start;
		gap: var(--space-lg);
		justify-content: space-between;
	}
	h3 {
		margin: 0;
	}
	p {
		margin: var(--space-sm) 0 var(--space-lg);
	}
	.groups-intro button {
		flex-shrink: 0;
	}
	.joinable-groups {
		list-style: none;
		padding: 0;
		margin: 0;
	}
	li {
		display: grid;
		grid-template-columns: minmax(0, 1fr) auto auto;
		gap: var(--space-lg);
		align-items: center;
		padding: var(--space-lg) 0;
		border-bottom: 1px solid var(--color-gray-300);
	}
	.group-description {
		display: flex;
		flex-direction: column;
		gap: var(--space-xs);
		overflow-wrap: anywhere;
	}
	.group-description span,
	.join-status {
		color: var(--color-text-secondary);
		font-size: var(--font-size-sm);
	}
	.join-error {
		color: var(--color-text-danger);
	}
	@media (max-width: 640px) {
		.groups-intro {
			flex-direction: column;
			gap: var(--space-sm);
		}
		li {
			grid-template-columns: minmax(0, 1fr) auto;
			gap: var(--space-sm);
		}
		.join-status {
			grid-column: 1;
		}
		li button {
			grid-column: 2;
			grid-row: 1 / 3;
		}
	}
</style>
