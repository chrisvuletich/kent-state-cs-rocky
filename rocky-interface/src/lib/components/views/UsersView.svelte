<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import {
		createOAuthWhitelistEntry,
		fetchOAuthWhitelistEntries,
		fetchUsersForViews,
		setUserActive,
		setUserRole,
		setUsersActive,
		setWhitelistUserActive,
		setWhitelistUserRole,
		type WhitelistEntry
	} from '$lib/api/users';
	import { fetchCourses } from '$lib/api/content';
	import type { Course } from '$lib/types/course';
	import type { User } from '$lib/types/user';
	import ViewShell from '$lib/components/ViewShell.svelte';
	import { focusScope } from '$lib/actions/focusScope';
	import { handleTabListKeydown } from '$lib/accessibility/tabs';
	import '$lib/styles/components/modules/popup.css';

	type UserTab = 'kent' | 'whitelist';
	type WhitelistField = 'firstName' | 'lastName' | 'email';
	type ListedUser = Pick<User, 'id' | 'displayName' | 'email' | 'isAdmin' | 'role' | 'isActive'>;
	let users: User[] = [];
	let whitelistEntries: WhitelistEntry[] = [];
	let activeTab: UserTab = 'kent';
	let isLoading = true;
	let error: string | null = null;
	let message: string | null = null;
	let isSaving = false;
	let searchQuery = '';
	let roleFilter = 'all';
	let statusFilter = 'all';
	let courseFilter = '';
	let nameSort: 'asc' | 'desc' = 'asc';
	let courses: Course[] = [];
	let selectedIds: string[] = [];
	let pendingBulkStatus: boolean | null = null;
	let firstName = '';
	let lastName = '';
	let email = '';
	let whitelistRole: 'student' | 'instructor' | 'admin' = 'student';
	let whitelistFieldErrors: Record<WhitelistField, string> = {
		firstName: '',
		lastName: '',
		email: ''
	};

	$: listedUsers = (
		activeTab === 'kent'
			? users.filter((user) => user.email.toLowerCase().endsWith('@kent.edu'))
			: whitelistEntries
	) as ListedUser[];
	$: currentUserId = $page.data.currentUser?.id?.trim().toLowerCase() || '';
	$: currentUserEmail = $page.data.currentUser?.email?.trim().toLowerCase() || '';
	$: coursesForFilter = [...courses].sort((first, second) =>
		`${first.name} ${first.code}`.localeCompare(`${second.name} ${second.code}`)
	);
	$: if (courseFilter && !coursesForFilter.some((course) => String(course.id) === courseFilter))
		courseFilter = '';
	$: visibleUsers = listedUsers
		.filter((user) => {
			const query = searchQuery.trim().toLowerCase();
			const matchesSearch =
				!query ||
				user.displayName.toLowerCase().includes(query) ||
				user.email.toLowerCase().includes(query);
			const matchesRole = roleFilter === 'all' || user.role === roleFilter;
			const matchesStatus =
				statusFilter === 'all' || (statusFilter === 'active' ? user.isActive : !user.isActive);
			const matchesCourse =
				!courseFilter ||
				courses.some(
					(course) => String(course.id) === courseFilter && isEnrolledInCourse(user, course)
				);
			return matchesSearch && matchesRole && matchesStatus && matchesCourse;
		})
		.sort((first, second) => {
			const comparison =
				first.displayName.localeCompare(second.displayName) ||
				first.email.localeCompare(second.email);
			return nameSort === 'asc' ? comparison : -comparison;
		});
	$: {
		const visibleSelectedIds = selectedIds.filter((id) =>
			visibleUsers.some((user) => user.id === id && !isCurrentUser(user))
		);
		if (visibleSelectedIds.length !== selectedIds.length) selectedIds = visibleSelectedIds;
	}
	$: selectableVisibleUsers = visibleUsers.filter((user) => !isCurrentUser(user));
	$: selectedVisibleCount = selectableVisibleUsers.filter((user) =>
		selectedIds.includes(user.id)
	).length;
	$: allVisibleSelected =
		selectableVisibleUsers.length > 0 && selectedVisibleCount === selectableVisibleUsers.length;

	onMount(() => {
		void refresh();
	});

	async function refresh(): Promise<void> {
		isLoading = true;
		error = null;
		try {
			const [loadedUsers, loadedWhitelist, loadedCourses] = await Promise.all([
				fetchUsersForViews(),
				fetchOAuthWhitelistEntries(),
				fetchCourses()
			]);
			users = loadedUsers;
			whitelistEntries = loadedWhitelist;
			courses = loadedCourses;
		} catch (err) {
			error = err instanceof Error ? err.message : 'Unable to load users.';
		} finally {
			isLoading = false;
		}
	}

	function isEnrolledInCourse(user: ListedUser, course: Course): boolean {
		const identifiers = [user.id, user.email].map((value) => value.toLowerCase());
		const courseIdentifiers = [
			course.instructorId,
			course.instructorEmail,
			...course.taIds,
			...course.taEmails
		].map((value) => (value || '').toLowerCase());
		return (
			courseIdentifiers.some((identifier) => identifiers.includes(identifier)) ||
			(course.members || []).some(
				(member) =>
					identifiers.includes((member.id || '').toLowerCase()) ||
					identifiers.includes(member.email.toLowerCase())
			)
		);
	}

	function isCurrentUser(user: ListedUser): boolean {
		return Boolean(
			(currentUserId && user.id.trim().toLowerCase() === currentUserId) ||
			(currentUserEmail && user.email.trim().toLowerCase() === currentUserEmail)
		);
	}

	function toggleSelected(id: string): void {
		const user = visibleUsers.find((candidate) => candidate.id === id);
		if (user && isCurrentUser(user)) return;
		selectedIds = selectedIds.includes(id)
			? selectedIds.filter((selectedId) => selectedId !== id)
			: [...selectedIds, id];
	}

	function toggleAllVisible(): void {
		const visibleIds = selectableVisibleUsers.map((user) => user.id);
		selectedIds = allVisibleSelected
			? selectedIds.filter((id) => !visibleIds.includes(id))
			: [...new Set([...selectedIds, ...visibleIds])];
	}

	function closeBulkConfirmation(): void {
		if (!isSaving) pendingBulkStatus = null;
	}

	function selectUserTab(tab: UserTab): void {
		activeTab = tab;
		selectedIds = [];
	}

	function clearWhitelistFieldError(field: WhitelistField): void {
		if (!whitelistFieldErrors[field]) return;
		whitelistFieldErrors = { ...whitelistFieldErrors, [field]: '' };
	}

	async function updateStatus(user: ListedUser, isActive: boolean): Promise<void> {
		if (isCurrentUser(user) && !isActive) return;
		isSaving = true;
		error = null;
		message = null;
		try {
			if (activeTab === 'whitelist') await setWhitelistUserActive(user.id, isActive);
			else await setUserActive(user.id, isActive);
			await refresh();
			message = `${user.displayName} ${isActive ? 'activated' : 'deactivated'}.`;
		} catch (err) {
			error = err instanceof Error ? err.message : 'Unable to update user.';
		} finally {
			isSaving = false;
		}
	}

	async function updateRole(
		user: ListedUser,
		role: 'student' | 'instructor' | 'admin'
	): Promise<void> {
		if (isCurrentUser(user) && role !== 'admin') return;
		if (role === user.role || !confirm(`Change ${user.displayName}'s account role to ${role}?`))
			return;
		isSaving = true;
		error = null;
		message = null;
		try {
			if (activeTab === 'whitelist') await setWhitelistUserRole(user.id, role);
			else await setUserRole(user.id, role);
			await refresh();
		} catch (err) {
			error = err instanceof Error ? err.message : 'Unable to update role.';
		} finally {
			isSaving = false;
		}
	}

	async function applyBulkStatus(): Promise<void> {
		if (pendingBulkStatus === null) return;
		isSaving = true;
		error = null;
		message = null;
		try {
			const result = await setUsersActive(selectedIds, pendingBulkStatus);
			await refresh();
			selectedIds = [];
			message = `${result.updatedIds.length} selected account${result.updatedIds.length === 1 ? '' : 's'} ${pendingBulkStatus ? 'reactivated' : 'deactivated'}${result.missingIds.length ? `; ${result.missingIds.length} could not be found.` : '.'}`;
		} catch (err) {
			error = err instanceof Error ? err.message : 'Unable to update selected users.';
		} finally {
			isSaving = false;
			pendingBulkStatus = null;
		}
	}

	async function addWhitelistEntry(): Promise<void> {
		error = null;
		message = null;
		const nextFieldErrors: Record<WhitelistField, string> = {
			firstName: firstName.trim() ? '' : 'First name is required.',
			lastName: lastName.trim() ? '' : 'Last name is required.',
			email: !email.trim()
				? 'Email is required.'
				: /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())
					? ''
					: 'Enter a valid email address.'
		};
		whitelistFieldErrors = nextFieldErrors;
		if (Object.values(nextFieldErrors).some(Boolean)) {
			return;
		}
		isSaving = true;
		try {
			await createOAuthWhitelistEntry({ firstName, lastName, email, role: whitelistRole });
			firstName = '';
			lastName = '';
			email = '';
			whitelistFieldErrors = { firstName: '', lastName: '', email: '' };
			whitelistRole = 'student';
			await refresh();
			message = 'Whitelist entry added.';
		} catch (err) {
			error = err instanceof Error ? err.message : 'Unable to add whitelist entry.';
		} finally {
			isSaving = false;
		}
	}
