<script lang="ts">
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import ViewShell from '$lib/components/ViewShell.svelte';
	import { profilePictureOptions } from '$lib/settings/userSettings';
	import { updateCurrentUserSetting } from '$lib/api/userSettings';
	import { fetchMyUsage } from '$lib/api/analytics';
	import { fetchCourses } from '$lib/api/content';
	import { fetchCourseApiKeys } from '$lib/api/courses';
	import { selectedCourseId } from '$lib/stores/courseStore';
	import { currentFrame } from '$lib/stores/frameStore';
	import type { Course } from '$lib/types/course';
	import '$lib/styles/routes/modules/account-view.css';

	let currentUser = $derived(page.data.currentUser);
	let savedProfilePicture = $state(page.data.userSettings.profilePicture);
	let draftProfilePicture = $state(page.data.userSettings.profilePicture);
	let isProfilePickerOpen = $state(false);
	let isOverviewLoading = $state(true);
	let overviewError = $state<string | null>(null);
	let courseSummaries = $state<Array<{ course: Course; keyCount: number }>>([]);
	let usage = $state({ requestsToday: 0, totalRequests: 0, coursesEnrolled: 0, totalApiKeys: 0 });

	function logout() {
		void goto('/logout');
	}

	function openProfilePicker() {
		draftProfilePicture = savedProfilePicture;
		isProfilePickerOpen = true;
	}

	function cancelProfilePicture() {
		draftProfilePicture = savedProfilePicture;
		isProfilePickerOpen = false;
	}

	async function saveProfilePicture() {
		const previousValue = savedProfilePicture;
		savedProfilePicture = draftProfilePicture;
		isProfilePickerOpen = false;

		try {
			const settings = await updateCurrentUserSetting('profilePicture', draftProfilePicture);
			savedProfilePicture = settings.profilePicture;
			draftProfilePicture = settings.profilePicture;
		} catch {
			savedProfilePicture = previousValue;
			draftProfilePicture = previousValue;
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

	function openCourse(courseId: number): void {
		selectedCourseId.set(courseId);
		currentFrame.set('courses');
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

<ViewShell title="Account Profile">
	<div slot="actions">
		<button class="view-btn" onclick={logout}>Log Out</button>
	</div>

	<section class="section account-card">
		<div class="account-profile-header">
			<div class="account-avatar-wrap">
				<button
					type="button"
					class="account-avatar-button"
					onclick={openProfilePicker}
					aria-haspopup="dialog"
					aria-expanded={isProfilePickerOpen}
					aria-label="Choose profile picture"
				>
					<img class="account-avatar" src={savedProfilePicture} alt="" />
				</button>

				{#if isProfilePickerOpen}
					<div class="account-avatar-picker" role="dialog" aria-label="Choose profile picture">
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
	</section>

	{#if isOverviewLoading}
		<section class="section account-overview-state">
			<p>Loading your courses and usage...</p>
		</section>
	{:else if overviewError}
		<section class="section account-overview-state">
			<p><strong>Unable to load overview:</strong> {overviewError}</p>
		</section>
	{:else}
		<section class="section account-overview-section">
			<h2>My Courses &amp; API Keys</h2>
			{#if courseSummaries.length === 0}
				<p class="account-note">You are not enrolled in any courses yet.</p>
			{:else}
				<div class="account-course-list">
					{#each courseSummaries as summary (summary.course.id)}
						<button
							type="button"
							class="account-course-row"
							onclick={() => openCourse(summary.course.id)}
						>
							<span
								><strong>{summary.course.name}</strong><small
									>{formatKeyCount(summary.keyCount)}</small
								></span
							>
							<span class="account-course-link">View Course</span>
						</button>
					{/each}
				</div>
			{/if}
		</section>

		<section class="section account-overview-section">
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
