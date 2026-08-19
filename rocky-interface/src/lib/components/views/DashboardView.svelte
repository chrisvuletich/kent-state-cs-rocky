<script lang="ts">
	import { page } from '$app/stores';
	import { onMount, tick } from 'svelte';
	import { fetchCourses } from '$lib/api/content';
	import CourseCard from '$lib/components/cards/CourseCard.svelte';
	import ViewShell from '$lib/components/ViewShell.svelte';
	import { openCourseComposer } from '$lib/stores/courseComposerStore';
	import { appHref } from '$lib/navigation/appRoute';
	import type { Course } from '$lib/types/course';

	let viewMode: 'card' | 'list' = 'card';
	let showViewMenu = false;
	let courses: Course[] = [];
	let isLoading = true;
	let error: string | null = null;
	let recentChats: Array<{ conversation_id: string; title?: string }> = [];
	let chatsError: string | null = null;
	let chatsLoading = true;
	let viewMenuButton: HTMLButtonElement | null = null;
	let viewMenu: HTMLDivElement | null = null;
	let viewSwitcher: HTMLDivElement | null = null;

	$: canCreateCourse = Boolean($page.data.currentUser?.isAdmin);
	$: currentUserDisplayName = $page.data.currentUser?.displayName?.trim() || '';
	$: currentUserFirstName = $page.data.currentUser?.firstName?.trim() || '';
	$: currentUserLastName = $page.data.currentUser?.lastName?.trim() || '';
	$: currentUserId = $page.data.currentUser?.id?.trim().toLowerCase() || '';
	$: currentUserFullName = [currentUserFirstName, currentUserLastName]
		.filter((value) => value.length > 0)
		.join(' ')
		.trim();
	$: currentUserEmail = $page.data.currentUser?.email?.trim().toLowerCase() || '';

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

	async function loadCourses(): Promise<void> {
		isLoading = true;
		error = null;
		try {
			courses = await fetchCourses();
		} catch (err) {
			error = err instanceof Error ? err.message : 'An error occurred while loading courses.';
		} finally {
			isLoading = false;
		}
	}

	async function loadRecentChats(): Promise<void> {
		chatsLoading = true;
		chatsError = null;
		try {
			const conversationResponse = await fetch('/api/chat/conversations', { method: 'POST' });
			const conversationData = await conversationResponse.json().catch(() => ({}));
			if (conversationResponse.ok && Array.isArray(conversationData?.conversations)) {
				recentChats = conversationData.conversations.slice(0, 5);
			} else {
				chatsError = 'Recent chats are unavailable right now.';
			}
		} catch {
			chatsError = 'Recent chats are unavailable right now.';
		} finally {
			chatsLoading = false;
		}
	}

	onMount(() => {
		void loadCourses();
		void loadRecentChats();
	});

	async function closeViewMenu(restoreFocus = true) {
		showViewMenu = false;
		await tick();
		if (restoreFocus) viewMenuButton?.focus();
	}

	async function toggleViewMenu() {
		if (showViewMenu) {
			await closeViewMenu();
			return;
		}
		showViewMenu = true;
		await tick();
		viewMenu?.querySelector<HTMLElement>('[aria-pressed="true"]')?.focus();
	}

	function setView(mode: 'card' | 'list') {
		viewMode = mode;
		void closeViewMenu();
	}

	function handleViewMenuKeydown(event: KeyboardEvent) {
		if (showViewMenu && event.key === 'Escape') {
			event.preventDefault();
			void closeViewMenu();
		}
	}

	function handleViewMenuFocusOut(event: FocusEvent) {
		if (
			showViewMenu &&
			(!(event.relatedTarget instanceof Node) || !viewSwitcher?.contains(event.relatedTarget))
		) {
			showViewMenu = false;
		}
	}

	function handleViewMenuPointerDown(event: PointerEvent) {
		if (showViewMenu && event.target instanceof Node && !viewSwitcher?.contains(event.target)) {
			void closeViewMenu(false);
		}
	}

	function handleCreateCourse() {
		if (!canCreateCourse) {
			return;
		}
		openCourseComposer();
	}

	function chatLabel(chat: { title?: string }): string {
		return chat.title?.trim() || 'Untitled chat';
	}
</script>

<svelte:window onkeydown={handleViewMenuKeydown} onpointerdown={handleViewMenuPointerDown} />

