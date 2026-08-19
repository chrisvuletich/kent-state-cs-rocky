<script lang="ts">
	import { onMount } from 'svelte';
	import {
		fetchCourseApiKeys,
		updateCourseApiKeyStatus,
		type CourseApiKeySummaryResponse
	} from '$lib/api/courses';
	import { fetchCourses } from '$lib/api/content';
	import { fetchUsersForViews } from '$lib/api/users';
	import ViewShell from '$lib/components/ViewShell.svelte';
	import type { Course } from '$lib/types/course';
	import type { User } from '$lib/types/user';
	import '$lib/styles/routes/modules/audit-logs.css';
	import '$lib/styles/routes/modules/api-keys-view.css';

	type ApiKeyRecord = {
		keyId: string;
		ownerType: 'person' | 'group';
		ownerId: string;
		keyName: string;
		slotIndex: number;
		created: string;
		course: Course;
		isActive: boolean;
	};
	type SortColumn = 'semester' | 'course' | 'owner' | 'status' | 'created';
	type SortState = { column: SortColumn; direction: 'asc' | 'desc' };

	let keys: ApiKeyRecord[] = [];
	let users: User[] = [];
	let loading = true;
	let error = '';
	let message = '';
	let search = '';
	let status = '';
	let semester = '';
	let course = '';
	let savingKeyId = '';
	let selectedKeyIds: string[] = [];
	let sortState: SortState = { column: 'semester', direction: 'desc' };

	$: semesters = [...new Set(keys.map((key) => key.course.semester))].sort(
		(first, second) => semesterValue(second) - semesterValue(first)
	);
	$: coursesForFilter = [
		...new Map(
			keys
				.filter((key) => !semester || key.course.semester === semester)
				.map((key) => [key.course.id, key.course])
		).values()
	].sort((first, second) =>
		`${first.name} ${first.code}`.localeCompare(`${second.name} ${second.code}`)
	);
	$: if (course && !coursesForFilter.some((selectedCourse) => String(selectedCourse.id) === course))
		course = '';
	$: visibleKeys = keys
		.filter((key) => {
			const query = search.trim().toLowerCase();
			const owner = findOwner(key);
			const matchesSearch =
				!query ||
				[owner.name, owner.email, key.keyName, key.course.name, key.course.code].some((value) =>
					value.toLowerCase().includes(query)
				);
			return (
				matchesSearch &&
				(!status || String(key.isActive) === status) &&
				(!semester || key.course.semester === semester) &&
				(!course || String(key.course.id) === course)
			);
		})
		.sort((first, second) => compareKeys(first, second, sortState));
	$: {
		const visibleSelectedKeyIds = selectedKeyIds.filter((keyId) =>
			visibleKeys.some((key) => key.keyId === keyId)
		);
		if (visibleSelectedKeyIds.length !== selectedKeyIds.length)
			selectedKeyIds = visibleSelectedKeyIds;
	}
	$: allVisibleSelected =
		visibleKeys.length > 0 && visibleKeys.every((key) => selectedKeyIds.includes(key.keyId));

	onMount(loadKeys);

	function normalizeKey(
		raw: CourseApiKeySummaryResponse,
		selectedCourse: Course
	): ApiKeyRecord | null {
		if (raw.has_hash === false) return null;
		const ownerId = raw.owner_id?.trim() || '';
		if (!ownerId) return null;
		return {
			keyId: raw.key_id?.trim() || '',
			ownerType: raw.owner_type === 'group' ? 'group' : 'person',
			ownerId,
			keyName: raw.key_name?.trim() || 'key-1',
			slotIndex: typeof raw.slot_index === 'number' && raw.slot_index > 0 ? raw.slot_index : 1,
			created: raw.created?.trim() || '',
			course: selectedCourse,
			isActive: raw.is_active !== false
		};
	}

	async function loadKeys(): Promise<void> {
		loading = true;
		error = '';
		try {
			const [courses, loadedUsers] = await Promise.all([fetchCourses(), fetchUsersForViews()]);
			const keyLists = await Promise.all(
				courses.map((selectedCourse) => fetchCourseApiKeys(selectedCourse.id))
			);
			keys = keyLists.flatMap((keyList, index) =>
				keyList
					.map((key) => normalizeKey(key, courses[index]))
					.filter((key): key is ApiKeyRecord => key !== null)
			);
			users = loadedUsers;
		} catch (err) {
			error = err instanceof Error ? err.message : 'Unable to load API keys.';
		} finally {
			loading = false;
		}
	}

	function findOwner(key: ApiKeyRecord): { name: string; email: string; role: string } {
		if (key.ownerType === 'group')
			return { name: `Group: ${key.ownerId}`, email: '—', role: 'group' };
		const ownerId = key.ownerId.toLowerCase();
		const owner = users.find(
			(user) => user.id.toLowerCase() === ownerId || user.email.toLowerCase() === ownerId
		);
		return owner
			? { name: owner.displayName, email: owner.email, role: owner.role }
			: { name: key.ownerId, email: '—', role: 'person' };
	}

	function formatDate(value: string): string {
		const date = new Date(value);
		return value && !Number.isNaN(date.getTime()) ? date.toLocaleString() : '—';
	}

	function semesterValue(value: string): number {
		const match = value.match(/^(Spring|Summer|Fall)\s+(\d{4})$/i);
		if (!match) return -1;
		return Number(match[2]) * 10 + ({ spring: 1, summer: 2, fall: 3 }[match[1].toLowerCase()] || 0);
	}

	function compareKeys(first: ApiKeyRecord, second: ApiKeyRecord, sort: SortState): number {
		const firstOwner = findOwner(first).name;
		const secondOwner = findOwner(second).name;
		const firstValue =
			sort.column === 'semester'
				? semesterValue(first.course.semester)
				: sort.column === 'course'
					? `${first.course.name} ${first.course.code}`
					: sort.column === 'owner'
						? firstOwner
						: sort.column === 'status'
							? String(first.isActive)
							: new Date(first.created).getTime() || 0;
		const secondValue =
			sort.column === 'semester'
				? semesterValue(second.course.semester)
				: sort.column === 'course'
					? `${second.course.name} ${second.course.code}`
					: sort.column === 'owner'
						? secondOwner
						: sort.column === 'status'
							? String(second.isActive)
							: new Date(second.created).getTime() || 0;
		const comparison =
			typeof firstValue === 'number' && typeof secondValue === 'number'
				? firstValue - secondValue
				: String(firstValue).localeCompare(String(secondValue));
		if (comparison) return sort.direction === 'asc' ? comparison : -comparison;
		return (
			`${first.course.name} ${first.course.code}`.localeCompare(
				`${second.course.name} ${second.course.code}`
			) || firstOwner.localeCompare(secondOwner)
		);
	}

	function toggleSort(column: SortColumn): void {
		sortState = {
			column,
			direction:
				sortState.column === column
					? sortState.direction === 'asc'
						? 'desc'
						: 'asc'
					: column === 'semester' || column === 'created'
						? 'desc'
						: 'asc'
		};
	}

	function sortIndicator(column: SortColumn, sort: SortState): string {
		return sort.column === column ? (sort.direction === 'asc' ? ' ↑' : ' ↓') : '';
	}

	function sortAria(column: SortColumn, sort: SortState): 'ascending' | 'descending' | undefined {
		if (sort.column !== column) return undefined;
		return sort.direction === 'asc' ? 'ascending' : 'descending';
	}

	function toggleSelected(keyId: string): void {
		selectedKeyIds = selectedKeyIds.includes(keyId)
			? selectedKeyIds.filter((selectedKeyId) => selectedKeyId !== keyId)
			: [...selectedKeyIds, keyId];
	}

	function toggleAllVisible(): void {
		const visibleIds = visibleKeys.map((key) => key.keyId);
		selectedKeyIds = allVisibleSelected
			? selectedKeyIds.filter((keyId) => !visibleIds.includes(keyId))
			: [...new Set([...selectedKeyIds, ...visibleIds])];
	}

	function setKeyStatus(key: ApiKeyRecord, isActive: boolean): Promise<void> {
		return updateCourseApiKeyStatus(key.course.id, {
			ownerType: key.ownerType,
			ownerId: key.ownerType === 'person' ? key.ownerId : undefined,
			groupId: key.ownerType === 'group' ? key.ownerId : undefined,
			keyName: key.keyName,
			slotIndex: key.slotIndex,
			isActive
		});
	}

	async function updateStatus(key: ApiKeyRecord, isActive: boolean): Promise<void> {
		if (
			!confirm(
				`${isActive ? 'Reactivate' : 'Deactivate'} ${key.keyName} for ${findOwner(key).name}?`
			)
		)
			return;
		savingKeyId = 'single';
		error = '';
		message = '';
		try {
			await setKeyStatus(key, isActive);
			keys = keys.map((entry) => (entry === key ? { ...entry, isActive } : entry));
			message = `${key.keyName} ${isActive ? 'reactivated' : 'deactivated'}.`;
		} catch (err) {
			error = err instanceof Error ? err.message : 'Unable to update API key status.';
		} finally {
			savingKeyId = '';
		}
	}

	async function updateSelectedStatus(isActive: boolean): Promise<void> {
		const selectedKeys = visibleKeys.filter((key) => selectedKeyIds.includes(key.keyId));
		const keysToUpdate = selectedKeys.filter((key) => key.isActive !== isActive);
		const skipped = selectedKeys.length - keysToUpdate.length;
		if (
			keysToUpdate.length &&
			!confirm(
				`${isActive ? 'Reactivate' : 'Deactivate'} ${keysToUpdate.length} selected API key${keysToUpdate.length === 1 ? '' : 's'}?`
			)
		)
			return;
		savingKeyId = 'bulk';
		error = '';
		message = '';
		const results = await Promise.allSettled(
			keysToUpdate.map((key) => setKeyStatus(key, isActive))
		);
		const succeeded = results.filter((result) => result.status === 'fulfilled').length;
		const failed = results.length - succeeded;
		await loadKeys();
		selectedKeyIds = [];
		message = `${succeeded} ${isActive ? 'reactivated' : 'deactivated'}, ${failed} failed, ${skipped} skipped.`;
		savingKeyId = '';
	}
