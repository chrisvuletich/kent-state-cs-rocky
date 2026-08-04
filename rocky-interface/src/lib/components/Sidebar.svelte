	<script lang="ts">
	import '$lib/styles/components/modules/sidebar.css';
	import { page } from '$app/state';
	import { browser } from '$app/environment';
	import { onDestroy, onMount } from 'svelte';
	import { fetchCourses } from '$lib/api/content';
	import type { Course } from '$lib/types/course';
	import { currentFrame, frameMap } from '$lib/stores/frameStore';
	import { selectedCourseId } from '$lib/stores/courseStore';
	import { openCourseComposer } from '$lib/stores/courseComposerStore';
	import { framesForRole, toFrameLabel, type FrameName } from '$lib/types/frame';
	import {sidebarOpen} from '$lib/stores/sidebarStore';

	const frameIcons: Record<FrameName, string> = {
		dashboard: '/dashboard-icon.svg',
		users: '/users-icon.svg',
		courses: '/courses-icon.svg',
		analytics: '/analytics-icon.svg',
		admin: '/admin-icon.svg',
		audit: '/analytics-icon.svg',
		'api-keys': '/api-key-icon.svg',
		account: '/account-icon.svg',
		chat: '/chat-icon.svg',
		help: '/help-icon.svg'
	};

	const frames = Object.keys(frameMap) as FrameName[];
	const isAdmin = $derived(Boolean(page.data.currentUser?.isAdmin));
	const currentUserDisplayName = $derived(page.data.currentUser?.displayName?.trim() || '');
	const currentUserFirstName = $derived(page.data.currentUser?.firstName?.trim() || '');
	const currentUserLastName = $derived(page.data.currentUser?.lastName?.trim() || '');
	const currentUserId = $derived(page.data.currentUser?.id?.trim().toLowerCase() || '');
	const currentUserFullName = $derived(
		[currentUserFirstName, currentUserLastName].filter((value) => value.length > 0).join(' ').trim()
	);
	const currentUserEmail = $derived(page.data.currentUser?.email?.trim().toLowerCase() || '');
	const allowedFrames = $derived(framesForRole(isAdmin));
	const primaryFrames = $derived(allowedFrames.filter((frame) => frame !== 'help'));
	const coursesFrameIndex = $derived(primaryFrames.indexOf('courses'));
	const framesBeforeCourses = $derived(
		coursesFrameIndex >= 0 ? primaryFrames.slice(0, coursesFrameIndex) : primaryFrames.filter((frame) => frame !== 'courses')
	);
	const framesAfterCourses = $derived(coursesFrameIndex >= 0 ? primaryFrames.slice(coursesFrameIndex + 1) : []);
	const canCreateCourse = $derived(isAdmin);
	let activeFrame = $derived((browser ? $currentFrame : page.data.initialFrame) as FrameName);
	const SESSION_VALIDATE_TTL_MS = 10_000;
	let lastSessionValidationAt = 0;
	let sessionValidationInFlight: Promise<boolean> | null = null;
	let courseMenuOpen = $state(false);
	let courseMenuLoading = $state(false);
	let courseMenuError = $state<string | null>(null);
	let visibleCourses = $state<Course[]>([]);
	let courseTabGroupElement: HTMLDivElement | null = null;

	function scrollToTopOfApp() {
		if (!browser) {
			return;
		}

		window.scrollTo({ top: 0, behavior: 'auto' });

		const appContent = document.querySelector('.app-content');
		if (appContent instanceof HTMLElement) {
			appContent.scrollTo({ top: 0, behavior: 'auto' });
		}

		const viewContent = document.querySelector('.view-content');
		if (viewContent instanceof HTMLElement) {
			viewContent.scrollTo({ top: 0, behavior: 'auto' });
		}
	}

	function handleDocumentPointerDown(event: PointerEvent) {
		if (!courseMenuOpen) {
			return;
		}

		const target = event.target;
		if (!(target instanceof Node)) {
			return;
		}

		if (courseTabGroupElement?.contains(target)) {
			return;
		}

		courseMenuOpen = false;
	}

	async function validateSession(): Promise<boolean> {
		if (Date.now() - lastSessionValidationAt < SESSION_VALIDATE_TTL_MS) {
			return true;
		}

		if (sessionValidationInFlight) {
			return sessionValidationInFlight;
		}

		sessionValidationInFlight = (async () => {
			const response = await fetch('/api/session/validate', { method: 'GET', cache: 'no-store' });
			if (!response.ok) {
				return false;
			}

			lastSessionValidationAt = Date.now();
			return true;
		})();

		try {
			return await sessionValidationInFlight;
		} finally {
			sessionValidationInFlight = null;
		}
	}

	async function handleFrameChange(frame: FrameName) {
		if (!allowedFrames.includes(frame)) {
			return;
		}

		if ($currentFrame === frame) {
			return;
		}

		try {
			const isValid = await validateSession();
			if (!isValid) {
				window.location.href = '/login';
				return;
			}

			currentFrame.set(frame);
			sidebarOpen.set(false);
		} catch (error) {
			console.error('Session validation error:', error);
			window.location.href = '/login';
		}
	}

	async function loadCourseMenuData() {
		courseMenuLoading = true;
		courseMenuError = null;

		try {
			visibleCourses = await fetchCourses();
		} catch (error) {
			courseMenuError = error instanceof Error ? error.message : 'Unable to load your courses right now.';
		} finally {
			courseMenuLoading = false;
		}
	}

	onMount(() => {
		void loadCourseMenuData();
		if (browser) {
			document.addEventListener('pointerdown', handleDocumentPointerDown, true);
		}
	});

	onDestroy(() => {
		if (browser) {
			document.removeEventListener('pointerdown', handleDocumentPointerDown, true);
		}
	});

	async function toggleCourseMenu() {
		if (!courseMenuOpen) {
			await loadCourseMenuData();
		}

		courseMenuOpen = !courseMenuOpen;
	}

	async function openCourse(courseId: number) {
		selectedCourseId.set(courseId);
		await handleFrameChange('courses');
		courseMenuOpen = false;
		sidebarOpen.set(false);
		requestAnimationFrame(() => {
			requestAnimationFrame(() => {
				scrollToTopOfApp();
			});
		});
	}

	function openCreateCourseComposer() {
		if (!canCreateCourse) {
			return;
		}
		courseMenuOpen = false;
		openCourseComposer();
	}

	function iconForFrame(frame: FrameName): string {
		return frameIcons[frame];
	}

	function getCourseRoleTag(course: Course): string {
		const instructorIdentifiers = [course.instructorId, course.instructorEmail]
			.map((value) => value?.trim().toLowerCase() || '')
			.filter((value) => value.length > 0);
		const teacherAssistantIdentifiers = [...(course.taIds || []), ...(course.taEmails || [])]
			.map((value) => value?.trim().toLowerCase() || '')
			.filter((value) => value.length > 0);

		const currentIdentifiers = [currentUserId, currentUserEmail].filter((value) => value.length > 0);
		if (currentIdentifiers.some((identifier) => instructorIdentifiers.includes(identifier))) {
			return 'Instructor';
		}
		if (currentIdentifiers.some((identifier) => teacherAssistantIdentifiers.includes(identifier))) {
			return 'Teacher Assistant';
		}
		return '';
	}