</script>

<ViewShell title="User Management">
	{#if isLoading}<div class="empty-state"><p>Loading users...</p></div>
	{:else if error && users.length === 0 && whitelistEntries.length === 0 && courses.length === 0}
		<div class="empty-state" role="alert">
			<p>{error}</p>
			<button class="view-btn" type="button" onclick={refresh}>Try again</button>
		</div>
	{:else}
		<section class="section section-flat users-management">
			<p class="management-intro">
				Find accounts by name or email, filter their role and status, and manage access safely.
			</p>
			<div class="user-tab-bar" role="tablist" aria-label="User account source">
				<button
					id="kent-accounts-tab"
					type="button"
					role="tab"
					aria-selected={activeTab === 'kent'}
					aria-controls="user-account-panel"
					tabindex={activeTab === 'kent' ? 0 : -1}
					class="view-btn user-tab-btn"
					class:user-tab-active={activeTab === 'kent'}
					onkeydown={handleTabListKeydown}
					onclick={() => selectUserTab('kent')}>Kent accounts</button
				>
				<button
					id="whitelist-accounts-tab"
					type="button"
					role="tab"
					aria-selected={activeTab === 'whitelist'}
					aria-controls="user-account-panel"
					tabindex={activeTab === 'whitelist' ? 0 : -1}
					class="view-btn user-tab-btn"
					class:user-tab-active={activeTab === 'whitelist'}
					onkeydown={handleTabListKeydown}
					onclick={() => selectUserTab('whitelist')}>Whitelist accounts</button
				>
			</div>
			<div
				id="user-account-panel"
				class="user-account-panel"
				role="tabpanel"
				aria-labelledby={activeTab === 'kent' ? 'kent-accounts-tab' : 'whitelist-accounts-tab'}
			>
				<div class="user-filters">
					<input
						type="search"
						placeholder="Search name or email"
						bind:value={searchQuery}
						aria-label="Search users"
					/>
					<select bind:value={roleFilter} aria-label="Filter by role"
						><option value="all">All roles</option><option value="student">Students</option><option
							value="instructor">Instructors</option
						><option value="admin">Admins</option></select
					>
					<select bind:value={statusFilter} aria-label="Filter by status"
						><option value="all">All statuses</option><option value="active">Active</option><option
							value="inactive">Inactive</option
						></select
					>
					<select bind:value={courseFilter} aria-label="Filter by course"
						><option value="">All courses</option
						>{#each coursesForFilter as course (course.id)}<option value={String(course.id)}
								>{course.name} {course.code ? `(${course.code})` : ''}</option
							>{/each}</select
					>
					<select bind:value={nameSort} aria-label="Sort users by name"
						><option value="asc">Name: A–Z</option><option value="desc">Name: Z–A</option></select
					>
				</div>
				{#if activeTab === 'whitelist'}
					<div class="whitelist-form">
						<div class="whitelist-field">
							<label class="sr-only" for="whitelist-first-name">First name</label>
							<input
								id="whitelist-first-name"
								placeholder="First name"
								aria-label="Whitelist first name"
								bind:value={firstName}
								aria-invalid={whitelistFieldErrors.firstName ? 'true' : undefined}
								aria-describedby={whitelistFieldErrors.firstName
									? 'whitelist-first-name-error'
									: undefined}
								oninput={() => clearWhitelistFieldError('firstName')}
							/>
							{#if whitelistFieldErrors.firstName}<p
									id="whitelist-first-name-error"
									class="whitelist-field-error"
									role="alert"
								>
									{whitelistFieldErrors.firstName}
								</p>{/if}
						</div>
						<div class="whitelist-field">
							<label class="sr-only" for="whitelist-last-name">Last name</label>
							<input
								id="whitelist-last-name"
								placeholder="Last name"
								aria-label="Whitelist last name"
								bind:value={lastName}
								aria-invalid={whitelistFieldErrors.lastName ? 'true' : undefined}
								aria-describedby={whitelistFieldErrors.lastName
									? 'whitelist-last-name-error'
									: undefined}
								oninput={() => clearWhitelistFieldError('lastName')}
							/>
							{#if whitelistFieldErrors.lastName}<p
									id="whitelist-last-name-error"
									class="whitelist-field-error"
									role="alert"
								>
									{whitelistFieldErrors.lastName}
								</p>{/if}
						</div>
						<div class="whitelist-field">
							<label class="sr-only" for="whitelist-email">Email</label>
							<input
								id="whitelist-email"
								type="email"
								placeholder="Email"
								aria-label="Whitelist email"
								bind:value={email}
								aria-invalid={whitelistFieldErrors.email ? 'true' : undefined}
								aria-describedby={whitelistFieldErrors.email ? 'whitelist-email-error' : undefined}
								oninput={() => clearWhitelistFieldError('email')}
							/>
							{#if whitelistFieldErrors.email}<p
									id="whitelist-email-error"
									class="whitelist-field-error"
									role="alert"
								>
									{whitelistFieldErrors.email}
								</p>{/if}
						</div>
						<label class="whitelist-field">
							<span class="sr-only">Role</span>
							<select bind:value={whitelistRole} aria-label="Whitelist role"
								><option value="student">Student</option><option value="instructor"
									>Instructor</option
								><option value="admin">Admin</option></select
							>
						</label>
						<button class="view-btn" type="button" onclick={addWhitelistEntry} disabled={isSaving}
							>Add account</button
						>
					</div>
				{/if}
				{#if error}<p class="whitelist-feedback whitelist-error" role="alert">{error}</p>{/if}
				{#if message}<p class="whitelist-feedback" role="status">{message}</p>{/if}
				{#if selectedIds.length > 0}
					<div class="bulk-toolbar">
						<strong>{selectedIds.length} selected</strong><button
							class="view-btn"
							disabled={isSaving}
							onclick={() => (pendingBulkStatus = false)}>Deactivate selected</button
						><button class="view-btn" disabled={isSaving} onclick={() => (pendingBulkStatus = true)}
							>Reactivate selected</button
						><button class="view-btn" onclick={() => (selectedIds = [])}>Clear</button>
					</div>
				{/if}
				{#if pendingBulkStatus !== null}
					<div
						class="popup-backdrop"
						role="presentation"
						onclick={(event) => {
							if (event.target === event.currentTarget) closeBulkConfirmation();
						}}
					>
						<div
							class="popup-card bulk-confirmation"
							role="alertdialog"
							aria-modal="true"
							aria-labelledby="bulk-confirmation-title"
							aria-describedby="bulk-confirmation-description"
							tabindex="-1"
							use:focusScope={{ onEscape: closeBulkConfirmation }}
						>
							<h3 id="bulk-confirmation-title">Confirm bulk change</h3>
							<span id="bulk-confirmation-description"
								>{pendingBulkStatus ? 'Reactivate' : 'Deactivate'}
								{selectedIds.length} selected account{selectedIds.length === 1 ? '' : 's'}?</span
							>
							<div class="bulk-confirmation-actions">
								<button class="view-btn" disabled={isSaving} onclick={closeBulkConfirmation}
									>Cancel</button
								><button class="view-btn" disabled={isSaving} onclick={applyBulkStatus}
									>Confirm</button
								>
							</div>
						</div>
					</div>
				{/if}
				<div class="table-container">
					<table class="data-table users-table">
						<thead
							><tr
								><th
									><input
										type="checkbox"
										checked={allVisibleSelected}
										onchange={toggleAllVisible}
										aria-label="Select all visible users"
									/></th
								><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th>Actions</th></tr
							></thead
						><tbody>
							{#if visibleUsers.length === 0}<tr
									><td colspan="6">No users match these filters.</td></tr
								>
							{:else}{#each visibleUsers as user (user.id)}<tr
										><td
											><input
												type="checkbox"
												checked={selectedIds.includes(user.id)}
												disabled={isCurrentUser(user)}
												onchange={() => toggleSelected(user.id)}
												aria-label={`Select ${user.displayName}`}
												title={isCurrentUser(user)
													? 'You cannot bulk-update your own administrator account.'
													: undefined}
											/></td
										><td>{user.displayName}</td><td>{user.email}</td><td
											><span class:role-admin={user.role === 'admin'} class="role-badge"
												>{user.role}</span
											></td
										><td
											><span class:status-active={user.isActive} class="status-badge"
												>{user.isActive ? 'Active' : 'Inactive'}</span
											></td
										><td
											><div class="user-actions">
												<button
													class="view-btn user-action-btn"
													disabled={isSaving || isCurrentUser(user)}
													title={isCurrentUser(user)
														? 'You cannot deactivate your own administrator account.'
														: undefined}
													onclick={() => updateStatus(user, !user.isActive)}
													>{user.isActive ? 'Deactivate' : 'Reactivate'}</button
												><select
													class="role-select"
													value={user.role}
													disabled={isSaving || isCurrentUser(user)}
													title={isCurrentUser(user)
														? 'You cannot change your own administrator role.'
														: undefined}
													onchange={(event) =>
														updateRole(
															user,
															(event.currentTarget as HTMLSelectElement).value as
																| 'student'
																| 'instructor'
																| 'admin'
														)}
													aria-label={`Change ${user.displayName}'s role`}
													><option value="student">Student</option><option value="instructor"
														>Instructor</option
													><option value="admin">Admin</option></select
												>
											</div></td
										></tr
									>{/each}{/if}
						</tbody>
					</table>
				</div>
			</div>
		</section>
	{/if}
</ViewShell>
