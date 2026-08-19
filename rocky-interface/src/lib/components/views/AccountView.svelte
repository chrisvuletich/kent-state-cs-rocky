<script lang="ts">
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { onMount, tick } from 'svelte';
	import ViewShell from '$lib/components/ViewShell.svelte';
	import { profilePictureOptions } from '$lib/settings/userSettings';
	import { updateCurrentUserSetting } from '$lib/api/userSettings';
	import { applyThemePreference, setThemePreference } from '$lib/stores/themeStore';
	import { fetchMyUsage } from '$lib/api/analytics';
	import { fetchCourses } from '$lib/api/content';
	import { fetchCourseApiKeys } from '$lib/api/courses';
	import { appHref } from '$lib/navigation/appRoute';
	import type { Course } from '$lib/types/course';
	import type { ThemePreference } from '$lib/settings/userSettings';

	let currentUser = $derived(page.data.currentUser);
	let savedProfilePicture = $state(page.data.userSettings.profilePicture);
	let draftProfilePicture = $state(page.data.userSettings.profilePicture);
	let themePreference = $state<ThemePreference>(page.data.userSettings.themePreference);
	let isThemeSaving = $state(false);
	let isProfilePickerOpen = $state(false);
	let isOverviewLoading = $state(true);
	let overviewError = $state<string | null>(null);
	let courseSummaries = $state<Array<{ course: Course; keyCount: number }>>([]);
	let usage = $state({ requestsToday: 0, totalRequests: 0, coursesEnrolled: 0, totalApiKeys: 0 });
	let avatarPickerWrap = $state<HTMLDivElement>();
	let avatarButton = $state<HTMLButtonElement>();
	let avatarPicker = $state<HTMLDivElement>();

	function logout() {
		void goto('/logout');
	}

	async function toggleTheme() {
		if (isThemeSaving) return;
		const previousPreference = themePreference;
		const nextPreference: ThemePreference = themePreference === 'dark' ? 'light' : 'dark';
		themePreference = nextPreference;
		applyThemePreference(nextPreference);
		isThemeSaving = true;

		try {
			await setThemePreference(nextPreference);
		} catch {
			themePreference = previousPreference;
			applyThemePreference(previousPreference);
		} finally {
			isThemeSaving = false;
		}
	}

	async function openProfilePicker() {
		if (isProfilePickerOpen) {
			await closeProfilePicker();
			return;
		}
		draftProfilePicture = savedProfilePicture;
		isProfilePickerOpen = true;
		await tick();
		avatarPicker?.querySelector<HTMLElement>('.account-avatar-option-active')?.focus();
	}

	async function closeProfilePicker(restoreFocus = true) {
		isProfilePickerOpen = false;
		await tick();
		if (restoreFocus) avatarButton?.focus();
	}

	function cancelProfilePicture() {
		draftProfilePicture = savedProfilePicture;
		void closeProfilePicker();
	}

	async function saveProfilePicture() {
		const previousValue = savedProfilePicture;
		savedProfilePicture = draftProfilePicture;
		await closeProfilePicker();

		try {
			const settings = await updateCurrentUserSetting('profilePicture', draftProfilePicture);
			savedProfilePicture = settings.profilePicture;
			draftProfilePicture = settings.profilePicture;
		} catch {
			savedProfilePicture = previousValue;
			draftProfilePicture = previousValue;
		}
	}

	function handlePickerKeydown(event: KeyboardEvent) {
		if (isProfilePickerOpen && event.key === 'Escape') {
			event.preventDefault();
			cancelProfilePicture();
		}
	}

	function handlePickerPointerDown(event: PointerEvent) {
		if (
			isProfilePickerOpen &&
			event.target instanceof Node &&
			!avatarPickerWrap?.contains(event.target)
		) {
			void closeProfilePicker(false);
		}
	}

	function handlePickerFocusOut(event: FocusEvent) {
		if (
			isProfilePickerOpen &&
			(!(event.relatedTarget instanceof Node) || !avatarPickerWrap?.contains(event.relatedTarget))
		) {
			void closeProfilePicker(false);
		}
	}

	function normalizeIdentifier(value: string | null | undefined): string {
		return value?.trim().toLowerCase() || '';
	}

	function userIdentifiers(): string[] {
		return [currentUser?.id, currentUser?.email, currentUser?.apiKeyOwnerId]
			.map(normalizeIdentifier)
			.filter(Boolean);
	}

	function isCurrentUserIdentifier(value: string | null | undefined): boolean {
		return userIdentifiers().includes(normalizeIdentifier(value));
	}

	function isEnrolled(course: Course): boolean {
		return (
			isCurrentUserIdentifier(course.instructorId) ||
			isCurrentUserIdentifier(course.instructorEmail) ||
			course.taIds.some(isCurrentUserIdentifier) ||
			course.taEmails.some(isCurrentUserIdentifier) ||
			(course.members || []).some(
				(member) => isCurrentUserIdentifier(member.id) || isCurrentUserIdentifier(member.email)
			)
		);
	}

	function formatKeyCount(count: number): string {
		if (count === 0) return 'No API Keys';
		return `${count} API Key${count === 1 ? '' : 's'}`;
	}

	onMount(async () => {
		if (!currentUser) {
			isOverviewLoading = false;
			return;
		}

		try {
			const [loadedCourses, telemetryUsage] = await Promise.all([fetchCourses(), fetchMyUsage()]);
			const enrolledCourses = loadedCourses.filter(isEnrolled);
			const courseData = await Promise.all(
				enrolledCourses.map(async (course) => {
					const keys = await fetchCourseApiKeys(course.id);
					const keyCount = keys.filter(
						(key) =>
							key.has_hash !== false &&
							key.owner_type === 'person' &&
							isCurrentUserIdentifier(key.owner_id)
					).length;
					return { course, keyCount };
				})
			);

			courseSummaries = courseData.map(({ course, keyCount }) => ({ course, keyCount }));
			usage = {
				requestsToday: telemetryUsage.requests_today,
				totalRequests: telemetryUsage.total_requests,
				coursesEnrolled: enrolledCourses.length,
				totalApiKeys: courseData.reduce((total, entry) => total + entry.keyCount, 0)
			};
		} catch (err) {
			overviewError =
				err instanceof Error ? err.message : 'Unable to load your course and usage information.';
		} finally {
			isOverviewLoading = false;
		}
	});
