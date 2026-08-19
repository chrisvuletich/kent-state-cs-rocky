<script lang="ts">
	import '$lib/styles/components/modules/sidebar.css';
	import { page } from '$app/state';
	import { browser } from '$app/environment';
	import { onDestroy, onMount, tick } from 'svelte';
	import { fetchCourses } from '$lib/api/content';
	import type { Course } from '$lib/types/course';
	import { openCourseComposer } from '$lib/stores/courseComposerStore';
	import { framesForRole, toFrameLabel, type FrameName } from '$lib/types/frame';
	import { sidebarOpen } from '$lib/stores/sidebarStore';
	import { appHref, parseCourseId } from '$lib/navigation/appRoute';
	import { focusScope } from '$lib/actions/focusScope';

	const frameIcons: Record<FrameName, string> = {
		dashboard: '/dashboard-icon.svg',
		analytics: '/analytics-icon.svg',
		users: '/users-icon.svg',
		courses: '/courses-icon.svg',
		admin: '/admin-icon.svg',
		audit: '/analytics-icon.svg',
		'api-keys': '/api-key-icon.svg',
		account: '/account-icon.svg',
		chat: '/chat-icon.svg',
		help: '/help-icon.svg'
	};

	const isAdmin = $derived(Boolean(page.data.currentUser?.isAdmin));
	const currentUserDisplayName = $derived(page.data.currentUser?.displayName?.trim() || '');
	const currentUserFirstName = $derived(page.data.currentUser?.firstName?.trim() || '');
	const currentUserLastName = $derived(page.data.currentUser?.lastName?.trim() || '');
	const currentUserId = $derived(page.data.currentUser?.id?.trim().toLowerCase() || '');
	const currentUserFullName = $derived(
		[currentUserFirstName, currentUserLastName]
			.filter((value) => value.length > 0)
			.join(' ')
			.trim()
	);
	const currentUserEmail = $derived(page.data.currentUser?.email?.trim().toLowerCase() || '');
	const allowedFrames = $derived(framesForRole(isAdmin));
	const primaryFrames = $derived(allowedFrames.filter((frame) => frame !== 'help'));
	const coursesFrameIndex = $derived(primaryFrames.indexOf('courses'));
	const framesBeforeCourses = $derived(
		coursesFrameIndex >= 0
			? primaryFrames.slice(0, coursesFrameIndex)
			: primaryFrames.filter((frame) => frame !== 'courses')
	);
	const framesAfterCourses = $derived(
		coursesFrameIndex >= 0 ? primaryFrames.slice(coursesFrameIndex + 1) : []
	);
	const canCreateCourse = $derived(isAdmin);
	let activeFrame = $derived(page.data.initialFrame as FrameName);
	let activeCourseId = $derived(parseCourseId(page.url.searchParams.get('course')));
	let courseMenuOpen = $state(false);
	let courseMenuLoading = $state(false);
	let courseMenuError = $state<string | null>(null);
	let visibleCourses = $state<Course[]>([]);
	let courseTabGroupElement: HTMLDivElement | null = null;
	let courseDisclosureButton = $state<HTMLButtonElement | null>(null);
	let courseMenuElement = $state<HTMLDivElement | null>(null);
	let isMobile = $state(false);
	let mobileMediaQuery: MediaQueryList | null = null;

	function focusFirstCourseMenuItem() {
		const firstVisibleItem = Array.from(
			courseMenuElement?.querySelectorAll<HTMLElement>('button, a[href]') ?? []
		).find((item) => item.getClientRects().length > 0);
		firstVisibleItem?.focus();
	}

	function handleViewportChange(event: MediaQueryListEvent | MediaQueryList) {
		isMobile = event.matches;
		if (!isMobile) {
			sidebarOpen.set(false);
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

	async function loadCourseMenuData() {
		courseMenuLoading = true;
		courseMenuError = null;

		try {
			visibleCourses = await fetchCourses();
		} catch (error) {
			courseMenuError =
				error instanceof Error ? error.message : 'Unable to load your courses right now.';
		} finally {
			courseMenuLoading = false;
			await tick();
			if (courseMenuOpen && !courseMenuElement?.contains(document.activeElement)) {
				focusFirstCourseMenuItem();
			}
		}
	}

	onMount(() => {
		void loadCourseMenuData();
		if (browser) {
			mobileMediaQuery = window.matchMedia('(max-width: 768px)');
			handleViewportChange(mobileMediaQuery);
			mobileMediaQuery.addEventListener('change', handleViewportChange);
			document.addEventListener('pointerdown', handleDocumentPointerDown, true);
		}
	});

	onDestroy(() => {
		if (browser) {
			mobileMediaQuery?.removeEventListener('change', handleViewportChange);
			document.removeEventListener('pointerdown', handleDocumentPointerDown, true);
		}
	});

	async function toggleCourseMenu() {
		if (courseMenuOpen) {
			courseMenuOpen = false;
			return;
		}

		courseMenuOpen = true;
		if (!courseMenuLoading) void loadCourseMenuData();
		await tick();
		focusFirstCourseMenuItem();
	}

	async function closeCourseMenu(restoreFocus = false) {
		courseMenuOpen = false;
		if (restoreFocus) {
			await tick();
			courseDisclosureButton?.focus();
		}
	}

	function handleSidebarEscape() {
		if (courseMenuOpen) {
			void closeCourseMenu(true);
			return;
		}
		sidebarOpen.set(false);
	}

	function handleSidebarKeydown(event: KeyboardEvent) {
		if (!isMobile && courseMenuOpen && event.key === 'Escape') {
			event.preventDefault();
			void closeCourseMenu(true);
		}
	}

	function handleCourseMenuFocusOut(event: FocusEvent) {
		if (
			courseMenuOpen &&
			(!(event.relatedTarget instanceof Node) ||
				!courseTabGroupElement?.contains(event.relatedTarget))
		) {
			courseMenuOpen = false;
		}
	}

	function closeCourseNavigation() {
		courseMenuOpen = false;
		sidebarOpen.set(false);
	}

	function closeSidebar() {
		courseMenuOpen = false;
		sidebarOpen.set(false);
	}

	function hrefForFrame(frame: FrameName): string {
		return appHref(page.url, { frame });
	}

	function hrefForCourse(courseId: number): string {
		return appHref(page.url, { frame: 'courses', courseId });
	}

	function openCreateCourseComposer() {
		if (!canCreateCourse) {
			return;
		}
		courseMenuOpen = false;
		openCourseComposer(courseDisclosureButton);
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

		const currentIdentifiers = [currentUserId, currentUserEmail].filter(
			(value) => value.length > 0
		);
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
	<div
		class="sidebar-backdrop"
		data-focus-scope-allow
		onclick={closeSidebar}
		aria-hidden="true"
	></div>
{/if}

<nav
	id="rocky-sidebar-navigation"
	class="sidebar"
	class:open={$sidebarOpen}
	inert={isMobile && !$sidebarOpen}
	aria-hidden={isMobile && !$sidebarOpen ? 'true' : undefined}
	onkeydown={handleSidebarKeydown}
	use:focusScope={{
		active: isMobile && $sidebarOpen,
		initialFocus: '[aria-current="page"]',
		onEscape: handleSidebarEscape
	}}
>
	<div class="sidebar-navigation">
		{#each framesBeforeCourses as frame}
			<a
				href={hrefForFrame(frame)}
				class="nav-link"
				class:active={activeFrame === frame}
				aria-current={activeFrame === frame ? 'page' : undefined}
				onclick={closeSidebar}
			>
				<img class="nav-link-icon" src={iconForFrame(frame)} alt="" aria-hidden="true" />
				<span class="nav-link-label">{toFrameLabel(frame)}</span>
			</a>
		{/each}

		<div
			class="course-tab-group"
			bind:this={courseTabGroupElement}
			onfocusout={handleCourseMenuFocusOut}
		>
			<button
				bind:this={courseDisclosureButton}
				class="nav-link"
				class:active={activeFrame === 'courses'}
				type="button"
				aria-expanded={courseMenuOpen}
				aria-controls="rocky-course-menu"
				aria-current={activeFrame === 'courses' && activeCourseId === null ? 'page' : undefined}
				onclick={toggleCourseMenu}
			>
				<img class="nav-link-icon" src={iconForFrame('courses')} alt="" aria-hidden="true" />
				<span class="nav-link-label">{toFrameLabel('courses')}</span>
			</button>
			{#if courseMenuOpen}
				<div
					bind:this={courseMenuElement}
					id="rocky-course-menu"
					class="course-popout"
					role="group"
					aria-label="Course list"
				>
					<div class="course-popout-header">
						<span>Courses</span>
						{#if canCreateCourse}
							<button
								type="button"
								class="list-go-btn course-popout-create-btn"
								onclick={openCreateCourseComposer}>Create</button
							>
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
								<a
									href={hrefForCourse(course.id)}
									class="course-popout-item"
									class:active={activeCourseId === course.id}
									aria-current={activeFrame === 'courses' && activeCourseId === course.id
										? 'page'
										: undefined}
									onclick={closeCourseNavigation}
								>
									<span class="course-dot" style={`background-color: ${course.color};`}></span>
									<span class="course-item-text">
										<span class="course-item-name">{course.name}</span>
										{#if course.code?.trim()}
											<span class="course-item-meta">{course.code}</span>
										{/if}
										{#if getCourseRoleTag(course)}
											<span class="course-role-tag course-role-tag-popout"
												>{getCourseRoleTag(course)}</span
											>
										{/if}
									</span>
								</a>
							{/each}
						</div>
					{/if}
				</div>
			{/if}
		</div>

		{#each framesAfterCourses as frame}
			<a
				href={hrefForFrame(frame)}
				class="nav-link"
				class:active={activeFrame === frame}
				aria-current={activeFrame === frame ? 'page' : undefined}
				onclick={closeSidebar}
			>
				<img class="nav-link-icon" src={iconForFrame(frame)} alt="" aria-hidden="true" />
				<span class="nav-link-label">{toFrameLabel(frame)}</span>
			</a>
			{#if frame === 'chat' && allowedFrames.includes('help')}
				<a
					href={hrefForFrame('help')}
					class="nav-link mobile-help-link"
					class:active={activeFrame === 'help'}
					aria-current={activeFrame === 'help' ? 'page' : undefined}
					onclick={closeSidebar}
				>
					<img class="nav-link-icon" src={iconForFrame('help')} alt="" aria-hidden="true" />
					<span class="nav-link-label">{toFrameLabel('help')}</span>
				</a>
			{/if}
		{/each}
	</div>

	{#if allowedFrames.includes('help')}
		<div class="sidebar-footer desktop-help-footer">
			<a
				href={hrefForFrame('help')}
				class="nav-link"
				class:active={activeFrame === 'help'}
				aria-current={activeFrame === 'help' ? 'page' : undefined}
				onclick={closeSidebar}
			>
				<img class="nav-link-icon" src={iconForFrame('help')} alt="" aria-hidden="true" />
				<span class="nav-link-label">{toFrameLabel('help')}</span>
			</a>
		</div>
	{/if}
</nav>