</script>

{#if $sidebarOpen}
    <div class="sidebar-backdrop" onclick={() => sidebarOpen.set(false)} aria-hidden="true"></div>
{/if}

<nav class="sidebar" class:open={$sidebarOpen}>
	<div class="sidebar-navigation">
	{#each framesBeforeCourses as frame}
		<button class="nav-link" class:active={activeFrame === frame} onclick={() => handleFrameChange(frame)}>
			<img class="nav-link-icon" src={iconForFrame(frame)} alt="" aria-hidden="true" />
			<span class="nav-link-label">{toFrameLabel(frame)}</span>
		</button>
	{/each}

	<div class="course-tab-group" bind:this={courseTabGroupElement}>
		<button class="nav-link" class:active={activeFrame === 'courses'} onclick={toggleCourseMenu}>
			<img class="nav-link-icon" src={iconForFrame('courses')} alt="" aria-hidden="true" />
			<span class="nav-link-label">{toFrameLabel('courses')}</span>
		</button>
		{#if courseMenuOpen}
			<div class="course-popout" role="menu" aria-label="Course list">
				<div class="course-popout-header">
					<span>Courses</span>
					{#if canCreateCourse}
						<button type="button" class="list-go-btn course-popout-create-btn" onclick={openCreateCourseComposer}>Create</button>
					{/if}
				</div>
				{#if courseMenuLoading}
					<p class="course-popout-state">Loading courses...</p>
				{:else if courseMenuError}
					<p class="course-popout-state">{courseMenuError}</p>
				{:else if visibleCourses.length === 0}
					<p class="course-popout-state">No courses found in the database.</p>
				{:else}
					<div class="course-popout-list">
						{#each visibleCourses as course}
							<button type="button" class="course-popout-item" class:active={$selectedCourseId === course.id} onclick={() => openCourse(course.id)}>
								<span class="course-dot" style={`background-color: ${course.color};`}></span>
								<span class="course-item-text">
									<span class="course-item-name">{course.name}</span>
									{#if course.code?.trim()}
										<span class="course-item-meta">{course.code}</span>
									{/if}
									{#if getCourseRoleTag(course)}
										<span class="course-role-tag course-role-tag-popout">{getCourseRoleTag(course)}</span>
									{/if}
								</span>
							</button>
						{/each}
					</div>
				{/if}
			</div>
		{/if}
	</div>

	{#each framesAfterCourses as frame}
		<button class="nav-link" class:active={activeFrame === frame} onclick={() => handleFrameChange(frame)}>
			<img class="nav-link-icon" src={iconForFrame(frame)} alt="" aria-hidden="true" />
			<span class="nav-link-label">{toFrameLabel(frame)}</span>
		</button>
		{#if frame === 'chat' && allowedFrames.includes('help')}
			<button class="nav-link mobile-help-link" class:active={activeFrame === 'help'} onclick={() => handleFrameChange('help')}>
				<img class="nav-link-icon" src={iconForFrame('help')} alt="" aria-hidden="true" />
				<span class="nav-link-label">{toFrameLabel('help')}</span>
			</button>
		{/if}
	{/each}
	</div>

	{#if allowedFrames.includes('help')}
		<div class="sidebar-footer desktop-help-footer">
		<button class="nav-link" class:active={activeFrame === 'help'} onclick={() => handleFrameChange('help')}>
			<img class="nav-link-icon" src={iconForFrame('help')} alt="" aria-hidden="true" />
			<span class="nav-link-label">{toFrameLabel('help')}</span>
		</button>
		</div>
	{/if}
</nav>