<ViewShell title="Dashboard">
	<div slot="actions" class="dashboard-actions">
		{#if canCreateCourse}
			<button class="view-btn" onclick={handleCreateCourse}>Create Course</button>
		{/if}
		<div bind:this={viewSwitcher} class="view-switcher" onfocusout={handleViewMenuFocusOut}>
			<button
				bind:this={viewMenuButton}
				class="view-btn"
				type="button"
				aria-expanded={showViewMenu}
				aria-controls="dashboard-view-menu"
				onclick={toggleViewMenu}
			>
				View
				<svg
					xmlns="http://www.w3.org/2000/svg"
					width="14"
					height="14"
					viewBox="0 0 24 24"
					fill="none"
					stroke="currentColor"
					stroke-width="2"
					stroke-linecap="round"
					stroke-linejoin="round"
				>
					<polyline points="6 9 12 15 18 9"></polyline>
				</svg>
			</button>

			{#if showViewMenu}
				<button
					type="button"
					class="view-menu-backdrop"
					aria-label="Close view menu"
					onclick={() => closeViewMenu()}
				></button>
				<div
					bind:this={viewMenu}
					id="dashboard-view-menu"
					class="view-menu"
					role="group"
					aria-label="Dashboard layout"
				>
					<button
						class="view-option"
						class:active={viewMode === 'card'}
						type="button"
						aria-pressed={viewMode === 'card'}
						onclick={() => setView('card')}
					>
						<svg
							xmlns="http://www.w3.org/2000/svg"
							width="16"
							height="16"
							viewBox="0 0 24 24"
							fill="none"
							stroke="currentColor"
							stroke-width="2"
							stroke-linecap="round"
							stroke-linejoin="round"
						>
							<rect x="3" y="3" width="7" height="7"></rect>
							<rect x="14" y="3" width="7" height="7"></rect>
							<rect x="14" y="14" width="7" height="7"></rect>
							<rect x="3" y="14" width="7" height="7"></rect>
						</svg>
						Card
					</button>
					<button
						class="view-option"
						class:active={viewMode === 'list'}
						type="button"
						aria-pressed={viewMode === 'list'}
						onclick={() => setView('list')}
					>
						<svg
							xmlns="http://www.w3.org/2000/svg"
							width="16"
							height="16"
							viewBox="0 0 24 24"
							fill="none"
							stroke="currentColor"
							stroke-width="2"
							stroke-linecap="round"
							stroke-linejoin="round"
						>
							<line x1="8" y1="6" x2="21" y2="6"></line>
							<line x1="8" y1="12" x2="21" y2="12"></line>
							<line x1="8" y1="18" x2="21" y2="18"></line>
							<line x1="3" y1="6" x2="3.01" y2="6"></line>
							<line x1="3" y1="12" x2="3.01" y2="12"></line>
							<line x1="3" y1="18" x2="3.01" y2="18"></line>
						</svg>
						List
					</button>
				</div>
			{/if}
		</div>
	</div>

	<div class="dashboard-main-grid">
		<div class="section section-flat dashboard-courses">
			{#if isLoading}
				<div class="empty-state">
					<p>Loading courses...</p>
				</div>
			{:else if error}
				<div class="empty-state">
					<p><strong>Error:</strong> {error}</p>
					<button class="view-btn" type="button" onclick={loadCourses}>Try again</button>
				</div>
			{:else if courses.length === 0}
				<div class="empty-state">
					<p>No courses available.</p>
				</div>
			{:else if viewMode === 'card'}
				<div class="grid grid-3">
					{#each courses as course}
						<CourseCard
							{course}
							href={appHref($page.url, { frame: 'courses', courseId: course.id })}
							mode="card"
							roleTag={getCourseRoleTag(course)}
						/>
					{/each}
				</div>
			{:else}
				<div class="grid grid-1">
					{#each courses as course}
						<CourseCard
							{course}
							href={appHref($page.url, { frame: 'courses', courseId: course.id })}
							mode="list"
							roleTag={getCourseRoleTag(course)}
						/>
					{/each}
				</div>
			{/if}
		</div>
		<aside class="recent-chats-card" aria-label="Recent chats">
			<div class="recent-chats-heading">
				<h2>Recent Chats</h2>
				<a class="recent-chats-all" href={appHref($page.url, { frame: 'chat' })}>View all</a>
			</div>
			{#if chatsLoading}<p class="recent-chats-note">Loading recent chats…</p>
			{:else if chatsError}<p class="recent-chats-note">{chatsError}</p>
				<button class="view-btn" type="button" onclick={loadRecentChats}>Try again</button>
			{:else if recentChats.length === 0}<p class="recent-chats-note">No recent chats yet.</p>
			{:else}<div class="recent-chats-list">
					{#each recentChats as chat (chat.conversation_id)}<a
							class="recent-chat-button"
							href={appHref($page.url, {
								frame: 'chat',
								conversationId: chat.conversation_id
							})}>{chatLabel(chat)}</a
						>{/each}
				</div>{/if}
		</aside>
	</div>
</ViewShell>