</script>

<svelte:window onkeydown={handlePickerKeydown} onpointerdown={handlePickerPointerDown} />

<ViewShell title="Account Profile">
	<div slot="actions">
		<button class="view-btn" onclick={logout}>Log Out</button>
	</div>

	<section class="section section-flat account-card">
		<div class="account-profile-header">
			<div
				class="account-avatar-wrap"
				bind:this={avatarPickerWrap}
				onfocusout={handlePickerFocusOut}
			>
				<button
					bind:this={avatarButton}
					type="button"
					class="account-avatar-button"
					onclick={openProfilePicker}
					aria-haspopup="dialog"
					aria-expanded={isProfilePickerOpen}
					aria-controls="account-avatar-picker"
					aria-label="Choose profile picture"
				>
					<img class="account-avatar" src={savedProfilePicture} alt="" />
				</button>

				{#if isProfilePickerOpen}
					<div
						bind:this={avatarPicker}
						id="account-avatar-picker"
						class="account-avatar-picker"
						role="dialog"
						aria-label="Choose profile picture"
					>
						<div class="account-avatar-grid">
							{#each profilePictureOptions as option}
								<button
									type="button"
									class="account-avatar-option"
									class:account-avatar-option-active={draftProfilePicture === option.value}
									onclick={() => (draftProfilePicture = option.value)}
									aria-label={option.label}
									aria-pressed={draftProfilePicture === option.value}
								>
									<img src={option.value} alt="" />
								</button>
							{/each}
						</div>
						<div class="account-avatar-actions">
							<button type="button" class="account-avatar-cancel" onclick={cancelProfilePicture}
								>Cancel</button
							>
							<button type="button" class="account-avatar-save" onclick={saveProfilePicture}
								>Save</button
							>
						</div>
					</div>
				{/if}
			</div>
			<div class="account-identity">
				<h2 class="account-name">
					{currentUser ? `${currentUser.firstName} ${currentUser.lastName}` : 'Unknown User'}
				</h2>
				<p><strong>ID:</strong> {currentUser?.id ?? '-'}</p>
				<p><strong>Email:</strong> {currentUser?.email ?? '-'}</p>
			</div>
		</div>
		<div class="account-divider"></div>
		<div class="account-theme-row">
			<div>
				<h3 class="account-theme-title">Appearance</h3>
				<p class="account-note">
					Use Rocky in dark mode. This preference is saved to your account.
				</p>
			</div>
			<div class="account-theme-control">
				<span aria-live="polite"
					>{themePreference === 'dark' ? 'Dark mode on' : 'Dark mode off'}</span
				>
				<button
					type="button"
					class="account-toggle"
					class:account-toggle-active={themePreference === 'dark'}
					role="switch"
					aria-checked={themePreference === 'dark'}
					aria-label="Dark mode"
					disabled={isThemeSaving}
					onclick={toggleTheme}
				>
					<span class="account-toggle-knob" aria-hidden="true"></span>
				</button>
			</div>
		</div>
	</section>

	{#if isOverviewLoading}
		<section class="section section-flat account-overview-state">
			<p>Loading your courses and usage...</p>
		</section>
	{:else if overviewError}
		<section class="section section-flat account-overview-state">
			<p><strong>Unable to load overview:</strong> {overviewError}</p>
		</section>
	{:else}
		<section class="section section-flat account-overview-section">
			<h2>My Courses &amp; API Keys</h2>
			{#if courseSummaries.length === 0}
				<p class="account-note">You are not enrolled in any courses yet.</p>
			{:else}
				<div class="account-course-list">
					{#each courseSummaries as summary (summary.course.id)}
						<a
							href={appHref(page.url, { frame: 'courses', courseId: summary.course.id })}
							class="account-course-row"
						>
							<span
								><strong>{summary.course.name}</strong><small
									>{formatKeyCount(summary.keyCount)}</small
								></span
							>
							<span class="account-course-link">View Course</span>
						</a>
					{/each}
				</div>
			{/if}
		</section>

		<section class="section section-flat account-overview-section">
			<h2>My Usage</h2>
			<div class="account-usage-grid">
				<div><span>Requests Today</span><strong>{usage.requestsToday}</strong></div>
				<div><span>Total Requests</span><strong>{usage.totalRequests}</strong></div>
				<div><span>Courses Enrolled</span><strong>{usage.coursesEnrolled}</strong></div>
				<div><span>Total API Keys</span><strong>{usage.totalApiKeys}</strong></div>
			</div>
		</section>
	{/if}
</ViewShell>