</script>

<ViewShell title="API Keys">
	<section class="section section-flat audit-log-view">
		<p class="audit-intro">View course API keys across Rocky. Key values are never displayed.</p>
		<div class="audit-filters">
			<input
				bind:value={search}
				type="search"
				placeholder="Search owner, email, key, or course"
				aria-label="Search API keys"
			/>
			<select bind:value={status} aria-label="Filter by status"
				><option value="">All statuses</option><option value="true">Active</option><option
					value="false">Inactive</option
				></select
			>
			<select bind:value={semester} aria-label="Filter by semester"
				><option value="">All semesters</option
				>{#each semesters as selectedSemester (selectedSemester)}<option value={selectedSemester}
						>{selectedSemester}</option
					>{/each}</select
			>
			<select bind:value={course} aria-label="Filter by course"
				><option value="">All courses</option
				>{#each coursesForFilter as selectedCourse (selectedCourse.id)}<option
						value={String(selectedCourse.id)}
						>{selectedCourse.name} {selectedCourse.code ? `(${selectedCourse.code})` : ''}</option
					>{/each}</select
			>
		</div>
		{#if loading}<div class="empty-state"><p>Loading API keys...</p></div>
		{:else if error}<div class="empty-state" role="alert">
				<p>{error}</p>
				<button class="view-btn" type="button" onclick={loadKeys}>Try again</button>
			</div>
		{:else}<p class="audit-count">
				{visibleKeys.length} API {visibleKeys.length === 1 ? 'key' : 'keys'}
			</p>
			{#if message}<p class="audit-count" role="status">{message}</p>{/if}
			{#if selectedKeyIds.length > 0}<div class="api-key-bulk-toolbar">
					<strong>{selectedKeyIds.length} selected</strong><button
						class="view-btn"
						disabled={Boolean(savingKeyId)}
						onclick={() => updateSelectedStatus(false)}>Deactivate selected</button
					><button
						class="view-btn"
						disabled={Boolean(savingKeyId)}
						onclick={() => updateSelectedStatus(true)}>Reactivate selected</button
					><button
						class="view-btn"
						disabled={Boolean(savingKeyId)}
						onclick={() => (selectedKeyIds = [])}>Clear selection</button
					>
				</div>{/if}
			<div class="table-container">
				<table class="data-table audit-table">
					<thead
						><tr
							><th
								><input
									type="checkbox"
									checked={allVisibleSelected}
									disabled={Boolean(savingKeyId)}
									onchange={toggleAllVisible}
									aria-label="Select all visible API keys"
								/></th
							><th aria-sort={sortAria('semester', sortState)}
								><button class="api-key-sort" type="button" onclick={() => toggleSort('semester')}
									>Semester{sortIndicator('semester', sortState)}</button
								></th
							><th aria-sort={sortAria('owner', sortState)}
								><button class="api-key-sort" type="button" onclick={() => toggleSort('owner')}
									>Owner{sortIndicator('owner', sortState)}</button
								></th
							><th>Role</th><th aria-sort={sortAria('course', sortState)}
								><button class="api-key-sort" type="button" onclick={() => toggleSort('course')}
									>Course{sortIndicator('course', sortState)}</button
								></th
							><th>Key</th><th aria-sort={sortAria('status', sortState)}
								><button class="api-key-sort" type="button" onclick={() => toggleSort('status')}
									>Status{sortIndicator('status', sortState)}</button
								></th
							><th aria-sort={sortAria('created', sortState)}
								><button class="api-key-sort" type="button" onclick={() => toggleSort('created')}
									>Created{sortIndicator('created', sortState)}</button
								></th
							><th>Actions</th></tr
						></thead
					><tbody>
						{#if visibleKeys.length === 0}<tr
								><td colspan="9">No API keys match these filters.</td></tr
							>
						{:else}{#each visibleKeys as key (key.keyId)}<tr
									class:api-key-active={key.isActive}
									class:api-key-inactive={!key.isActive}
									class:api-key-selected={selectedKeyIds.includes(key.keyId)}
									><td
										><input
											type="checkbox"
											checked={selectedKeyIds.includes(key.keyId)}
											disabled={Boolean(savingKeyId)}
											onchange={() => toggleSelected(key.keyId)}
											aria-label={`Select ${key.keyName}`}
										/></td
									><td>{key.course.semester}</td><td
										><strong>{findOwner(key).name}</strong><br /><span>{findOwner(key).email}</span
										></td
									><td>{findOwner(key).role}</td><td
										>{key.course.name}<br /><span>{key.course.code || '—'}</span></td
									><td>{key.keyName}</td><td
										><span
											class="api-key-status"
											class:api-key-status-active={key.isActive}
											class:api-key-status-inactive={!key.isActive}
											>{key.isActive ? 'Active' : 'Inactive'}</span
										></td
									><td>{formatDate(key.created)}</td><td
										><button
											class="view-btn"
											disabled={Boolean(savingKeyId)}
											onclick={() => updateStatus(key, !key.isActive)}
											>{key.isActive ? 'Deactivate' : 'Reactivate'}</button
										></td
									></tr
								>{/each}{/if}
					</tbody>
				</table>
			</div>
		{/if}
	</section>
</ViewShell>
