<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { page } from '$app/stores';
	import {
		addCourseMembers,
		addGroupMember as addCourseGroupMember,
		createCourseGroup as createCourseGroupRequest,
		deleteCourseApiKey,
		fetchCourseApiKeys,
		fetchCourseApiHistory,
		removeCourseMember,
		removeGroupMember as removeCourseGroupMember,
		regenerateCourseApiKey,
		updateCourseActiveStatus,
		updateCourseApiKeyStatus,
		updateCourseGroupKeyLimit,
		updateCourseInstructorKeyLimit,
		updateCourseInstructorHandoutLimit,
		updateCourseMemberKeyLimit,
		updateCourseMetadata
	} from '$lib/api/courses';
	import { fetchCourseDetails, fetchCourseGroups, fetchCourses } from '$lib/api/content';
	import { fetchUsersForViews } from '$lib/api/users';
	import { selectedCourseId } from '$lib/stores/courseStore';
	import ViewShell from '$lib/components/ViewShell.svelte';
	import CourseEditorCard from '$lib/components/cards/CourseEditorCard.svelte';
	import CourseKeySlotCard from '$lib/components/cards/CourseKeySlotCard.svelte';
	import {
		COURSE_EDITOR_DEFAULT_COLOR,
		COURSE_EDITOR_SEMESTER_YEAR_MAX,
		COURSE_EDITOR_SEMESTER_YEAR_MIN
	} from '$lib/config/courseEditor';
	import { showErrorFeedback } from '$lib/stores/feedbackStore';
	import type { Course, CourseApiKeySummary, CourseDetail, CourseGroup } from '$lib/types/course';
	import type { User } from '$lib/types/user';
	import type { CourseApiHistoryEntry, CourseApiKeySummaryResponse } from '$lib/api/courses';

	type CourseTab =
		| 'home'
		| 'students'
		| 'groups'
		| 'edit-roster'
		| 'edit-groups'
		| 'course-settings'
		| `group:${string}`;
	type KeySlot = {
		slotIndex: number;
		baseKeyName: string;
		hasExistingKey: boolean;
		isActive: boolean;
		key: CourseApiKeySummary | null;
	};
	type RosterEntry = CourseDetail['members'][number] & {
		isInstructor: boolean;
		isTeacherAssistant: boolean;
	};
	const API_KEY_PREFIX = 'sk_kent_';

	function buildMaskedApiKeyPreview(maskLength: number): string {
		return `${API_KEY_PREFIX}${'*'.repeat(maskLength)}`;
	}

	function isSelectedCourseActive(): boolean {
		return selectedCourse?.isActive !== false;
	}

	function ensureCourseIsEditable(): boolean {
		if (isSelectedCourseActive()) {
			return true;
		}
		showErrorFeedback('Course is closed. Reopen it to make changes.');
		return false;
	}

	let isSelectedCourseClosed = false;
	let courseStatusActionPending = false;
	let pendingCourseStatusValue: boolean | null = null;

	let allCourses: Course[] = [];
	let allUsers: User[] = [];
	let baseVisibleCourses: Course[] = [];
	let visibleCourses: Course[] = [];
	let detailsByCourseId: Record<number, CourseDetail> = {};
	let groupsByCourseId: Record<number, CourseGroup[]> = {};
	let activeTab: CourseTab = 'home';
	let isLoading = true;
	let error: string | null = null;
	let editCourseForm = {
		name: '',
		code: '',
		semester: '',
		color: COURSE_EDITOR_DEFAULT_COLOR,
		instructorId: '',
		taIds: [] as string[]
	};
	let newGroupName = '';
	let pendingGroupMemberIdByGroupId: Record<string, string> = {};
	let importCsvInput: HTMLInputElement | null = null;
	let previewApiKey: string | null = null;
	let apiKeyActionError: string | null = null;
	let courseApiHistory: CourseApiHistoryEntry[] = [];
	let courseApiHistoryLoading = false;
	let courseApiHistoryError: string | null = null;
	let loadedCourseApiHistoryForId: number | null = null;
	let lastSelectedCourseId: number | null = null;
	let courseApiKeys: CourseApiKeySummary[] = [];
	let courseApiKeysLoading = false;
	let courseApiKeysError: string | null = null;
	let loadedCourseApiKeysForId: number | null = null;
	let newPersonalKeyName = '';
	let newGroupKeyNameByGroupId: Record<string, string> = {};
	let pendingMemberKeyLimitById: Record<string, number> = {};
	let pendingInstructorKeyLimit = 2;
	let pendingInstructorHandoutLimit = 2;
	let pendingGroupKeyLimitById: Record<string, number> = {};
	let editedSlotKeyNamesById: Record<string, string> = {};
	let selectedInstructorStudentId = '';
	let selectedInstructorGroupId = '';
	let rosterEntries: RosterEntry[] = [];
	let searchQuery = '';
	let sortByName = false;
	let showAddEmailPopup = false;
	let newMemberEmail = '';
	let addEmailError: string | null = null;

	function normalizeIdentifier(value: string | null | undefined): string {
		return value?.trim().toLowerCase() || '';
	}

	function parseSlotIndexFromKeyName(value: string | null | undefined): number {
		const normalized = value?.trim().toLowerCase() || '';
		const match = normalized.match(/^key-(\d+)$/);
		if (!match) {
			return 0;
		}
		const parsed = Number(match[1]);
		return Number.isInteger(parsed) && parsed > 0 ? parsed : 0;
	}

	$: filteredMembers =
		rosterEntries.filter((member) => {
			const q = searchQuery.toLowerCase().trim();

			return (
				getMemberDisplayName(member)?.toLowerCase().includes(q) ||
				member.email?.toLowerCase().includes(q)
			);
		}) || [];

	$: sortedMembers = sortByName
		? [...filteredMembers].sort((a, b) =>
				getMemberDisplayName(a).localeCompare(getMemberDisplayName(b))
			)
		: filteredMembers;

	function getMemberIdentifier(member: CourseDetail['members'][number]): string {
		const emailIdentifier = normalizeIdentifier(member.email);
		if (emailIdentifier && emailIdentifier !== 'n/a') {
			return emailIdentifier;
		}
		return normalizeIdentifier(member.id);
	}

	function getMemberDisplayName(member: CourseDetail['members'][number]): string {
		const currentSessionUser = $page.data.currentUser;
		if (
			currentSessionUser &&
			normalizeIdentifier(currentSessionUser.email) === normalizeIdentifier(member.email)
		) {
			return currentSessionUser.displayName || member.name || currentSessionUser.email;
		}

		const matchedUser = allUsers.find(
			(user) => normalizeIdentifier(user.email) === normalizeIdentifier(member.email)
		);
		if (matchedUser) {
			return matchedUser.displayName || member.name || matchedUser.email;
		}

		if (member.name) {
			return member.name;
		}

		const email = member.email.trim();
		return email ? 'Pending user' : 'Unknown user';
	}

	function getCourseInstructorRosterEntry() {
		if (!selectedCourse) {
			return null;
		}

		const instructorEmail = selectedCourse.instructorEmail?.trim().toLowerCase() || '';
		const instructorMember = instructorEmail
			? (selectedDetail?.members || []).find(
					(member) => normalizeIdentifier(member.email) === instructorEmail
				)
			: undefined;

		return {
			id: selectedCourse.instructorId || instructorMember?.id || null,
			name: selectedCourse.instructor?.trim() || instructorMember?.name || null,
			email: selectedCourse.instructorEmail || instructorMember?.email || '',
			keyLimit: selectedCourse.instructorKeyLimit || 2
		};
	}

	function getCourseTeacherAssistantRosterEntries(): RosterEntry[] {
		if (!selectedCourse) {
			return [];
		}

		const courseTaIdentifiers = [
			...(selectedCourse.taIds || []),
			...(selectedCourse.taEmails || [])
		]
			.map(normalizeIdentifier)
			.filter(Boolean);
		if (!courseTaIdentifiers.length) {
			return [];
		}

		const entries: RosterEntry[] = [];
		for (const identifier of courseTaIdentifiers) {
			const matchedUser = allUsers.find((user) => {
				const userIdentifiers = [
					normalizeIdentifier(user.id),
					normalizeIdentifier(user.email)
				].filter(Boolean);
				return userIdentifiers.includes(identifier);
			});
			const matchedMember = (selectedDetail?.members || []).find((member) => {
				const memberIdentifiers = [
					normalizeIdentifier(member.id),
					normalizeIdentifier(member.email)
				].filter(Boolean);
				return memberIdentifiers.includes(identifier);
			});

			const email = matchedUser?.email || matchedMember?.email || '';
			if (!email) {
				continue;
			}

			entries.push({
				id: matchedUser?.id || matchedMember?.id || null,
				name: matchedUser?.displayName || matchedMember?.name || null,
				email,
				keyLimit: selectedCourse.instructorKeyLimit || 2,
				isInstructor: false,
				isTeacherAssistant: true
			});
		}

		const seen = new Set<string>();
		return entries.filter((entry) => {
			const key = normalizeIdentifier(entry.email) || normalizeIdentifier(entry.id);
			if (!key || seen.has(key)) {
				return false;
			}
			seen.add(key);
			return true;
		});
	}

	function getRosterEntries(): RosterEntry[] {
		const instructorEntry = getCourseInstructorRosterEntry();
		const teacherAssistantEntries = getCourseTeacherAssistantRosterEntries();
		const members = selectedDetail?.members || [];
		const teacherAssistantIdentifiers = new Set(
			teacherAssistantEntries
				.flatMap((entry) => [normalizeIdentifier(entry.id), normalizeIdentifier(entry.email)])
				.filter(Boolean)
		);
		const instructorIdentifiers = new Set(
			instructorEntry
				? [
						normalizeIdentifier(instructorEntry.id),
						normalizeIdentifier(instructorEntry.email)
					].filter(Boolean)
				: []
		);
		const managerIdentifiers = new Set([...teacherAssistantIdentifiers, ...instructorIdentifiers]);
		if (!instructorEntry) {
			return [
				...teacherAssistantEntries,
				...members
					.filter((member) => {
						const memberIdentifiers = [
							normalizeIdentifier(member.id),
							normalizeIdentifier(member.email)
						].filter(Boolean);
						return !memberIdentifiers.some((identifier) => managerIdentifiers.has(identifier));
					})
					.map((member) => ({ ...member, isInstructor: false, isTeacherAssistant: false }))
			];
		}

		return [
			{
				...instructorEntry,
				isInstructor: true,
				isTeacherAssistant: false
			},
			...teacherAssistantEntries,
			...members
				.filter((member) => {
					const memberIdentifiers = [
						normalizeIdentifier(member.id),
						normalizeIdentifier(member.email)
					].filter(Boolean);
					return !memberIdentifiers.some((identifier) => managerIdentifiers.has(identifier));
				})
				.map((member) => ({
					...member,
					isInstructor: false,
					isTeacherAssistant: false
				}))
		];
	}

	function getRosterRole(entry: RosterEntry): string {
		if (entry.isInstructor) {
			return 'Instructor';
		}
		if (entry.isTeacherAssistant) {
			return 'Teacher Assistant';
		}
		return 'Student';
	}

	function getRosterKeyLimit(entry: RosterEntry): number {
		if (entry.isInstructor || entry.isTeacherAssistant) {
			return selectedCourse?.instructorKeyLimit ?? entry.keyLimit ?? 2;
		}
		return entry.keyLimit;
	}

	function currentUserMatchesCourseManager(): boolean {
		if (!selectedCourse) {
			return false;
		}
		const instructorIdentifiers = [selectedCourse.instructorId, selectedCourse.instructorEmail]
			.map(normalizeIdentifier)
			.filter(Boolean);
		const teacherAssistantIdentifiers = [
			...(selectedCourse.taIds || []),
			...(selectedCourse.taEmails || [])
		]
			.map(normalizeIdentifier)
			.filter(Boolean);
		const managerIdentifiers = [...instructorIdentifiers, ...teacherAssistantIdentifiers];
		const currentIdentifiers = [currentUserId, currentUserEmail]
			.map(normalizeIdentifier)
			.filter(Boolean);
		return currentIdentifiers.some((identifier) => managerIdentifiers.includes(identifier));
	}

	function memberMatchesCurrentUser(member: CourseDetail['members'][number]): boolean {
		const currentUserIdentifiers = [currentUserId, currentUserEmail]
			.map(normalizeIdentifier)
			.filter(Boolean);
		const memberIdentifiers = [
			normalizeIdentifier(member.id),
			normalizeIdentifier(member.email)
		].filter(Boolean);
		return currentUserIdentifiers.some((identifier) => memberIdentifiers.includes(identifier));
	}

	function groupContainsCurrentUser(group: CourseGroup): boolean {
		const currentUserIdentifiers = [currentUserId, currentUserEmail]
			.map(normalizeIdentifier)
			.filter(Boolean);
		const groupMemberIds = group.memberIds.map(normalizeIdentifier);
		return currentUserIdentifiers.some((identifier) => groupMemberIds.includes(identifier));
	}

	function resolveMemberByIdentifier(
		identifier: string
	): CourseDetail['members'][number] | undefined {
		const normalizedIdentifier = normalizeIdentifier(identifier);
		return (selectedDetail?.members || []).find((member) => {
			return (
				normalizeIdentifier(member.email) === normalizedIdentifier ||
				normalizeIdentifier(member.id) === normalizedIdentifier
			);
		});
	}

	function isGroupTab(tab: CourseTab): tab is `group:${string}` {
		return tab.startsWith('group:');
	}

	function getGroupIdFromTab(tab: `group:${string}`): string {
		return tab.slice('group:'.length);
	}

	function getTabLabel(tab: CourseTab): string {
		if (tab === 'home') {
			return 'Home';
		}
		if (tab === 'students') {
			return 'Students';
		}
		if (tab === 'groups') {
			return 'Groups';
		}
		if (tab === 'edit-roster') {
			return 'Edit Roster';
		}
		if (tab === 'edit-groups') {
			return 'Edit Groups';
		}
		if (tab === 'course-settings') {
			return 'Course Settings';
		}

		const groupId = getGroupIdFromTab(tab);
		const group = selectedGroups.find((candidate) => candidate.id === groupId);
		return group?.name || 'Group';
	}

	function resolveActiveStudentGroup(tab: CourseTab): CourseGroup | null {
		if (!isGroupTab(tab)) {
			return null;
		}

		const groupId = getGroupIdFromTab(tab);
		return studentVisibleGroups.find((group) => group.id === groupId) || null;
	}

	function buildKeySlots(limit: number, keys: CourseApiKeySummary[]): KeySlot[] {
		const storedKeys = keys.filter((key) => key.hasHash !== false);
		const highestStoredSlot = storedKeys.reduce(
			(maxSlot, key) => (key.slotIndex > maxSlot ? key.slotIndex : maxSlot),
			0
		);
		const totalSlots = Math.max(0, limit, highestStoredSlot, storedKeys.length);
		if (totalSlots === 0) {
			return [];
		}
		const slotEntries: Array<CourseApiKeySummary | null> = Array.from(
			{ length: totalSlots },
			() => null
		);
		const orderedKeys = [...storedKeys].sort((a, b) => {
			const aSlot = a.slotIndex > 0 ? a.slotIndex : Number.MAX_SAFE_INTEGER;
			const bSlot = b.slotIndex > 0 ? b.slotIndex : Number.MAX_SAFE_INTEGER;
			if (aSlot !== bSlot) {
				return aSlot - bSlot;
			}
			const createdOrder = a.created.localeCompare(b.created);
			if (createdOrder !== 0) {
				return createdOrder;
			}
			return a.keyId.localeCompare(b.keyId);
		});

		for (const key of orderedKeys) {
			if (key.hasHash === false) {
				continue;
			}
			const targetIndex = key.slotIndex > 0 ? key.slotIndex - 1 : -1;
			if (targetIndex >= 0 && targetIndex < totalSlots && slotEntries[targetIndex] === null) {
				slotEntries[targetIndex] = key;
				continue;
			}
			const fallbackIndex = slotEntries.findIndex((entry) => entry === null);
			if (fallbackIndex >= 0) {
				slotEntries[fallbackIndex] = key;
			}
		}

		return Array.from({ length: totalSlots }, (_, slotIndex) => {
			const existing = slotEntries[slotIndex];
			return {
				slotIndex,
				baseKeyName: existing?.keyName || `key-${slotIndex + 1}`,
				hasExistingKey: existing ? existing.hasHash !== false : false,
				isActive: existing ? existing.isActive !== false : true,
				key: existing || null
			};
		});
	}

	function getSlotStateId(
		ownerType: 'person' | 'group',
		ownerId: string,
		slotIndex: number
	): string {
		return `${ownerType}:${normalizeIdentifier(ownerId)}:${slotIndex}`;
	}

	function getSlotKeyName(slotStateId: string, fallbackName: string): string {
		return editedSlotKeyNamesById[slotStateId] ?? fallbackName;
	}

	function setSlotKeyName(slotStateId: string, nextName: string) {
		editedSlotKeyNamesById = {
			...editedSlotKeyNamesById,
			[slotStateId]: nextName
		};
	}

	async function generateKeyForSlot(
		ownerType: 'person' | 'group',
		ownerId: string,
		slotIndex: number,
		fallbackKeyName: string
	): Promise<string | null> {
		if (!ensureCourseIsEditable()) {
			return null;
		}
		if (!selectedCourse) {
			return null;
		}

		const slotStateId = getSlotStateId(ownerType, ownerId, slotIndex);
		const keyName = getSlotKeyName(slotStateId, fallbackKeyName).trim() || fallbackKeyName;

		try {
			apiKeyActionError = null;
			const response = await regenerateCourseApiKey(selectedCourse.id, {
				ownerType,
				ownerId: ownerType === 'person' ? ownerId : undefined,
				groupId: ownerType === 'group' ? ownerId : undefined,
				keyName,
				slotIndex: slotIndex + 1
			});

			editedSlotKeyNamesById = {
				...editedSlotKeyNamesById,
				[slotStateId]: keyName
			};
			upsertGeneratedApiKeySummary(response);
			return response.api_key?.trim() || null;
		} catch (err) {
			apiKeyActionError = err instanceof Error ? err.message : 'Unable to generate key.';
			showErrorFeedback(apiKeyActionError);
			return null;
		}
	}

	async function removeKeyForSlot(
		ownerType: 'person' | 'group',
		ownerId: string,
		slotIndex: number,
		fallbackKeyName: string
	): Promise<boolean> {
		if (!ensureCourseIsEditable()) {
			return false;
		}
		if (!selectedCourse) {
			return false;
		}

		const slotStateId = getSlotStateId(ownerType, ownerId, slotIndex);
		const keyName = getSlotKeyName(slotStateId, fallbackKeyName).trim() || fallbackKeyName;

		try {
			apiKeyActionError = null;
			const response = await deleteCourseApiKey(selectedCourse.id, {
				ownerType,
				ownerId: ownerType === 'person' ? ownerId : undefined,
				groupId: ownerType === 'group' ? ownerId : undefined,
				keyName,
				slotIndex: slotIndex + 1
			});
			const responseKey = response.key;
			const responseOwnerType =
				normalizeIdentifier(responseKey?.owner_type) === 'group' ? 'group' : 'person';
			const responseOwnerId = normalizeIdentifier(responseKey?.owner_id || ownerId);
			const responseKeyName = normalizeIdentifier(responseKey?.key_name || keyName);
			const responseSlotIndex =
				typeof responseKey?.slot_index === 'number' ? responseKey.slot_index : slotIndex + 1;
			courseApiKeys = courseApiKeys.map((entry) =>
				normalizeIdentifier(entry.ownerId) === responseOwnerId &&
				((entry.slotIndex > 0 && entry.slotIndex === responseSlotIndex) ||
					normalizeIdentifier(entry.keyName) === responseKeyName) &&
				entry.ownerType === responseOwnerType
					? {
							...entry,
							hasHash: false,
							isActive: false
						}
					: entry
			);
			return true;
		} catch (err) {
			apiKeyActionError = err instanceof Error ? err.message : 'Unable to remove key.';
			showErrorFeedback(apiKeyActionError);
			return false;
		}
	}

	async function setSlotActiveState(
		ownerType: 'person' | 'group',
		ownerId: string,
		slotIndex: number,
		fallbackKeyName: string,
		nextIsActive: boolean
	) {
		if (!ensureCourseIsEditable()) {
			return;
		}
		if (!selectedCourse) {
			return;
		}

		const slotStateId = getSlotStateId(ownerType, ownerId, slotIndex);
		const keyName = getSlotKeyName(slotStateId, fallbackKeyName).trim() || fallbackKeyName;

		try {
			apiKeyActionError = null;
			await updateCourseApiKeyStatus(selectedCourse.id, {
				ownerType,
				ownerId: ownerType === 'person' ? ownerId : undefined,
				groupId: ownerType === 'group' ? ownerId : undefined,
				keyName,
				slotIndex: slotIndex + 1,
				isActive: nextIsActive
			});

			courseApiKeys = courseApiKeys.map((entry) =>
				entry.ownerType === ownerType &&
				normalizeIdentifier(entry.ownerId) === normalizeIdentifier(ownerId) &&
				((entry.slotIndex > 0 && entry.slotIndex === slotIndex + 1) ||
					normalizeIdentifier(entry.keyName) === normalizeIdentifier(keyName))
					? {
							...entry,
							isActive: nextIsActive
						}
					: entry
			);
		} catch (err) {
			apiKeyActionError = err instanceof Error ? err.message : 'Unable to update API key status.';
		}
	}

	function getGroupOwnedKeys(
		groupId: string,
		availableKeys: CourseApiKeySummary[]
	): CourseApiKeySummary[] {
		return availableKeys.filter(
			(key) =>
				key.hasHash !== false && normalizeIdentifier(key.ownerId) === normalizeIdentifier(groupId)
		);
	}

	function getMemberOwnerId(member: CourseDetail['members'][number] | null): string {
		if (!member) {
			return '';
		}
		return member.id?.trim() || member.email?.trim() || '';
	}

	function getCourseInstructorOwnerId(
		course: Course | null,
		detail: CourseDetail | null,
		requesterId: string,
		requesterEmail: string
	): string {
		if (!course) {
			return '';
		}

		const instructorMember = (detail?.members || []).find((member) => {
			return (
				normalizeIdentifier(member.id) === normalizeIdentifier(course.instructorId) ||
				normalizeIdentifier(member.email) === normalizeIdentifier(course.instructorEmail)
			);
		});

		return (
			[
				course.instructorId,
				course.instructorEmail,
				instructorMember?.id,
				instructorMember?.email,
				requesterId,
				requesterEmail
			]
				.map((value) => value?.trim() || '')
				.find((value) => value.length > 0) || ''
		);
	}

	function getMemberOwnedKeys(
		member: CourseDetail['members'][number] | null,
		availableKeys: CourseApiKeySummary[]
	): CourseApiKeySummary[] {
		if (!member) {
			return [];
		}

		const ownerIdentifiers = [member.id, member.email].map(normalizeIdentifier).filter(Boolean);
		return availableKeys.filter(
			(key) =>
				key.hasHash !== false &&
				key.ownerType === 'person' &&
				ownerIdentifiers.includes(normalizeIdentifier(key.ownerId))
		);
	}

	function getPersonOwnedKeys(
		ownerIdentifiers: Array<string | null | undefined>,
		availableKeys: CourseApiKeySummary[]
	): CourseApiKeySummary[] {
		const normalizedOwnerIdentifiers = ownerIdentifiers.map(normalizeIdentifier).filter(Boolean);
		if (normalizedOwnerIdentifiers.length === 0) {
			return [];
		}

		return availableKeys.filter(
			(key) =>
				key.hasHash !== false &&
				key.ownerType === 'person' &&
				normalizedOwnerIdentifiers.includes(normalizeIdentifier(key.ownerId))
		);
	}

	function clearSensitiveKeyState() {
		previewApiKey = null;
		apiKeyActionError = null;
	}

	async function loadWorkspace() {
		isLoading = true;
		error = null;
		try {
			const requestList = [fetchCourses(), fetchCourseDetails(), fetchCourseGroups()] as const;
			const [courses, details, groups] = await Promise.all(requestList);
			const needsUsers = Boolean($page.data.currentUser?.isAdmin);
			const usersPromise = needsUsers ? fetchUsersForViews() : Promise.resolve([] as User[]);
			const users = await usersPromise;

			allCourses = courses;
			allUsers = users;
			detailsByCourseId = Object.fromEntries(details.map((detail) => [detail.id, detail]));
			groupsByCourseId = groups.reduce<Record<number, CourseGroup[]>>((acc, group) => {
				const existing = acc[group.courseId] || [];
				acc[group.courseId] = [...existing, group];
				return acc;
			}, {});

			if ($selectedCourseId === null && courses.length > 0) {
				selectedCourseId.set(courses[0].id);
			}
		} catch (err) {
			error = err instanceof Error ? err.message : 'An error occurred while loading course data.';
		} finally {
			isLoading = false;
		}
	}

	onMount(async () => {
		await loadWorkspace();
	});

	onDestroy(() => {
		clearSensitiveKeyState();
	});

	$: visibleCourses = baseVisibleCourses;
	$: selectedCourse = visibleCourses.find((course) => course.id === $selectedCourseId) ?? null;
	$: selectedDetail = selectedCourse ? detailsByCourseId[selectedCourse.id] : null;
	$: selectedGroups = selectedCourse ? groupsByCourseId[selectedCourse.id] || [] : [];
	$: selectedGroupIds = new Set(selectedGroups.map((group) => group.id));
	$: nonAdminUsers = allUsers.filter((user) => !user.isAdmin);
	$: accountUsers = allUsers.filter(
		(user) => !user.isAdmin && user.email && user.email.trim() && user.email !== 'N/A'
	);
	$: currentUserId = $page.data.currentUser?.id?.trim() || '';
	$: currentUserEmail = $page.data.currentUser?.email?.trim().toLowerCase() || '';
	$: isCurrentUserAdmin = Boolean($page.data.currentUser?.isAdmin);
	$: baseVisibleCourses = isCurrentUserAdmin
		? allCourses
		: allCourses.filter((course) => {
				const managerIdentifiers = [
					course.instructorId,
					course.instructorEmail,
					...(course.taIds || []),
					...(course.taEmails || [])
				]
					.map(normalizeIdentifier)
					.filter(Boolean);
				if (
					managerIdentifiers.includes(normalizeIdentifier(currentUserId)) ||
					managerIdentifiers.includes(currentUserEmail)
				) {
					return true;
				}
				const members = detailsByCourseId[course.id]?.members || [];
				return members.some((member) => {
					const memberId = normalizeIdentifier(member.id);
					const memberEmail = normalizeIdentifier(member.email);
					return (
						memberId === normalizeIdentifier(currentUserId) || memberEmail === currentUserEmail
					);
				});
			});
	$: isCurrentUserCourseInstructor = Boolean(
		selectedCourse &&
		[
			normalizeIdentifier(selectedCourse.instructorId),
			normalizeIdentifier(selectedCourse.instructorEmail)
		]
			.filter(Boolean)
			.some(
				(identifier) =>
					identifier === normalizeIdentifier(currentUserId) || identifier === currentUserEmail
			)
	);
	$: isCurrentUserCourseTeacherAssistant = Boolean(
		selectedCourse &&
		[
			...(selectedCourse.taIds || []).map(normalizeIdentifier),
			...(selectedCourse.taEmails || []).map(normalizeIdentifier)
		]
			.filter(Boolean)
			.some(
				(identifier) =>
					identifier === normalizeIdentifier(currentUserId) || identifier === currentUserEmail
			)
	);
	$: isCurrentUserClient = !isCurrentUserAdmin;
	$: canEditCourse = isCurrentUserAdmin;
	$: canEditPeopleAndGroups =
		isCurrentUserAdmin || isCurrentUserCourseInstructor || isCurrentUserCourseTeacherAssistant;
	$: studentGroup = selectedGroups.find((group) => groupContainsCurrentUser(group)) || null;
	$: studentMembers = selectedDetail?.members || [];
	$: groupedStudentIdSet = new Set(
		selectedGroups.flatMap((group) => group.memberIds.map((id) => normalizeIdentifier(id)))
	);
	$: ungroupedStudentMembers = studentMembers.filter(
		(member) => !groupedStudentIdSet.has(getMemberIdentifier(member))
	);
	$: memberByIdentifier = (() => {
		const lookup = new Map<string, CourseDetail['members'][number]>();
		for (const member of selectedDetail?.members || []) {
			const memberId = normalizeIdentifier(member.id);
			const memberEmail = normalizeIdentifier(member.email);
			if (memberId) {
				lookup.set(memberId, member);
			}
			if (memberEmail) {
				lookup.set(memberEmail, member);
			}
		}
		return lookup;
	})();
	$: studentGroupMembers = (() => {
		if (!studentGroup || !selectedDetail) {
			return [];
		}

		return studentGroup.memberIds
			.map((id) => memberByIdentifier.get(normalizeIdentifier(id)))
			.filter((member): member is NonNullable<typeof member> => Boolean(member));
	})();
	$: groupMembershipRows = selectedGroups.map((group) => ({
		group,
		members: group.memberIds
			.map((id) => memberByIdentifier.get(normalizeIdentifier(id)))
			.filter((member): member is NonNullable<typeof member> => Boolean(member))
	}));
	$: canViewManagerApiData =
		isCurrentUserAdmin || isCurrentUserCourseInstructor || isCurrentUserCourseTeacherAssistant;
	$: canViewCourseApiHistory = isCurrentUserAdmin;
	$: canViewPersonalApiData =
		isCurrentUserClient &&
		!isCurrentUserCourseInstructor &&
		!isCurrentUserCourseTeacherAssistant &&
		!studentGroup;
	$: personalOwnedKeys = courseApiKeys.filter(
		(key) =>
			key.hasHash !== false &&
			key.ownerType === 'person' &&
			[normalizeIdentifier(currentUserId), currentUserEmail].includes(
				normalizeIdentifier(key.ownerId)
			)
	);
	$: groupOwnedKeys = courseApiKeys.filter(
		(key) => key.hasHash !== false && key.ownerType === 'group' && selectedGroupIds.has(key.ownerId)
	);
	$: studentVisibleGroups = selectedGroups.filter((group) => groupContainsCurrentUser(group));
	$: instructorVisibleStudents = studentMembers;
	$: if (instructorVisibleStudents.length === 0) {
		selectedInstructorStudentId = '';
	} else if (
		!instructorVisibleStudents.some(
			(member) => getMemberIdentifier(member) === selectedInstructorStudentId
		)
	) {
		selectedInstructorStudentId = getMemberIdentifier(instructorVisibleStudents[0]);
	}
	$: if (selectedGroups.length === 0) {
		selectedInstructorGroupId = '';
	} else if (!selectedGroups.some((group) => group.id === selectedInstructorGroupId)) {
		selectedInstructorGroupId = selectedGroups[0].id;
	}
	$: selectedInstructorStudent =
		instructorVisibleStudents.find(
			(member) => getMemberIdentifier(member) === selectedInstructorStudentId
		) || null;
	$: selectedInstructorStudentOwnerId = getMemberOwnerId(selectedInstructorStudent);
	$: selectedInstructorStudentKeys = getMemberOwnedKeys(selectedInstructorStudent, courseApiKeys);
	$: instructorStudentKeyLimit = selectedInstructorStudent?.keyLimit ?? 0;
	$: instructorStudentKeySlots = selectedInstructorStudent
		? buildKeySlots(instructorStudentKeyLimit, selectedInstructorStudentKeys)
		: [];
	$: selectedInstructorGroup =
		selectedGroups.find((group) => group.id === selectedInstructorGroupId) || null;
	$: instructorGroupKeySlots = selectedInstructorGroup
		? buildKeySlots(
				selectedInstructorGroup.keyLimit,
				getGroupOwnedKeys(selectedInstructorGroup.id, groupOwnedKeys)
			)
		: [];
	$: courseInstructorOwnerId = getCourseInstructorOwnerId(
		selectedCourse,
		selectedDetail,
		currentUserId,
		currentUserEmail
	);
	$: courseInstructorKeyLimit = Math.max(0, selectedCourse?.instructorKeyLimit ?? 2);
	$: courseInstructorKeySlots = buildKeySlots(
		courseInstructorKeyLimit,
		getPersonOwnedKeys([courseInstructorOwnerId], courseApiKeys)
	);
	$: currentUserMember =
		(selectedDetail?.members || []).find((member) => memberMatchesCurrentUser(member)) || null;
	$: studentPersonalKeyOwnerId = normalizeIdentifier(currentUserId) || currentUserEmail;
	$: personalKeyLimit = currentUserMatchesCourseManager()
		? Math.max(0, selectedCourse?.instructorKeyLimit ?? 2)
		: (currentUserMember?.keyLimit ?? 0);
	$: personalKeySlots = buildKeySlots(personalKeyLimit, personalOwnedKeys);
	$: studentGroupTabs = studentVisibleGroups.map((group) => `group:${group.id}` as CourseTab);
	$: activeStudentGroup = resolveActiveStudentGroup(activeTab);
	$: activeStudentGroupKeySlots = activeStudentGroup
		? buildKeySlots(
				activeStudentGroup.keyLimit,
				getGroupOwnedKeys(activeStudentGroup.id, groupOwnedKeys)
			)
		: [];
	$: courseStudentKeyLimit = Math.max(0, selectedCourse?.instructorHandoutLimit ?? 2);
	$: if (selectedCourse) {
		pendingInstructorKeyLimit = Math.max(0, selectedCourse.instructorKeyLimit ?? 2);
		pendingInstructorHandoutLimit = Math.max(0, selectedCourse.instructorHandoutLimit ?? 2);
	}
	$: canGenerateApiKey = Boolean(
		selectedCourse &&
		(isCurrentUserAdmin ||
			isCurrentUserCourseInstructor ||
			isCurrentUserCourseTeacherAssistant ||
			(selectedDetail?.members || []).some((member) => memberMatchesCurrentUser(member)))
	);
	$: showCourseTabBar = availableTabs.length > 0;
	$: selectableGroupMembers = selectedDetail?.members || [];
	$: availableTabs = canEditPeopleAndGroups
		? ([
				'home',
				'students',
				'groups',
				'edit-roster',
				'edit-groups',
				...(canEditCourse ? (['course-settings'] as CourseTab[]) : [])
			] as CourseTab[])
		: (['home', ...studentGroupTabs] as CourseTab[]);
	$: if (!availableTabs.includes(activeTab)) {
		activeTab = 'home';
	}
	$: if (!selectedCourse && visibleCourses.length > 0) {
		selectedCourseId.set(visibleCourses[0].id);
	}
	$: if (selectedCourse) {
		const matchingUserByName = nonAdminUsers.find(
			(user) => user.displayName === selectedCourse.instructor
		);
		const matchingUserByEmail = selectedCourse.instructorEmail
			? allUsers.find(
					(user) =>
						normalizeIdentifier(user.email) === normalizeIdentifier(selectedCourse.instructorEmail)
				)
			: undefined;
		const normalizedCourseTaIds = (selectedCourse.taIds || [])
			.map(normalizeIdentifier)
			.filter(Boolean);
		const normalizedCourseTaEmails = (selectedCourse.taEmails || [])
			.map(normalizeIdentifier)
			.filter(Boolean);
		const matchedTaIds = allUsers
			.filter((user) => {
				const userId = normalizeIdentifier(user.id);
				const userEmail = normalizeIdentifier(user.email);
				return (
					normalizedCourseTaIds.includes(userId) || normalizedCourseTaEmails.includes(userEmail)
				);
			})
			.map((user) => user.id);
		editCourseForm = {
			name: selectedCourse.name,
			code: selectedCourse.code,
			semester: selectedCourse.semester,
			color: selectedCourse.color,
			instructorId:
				selectedCourse.instructorId || matchingUserByEmail?.id || matchingUserByName?.id || '',
			taIds: [...new Set(matchedTaIds)]
		};
	}
	$: if (
		selectedCourse &&
		canViewCourseApiHistory &&
		loadedCourseApiHistoryForId !== selectedCourse.id
	) {
		void loadCourseApiHistory(selectedCourse.id);
	}
	$: if (selectedCourse && loadedCourseApiKeysForId !== selectedCourse.id) {
		void loadCourseApiKeys(selectedCourse.id);
	}
	$: if (selectedCourse?.id && selectedCourse.id !== lastSelectedCourseId) {
		lastSelectedCourseId = selectedCourse.id;
		clearSensitiveKeyState();
		newPersonalKeyName = '';
		newGroupKeyNameByGroupId = {};
		pendingMemberKeyLimitById = {};
		pendingInstructorKeyLimit = 2;
		pendingInstructorHandoutLimit = 2;
		pendingGroupKeyLimitById = {};
	}
	$: isSelectedCourseClosed = selectedCourse?.isActive === false;
	$: {
		selectedCourse;
		selectedDetail;
		rosterEntries = getRosterEntries();
	}

	function setSelectedCourseHasApiKey(
		hasApiKey: boolean,
		keyState:
			| {
					apiKeyOwnerType?: 'person' | 'group' | null;
					apiKeyOwnerId?: string | null;
					apiKeyGroupCreatedBy?: string | null;
					apiKeyCreated?: string | null;
			  }
			| undefined = undefined
	) {
		if (!selectedCourse) {
			return;
		}

		allCourses = allCourses.map((course) =>
			course.id === selectedCourse.id
				? {
						...course,
						hasApiKey,
						apiKeyOwnerType: keyState?.apiKeyOwnerType ?? null,
						apiKeyOwnerId: keyState?.apiKeyOwnerId ?? null,
						apiKeyGroupCreatedBy: keyState?.apiKeyGroupCreatedBy ?? null,
						apiKeyCreated: keyState?.apiKeyCreated ?? null
					}
				: course
		);
	}

	async function refreshAfterWrite() {
		isLoading = true;
		loadedCourseApiHistoryForId = null;
		loadedCourseApiKeysForId = null;
		await loadWorkspace();
	}

	function normalizeApiKeySummaries(rawKeys: CourseApiKeySummaryResponse[]): CourseApiKeySummary[] {
		return rawKeys
			.map((entry) => ({
				keyId: entry.key_id?.trim() || '',
				ownerType: (entry.owner_type === 'group' ? 'group' : 'person') as 'person' | 'group',
				ownerId: entry.owner_id?.trim() || '',
				keyName: entry.key_name?.trim() || 'key-1',
				slotIndex:
					typeof entry.slot_index === 'number' &&
					Number.isInteger(entry.slot_index) &&
					entry.slot_index > 0
						? entry.slot_index
						: parseSlotIndexFromKeyName(entry.key_name),
				created: entry.created?.trim() || '',
				courseId: typeof entry.course_id === 'number' ? entry.course_id : selectedCourse?.id || 0,
				hasHash: entry.has_hash !== false,
				isActive: entry.is_active !== false
			}))
			.filter((entry) => entry.ownerId.length > 0 && entry.keyName.length > 0);
	}

	function upsertGeneratedApiKeySummary(
		response: NonNullable<Awaited<ReturnType<typeof regenerateCourseApiKey>>>
	) {
		const ownerType = (response.owner_type === 'group' ? 'group' : 'person') as 'person' | 'group';
		const ownerId = response.owner_id?.trim() || '';
		const keyName = response.key_name?.trim() || 'key-1';

		if (!ownerId || !keyName) {
			return;
		}

		const nextSummary: CourseApiKeySummary = {
			keyId: response.key_id?.trim() || '',
			ownerType,
			ownerId,
			keyName,
			slotIndex:
				typeof response.slot_index === 'number' &&
				Number.isInteger(response.slot_index) &&
				response.slot_index > 0
					? response.slot_index
					: parseSlotIndexFromKeyName(response.key_name),
			created: response.created?.trim() || '',
			courseId:
				typeof response.course_id === 'number' ? response.course_id : selectedCourse?.id || 0,
			hasHash: true,
			isActive: true
		};

		courseApiKeys = [
			nextSummary,
			...courseApiKeys.filter(
				(entry) =>
					!(
						entry.ownerType === nextSummary.ownerType &&
						normalizeIdentifier(entry.ownerId) === normalizeIdentifier(nextSummary.ownerId) &&
						((entry.slotIndex > 0 && entry.slotIndex === nextSummary.slotIndex) ||
							normalizeIdentifier(entry.keyName) === normalizeIdentifier(nextSummary.keyName))
					)
			)
		];
	}

	async function loadCourseApiHistory(courseId: number) {
		courseApiHistoryLoading = true;
		courseApiHistoryError = null;
		loadedCourseApiHistoryForId = courseId;

		try {
			courseApiHistory = await fetchCourseApiHistory(courseId);
		} catch (err) {
			courseApiHistoryError = err instanceof Error ? err.message : 'Unable to load API history.';
			courseApiHistory = [];
		} finally {
			courseApiHistoryLoading = false;
		}
	}

	async function loadCourseApiKeys(courseId: number) {
		courseApiKeysLoading = true;
		courseApiKeysError = null;
		loadedCourseApiKeysForId = courseId;

		try {
			const rawKeys = await fetchCourseApiKeys(courseId);
			courseApiKeys = normalizeApiKeySummaries(rawKeys);
		} catch (err) {
			courseApiKeysError = err instanceof Error ? err.message : 'Unable to load API keys.';
			courseApiKeys = [];
		} finally {
			courseApiKeysLoading = false;
		}
	}

	async function removeMember(memberId: string) {
		if (!ensureCourseIsEditable()) {
			return;
		}
		if (!selectedCourse || !selectedDetail) {
			return;
		}

		try {
			await removeCourseMember(selectedCourse.id, memberId);
			await refreshAfterWrite();
		} catch {
			// API layer already shows user-facing feedback.
		}
	}

	function openAddEmailPopup() {
		if (!ensureCourseIsEditable()) {
			return;
		}

		newMemberEmail = '';
		addEmailError = null;
		showAddEmailPopup = true;
	}

	function closeAddEmailPopup() {
		showAddEmailPopup = false;
		newMemberEmail = '';
		addEmailError = null;
	}

	async function submitAddEmailPopup() {
		if (!ensureCourseIsEditable()) {
			return;
		}

		if (!selectedCourse || !selectedDetail) {
			return;
		}

		const email = newMemberEmail.trim();

		if (!email) {
			addEmailError = 'Email is required.';
			return;
		}

		const matchingAccount = allUsers.find(
			(user) => normalizeIdentifier(user.email) === normalizeIdentifier(email)
		);

		if (matchingAccount?.isAdmin) {
			addEmailError = 'Admins cannot be added to course lists.';
			return;
		}

		try {
			await addCourseMembers(selectedCourse.id, [{ email }]);
			await refreshAfterWrite();
			closeAddEmailPopup();
		} catch {
			addEmailError = 'Unable to add user.';
		}
	}

	async function importPeopleFromCanvasCsv(event: Event) {
		if (!ensureCourseIsEditable()) {
			return;
		}
		if (!selectedCourse || !selectedDetail) {
			return;
		}

		const target = event.currentTarget as HTMLInputElement | null;
		const file = target?.files?.[0];
		if (!file) {
			return;
		}

		const csvText = await file.text();
		const idMatches = csvText.match(/(?:KSUID|WLID)\d{9}/gi) || [];
		const parsedIds = [...new Set(idMatches.map((value) => value.trim()))];
		const nonAdminIds = parsedIds.filter((id) => {
			const matchingUser = allUsers.find(
				(user) => normalizeIdentifier(user.id) === normalizeIdentifier(id)
			);
			return !matchingUser?.isAdmin;
		});
		if (nonAdminIds.length !== parsedIds.length) {
			showErrorFeedback('Admin accounts were excluded from the imported course list.');
		}
		if (nonAdminIds.length === 0) {
			target.value = '';
			return;
		}

		try {
			await addCourseMembers(
				selectedCourse.id,
				nonAdminIds.map((id) => ({ id }))
			);
			await refreshAfterWrite();
		} catch {
			// API layer already shows user-facing feedback.
		}

		target.value = '';
	}

	function triggerCsvImportPicker() {
		importCsvInput?.click();
	}

	async function saveCourseEdits() {
		if (!ensureCourseIsEditable()) {
			return;
		}
		if (!selectedCourse) {
			return;
		}

		const courseName = editCourseForm.name.trim();
		if (!courseName) {
			showErrorFeedback('Course name is required.');
			return;
		}

		const normalizedInstructorId = editCourseForm.instructorId.trim();
		const currentInstructorId = selectedCourse.instructorId || '';

		try {
			await updateCourseMetadata(selectedCourse.id, {
				name: courseName,
				code: editCourseForm.code.trim() || selectedCourse.code,
				semester: editCourseForm.semester.trim() || selectedCourse.semester,
				color: editCourseForm.color.trim() || selectedCourse.color,
				instructorId: normalizedInstructorId || currentInstructorId,
				taIds: editCourseForm.taIds.filter(
					(id) => id !== (normalizedInstructorId || currentInstructorId)
				)
			});
			await refreshAfterWrite();
		} catch {
			// API layer already shows user-facing feedback.
		}
	}

	async function createGroup() {
		if (!ensureCourseIsEditable()) {
			return;
		}
		if (!selectedCourse) {
			return;
		}

		const trimmedName = newGroupName.trim();
		if (!trimmedName) {
			return;
		}

		try {
			await createCourseGroupRequest(selectedCourse.id, trimmedName);
			await refreshAfterWrite();
			newGroupName = '';
		} catch {
			// API layer already shows user-facing feedback.
		}
	}

	async function addGroupMember(groupId: string) {
		if (!ensureCourseIsEditable()) {
			return;
		}
		if (!selectedCourse) {
			return;
		}

		const identifier = (pendingGroupMemberIdByGroupId[groupId] || '').trim();
		if (!identifier) {
			return;
		}

		try {
			await addCourseGroupMember(selectedCourse.id, groupId, identifier);
			await refreshAfterWrite();
			pendingGroupMemberIdByGroupId = {
				...pendingGroupMemberIdByGroupId,
				[groupId]: ''
			};
		} catch {
			// API layer already shows user-facing feedback.
		}
	}

	async function removeGroupMember(groupId: string, id: string) {
		if (!ensureCourseIsEditable()) {
			return;
		}
		if (!selectedCourse) {
			return;
		}

		try {
			await removeCourseGroupMember(selectedCourse.id, groupId, id);
			await refreshAfterWrite();
		} catch {
			// API layer already shows user-facing feedback.
		}
	}

	async function regenerateApiKey() {
		if (!ensureCourseIsEditable()) {
			return;
		}
		if (!selectedCourse) {
			return;
		}

		try {
			apiKeyActionError = null;
			const response = await regenerateCourseApiKey(selectedCourse.id, {
				ownerType: 'person',
				ownerId: currentUserId,
				keyName: 'key-1'
			});
			previewApiKey = response.api_key?.trim() || null;
			setSelectedCourseHasApiKey(true, {
				apiKeyOwnerType: response.owner_type ?? null,
				apiKeyOwnerId: response.owner_id ?? null,
				apiKeyGroupCreatedBy: response.group_created_by ?? null,
				apiKeyCreated: response.created ?? null
			});
			await loadCourseApiKeys(selectedCourse.id);
		} catch (err) {
			apiKeyActionError = err instanceof Error ? err.message : 'Unable to generate API key.';
		}
	}

	async function generateNamedPersonalKey() {
		if (!ensureCourseIsEditable()) {
			return;
		}
		if (!selectedCourse || !currentUserId) {
			return;
		}
		const keyName = newPersonalKeyName.trim() || `key-${personalOwnedKeys.length + 1}`;
		try {
			apiKeyActionError = null;
			const response = await regenerateCourseApiKey(selectedCourse.id, {
				ownerType: 'person',
				ownerId: currentUserId,
				keyName
			});
			previewApiKey = response.api_key?.trim() || null;
			newPersonalKeyName = '';
			await loadCourseApiKeys(selectedCourse.id);
		} catch (err) {
			apiKeyActionError = err instanceof Error ? err.message : 'Unable to generate personal key.';
		}
	}

	async function generateNamedGroupKey(groupId: string) {
		if (!ensureCourseIsEditable()) {
			return;
		}
		if (!selectedCourse) {
			return;
		}
		const keyName =
			(newGroupKeyNameByGroupId[groupId] || '').trim() ||
			`key-${groupOwnedKeys.filter((key) => key.ownerId === groupId).length + 1}`;
		try {
			apiKeyActionError = null;
			const response = await regenerateCourseApiKey(selectedCourse.id, {
				ownerType: 'group',
				groupId,
				keyName
			});
			previewApiKey = response.api_key?.trim() || null;
			newGroupKeyNameByGroupId = {
				...newGroupKeyNameByGroupId,
				[groupId]: ''
			};
			await loadCourseApiKeys(selectedCourse.id);
		} catch (err) {
			apiKeyActionError = err instanceof Error ? err.message : 'Unable to generate group key.';
		}
	}

	async function saveMemberKeyLimit(memberId: string) {
		if (!ensureCourseIsEditable()) {
			return;
		}
		if (!selectedCourse) {
			return;
		}
		const keyLimit = pendingMemberKeyLimitById[memberId];
		if (!Number.isInteger(keyLimit) || keyLimit < 0) {
			return;
		}
		if (keyLimit > courseStudentKeyLimit) {
			showErrorFeedback(
				`Member key limit cannot exceed the student key limit (${courseStudentKeyLimit}).`
			);
			pendingMemberKeyLimitById = {
				...pendingMemberKeyLimitById,
				[memberId]: courseStudentKeyLimit
			};
			return;
		}
		try {
			await updateCourseMemberKeyLimit(selectedCourse.id, memberId, keyLimit);
			await refreshAfterWrite();
		} catch {
			// API layer already shows user-facing feedback.
		}
	}

	async function saveInstructorHandoutLimit() {
		if (!ensureCourseIsEditable()) {
			return;
		}
		if (!selectedCourse) {
			return;
		}
		const instructorHandoutLimit = pendingInstructorHandoutLimit;
		if (!Number.isInteger(instructorHandoutLimit) || instructorHandoutLimit < 0) {
			return;
		}
		try {
			await updateCourseInstructorHandoutLimit(selectedCourse.id, instructorHandoutLimit);
			await refreshAfterWrite();
		} catch {
			// API layer already shows user-facing feedback.
		}
	}

	async function saveInstructorKeyLimit() {
		if (!ensureCourseIsEditable()) {
			return;
		}
		if (!selectedCourse) {
			return;
		}
		const instructorKeyLimit = pendingInstructorKeyLimit;
		if (!Number.isInteger(instructorKeyLimit) || instructorKeyLimit < 0) {
			return;
		}
		try {
			await updateCourseInstructorKeyLimit(selectedCourse.id, instructorKeyLimit);
			await refreshAfterWrite();
		} catch {
			// API layer already shows user-facing feedback.
		}
	}

	async function saveGroupKeyLimit(groupId: string) {
		if (!ensureCourseIsEditable()) {
			return;
		}
		if (!selectedCourse) {
			return;
		}
		const keyLimit = pendingGroupKeyLimitById[groupId];
		if (!Number.isInteger(keyLimit) || keyLimit < 0) {
			return;
		}
		const courseKeyLimit = Math.max(0, selectedCourse.instructorHandoutLimit ?? 2);
		if (keyLimit > courseKeyLimit) {
			showErrorFeedback(`Group key limit cannot exceed the course key limit (${courseKeyLimit}).`);
			pendingGroupKeyLimitById = {
				...pendingGroupKeyLimitById,
				[groupId]: courseKeyLimit
			};
			return;
		}
		try {
			await updateCourseGroupKeyLimit(selectedCourse.id, groupId, keyLimit);
			await refreshAfterWrite();
		} catch {
			// API layer already shows user-facing feedback.
		}
	}

	function clearPreviewApiKey() {
		previewApiKey = null;
	}

	async function deleteApiKey() {
		if (!ensureCourseIsEditable()) {
			return;
		}
		if (!selectedCourse) {
			return;
		}

		try {
			apiKeyActionError = null;
			await deleteCourseApiKey(selectedCourse.id);
			previewApiKey = null;
			setSelectedCourseHasApiKey(false, {
				apiKeyOwnerType: null,
				apiKeyOwnerId: null,
				apiKeyGroupCreatedBy: null,
				apiKeyCreated: null
			});
		} catch (err) {
			apiKeyActionError = err instanceof Error ? err.message : 'Unable to delete API key.';
		}
	}

	function getAvailableMembersForGroup(group: CourseGroup) {
		return selectableGroupMembers.filter(
			(member) => !group.memberIds.map(normalizeIdentifier).includes(getMemberIdentifier(member))
		);
	}

	function getCourseStatusActionLabel(): string {
		if (courseStatusActionPending) {
			return pendingCourseStatusValue ? 'Opening...' : 'Closing...';
		}
		return isSelectedCourseClosed ? 'Open Course' : 'Close Course';
	}

	async function toggleSelectedCourseActiveStatus() {
		if (!selectedCourse || !isCurrentUserAdmin || courseStatusActionPending) {
			return;
		}

		const targetCourseId = selectedCourse.id;
		const nextIsActive = !isSelectedCourseActive();
		const previousCourses = allCourses;
		const previousKeys = courseApiKeys;

		courseStatusActionPending = true;
		pendingCourseStatusValue = nextIsActive;

		allCourses = allCourses.map((course) =>
			course.id === targetCourseId
				? {
						...course,
						isActive: nextIsActive
					}
				: course
		);
		courseApiKeys = courseApiKeys.map((entry) =>
			entry.courseId === targetCourseId
				? {
						...entry,
						isActive: nextIsActive
					}
				: entry
		);

		try {
			await updateCourseActiveStatus(targetCourseId, nextIsActive);
			void refreshAfterWrite();
		} catch {
			allCourses = previousCourses;
			courseApiKeys = previousKeys;
			// API layer already shows user-facing feedback.
		} finally {
			courseStatusActionPending = false;
			pendingCourseStatusValue = null;
		}
	}
</script>

<ViewShell title="Courses">
	{#if isLoading}
		<div class="empty-state">
			<p>Loading course workspace...</p>
		</div>
	{:else if error}
		<div class="empty-state">
			<p><strong>Error:</strong> {error}</p>
			<button type="button" class="view-btn" onclick={loadWorkspace}>Try Again</button>
		</div>
	{:else if visibleCourses.length === 0}
		<div class="empty-state">
			<p>No courses were found in the database.</p>
		</div>
	{:else if !selectedCourse}
		<section class="section">
			<div class="section-header">
				<h2>Select a Course</h2>
			</div>
			<div class="section-content">
				<p class="section-text">
					Choose a course from Dashboard cards or from the Courses tab popout list.
				</p>
			</div>
		</section>
	{:else}
		<section class="section course-workspace" class:course-locked={isSelectedCourseClosed}>
			<div class="section-header course-header">
				<div>
					<h2>{selectedCourse.name}</h2>
					<p class="section-text">
						{[selectedCourse.code?.trim(), selectedCourse.semester, selectedCourse.instructor]
							.filter((value) => value && value.length > 0)
							.join(' · ')}
					</p>
				</div>
			</div>

			{#if showCourseTabBar}
				<div class="course-tab-bar">
					{#each availableTabs as tab}
						<button
							type="button"
							class="view-btn"
							class:course-tab-active={activeTab === tab}
							onclick={() => (activeTab = tab)}
						>
							{getTabLabel(tab)}
						</button>
					{/each}
				</div>
			{/if}

			{#if activeTab === 'home' && !canEditPeopleAndGroups}
				<div class="section-content home-panel-stack">
					{#if courseApiKeysLoading}
						<p>Loading key slots...</p>
					{:else if courseApiKeysError}
						<p><strong>Error:</strong> {courseApiKeysError}</p>
					{:else if personalKeySlots.length}
						{#each personalKeySlots as slot (getSlotStateId('person', studentPersonalKeyOwnerId, slot.slotIndex))}
							{@const slotStateId = getSlotStateId(
								'person',
								studentPersonalKeyOwnerId,
								slot.slotIndex
							)}
							<CourseKeySlotCard
								title={`Personal Key ${slot.slotIndex + 1}`}
								keyName={getSlotKeyName(slotStateId, slot.baseKeyName)}
								hasExistingKey={slot.hasExistingKey}
								maskedPreview={slot.hasExistingKey ? buildMaskedApiKeyPreview(30) : ''}
								placeholderText="No key exists for this slot yet."
								slotIdentity={slotStateId}
								readOnly={isSelectedCourseClosed}
								generateDisabled={isSelectedCourseClosed}
								onKeyNameChange={(nextName) => setSlotKeyName(slotStateId, nextName)}
								onGenerate={() =>
									generateKeyForSlot(
										'person',
										studentPersonalKeyOwnerId,
										slot.slotIndex,
										slot.baseKeyName
									)}
								removeDisabled={!slot.hasExistingKey || isSelectedCourseClosed}
								onRemove={() =>
									removeKeyForSlot(
										'person',
										studentPersonalKeyOwnerId,
										slot.slotIndex,
										slot.baseKeyName
									)}
								showToggleActive={false}
								isKeyActive={slot.isActive}
								toggleActiveDisabled={!slot.hasExistingKey || isSelectedCourseClosed}
								onToggleActive={() =>
									setSlotActiveState(
										'person',
										studentPersonalKeyOwnerId,
										slot.slotIndex,
										slot.baseKeyName,
										!slot.isActive
									)}
							/>
						{/each}
					{:else}
						<p class="section-text">No personal keys are configured for this course member.</p>
					{/if}
				</div>
			{:else if activeTab === 'home' && canEditPeopleAndGroups}
				<div class="section-content home-panel-stack">
					{#if courseApiKeysLoading}
						<p>Loading key slots...</p>
					{:else if courseApiKeysError}
						<p><strong>Error:</strong> {courseApiKeysError}</p>
					{:else if courseInstructorKeySlots.length}
						{#each courseInstructorKeySlots as slot (getSlotStateId('person', courseInstructorOwnerId, slot.slotIndex))}
							{@const slotStateId = getSlotStateId(
								'person',
								courseInstructorOwnerId,
								slot.slotIndex
							)}
							<CourseKeySlotCard
								title={`Instructor Key ${slot.slotIndex + 1}`}
								keyName={getSlotKeyName(slotStateId, slot.baseKeyName)}
								hasExistingKey={slot.hasExistingKey}
								maskedPreview={slot.hasExistingKey ? buildMaskedApiKeyPreview(30) : ''}
								placeholderText="No key exists for this slot yet."
								slotIdentity={slotStateId}
								readOnly={isSelectedCourseClosed}
								generateDisabled={isSelectedCourseClosed}
								onKeyNameChange={(nextName) => setSlotKeyName(slotStateId, nextName)}
								onGenerate={() =>
									generateKeyForSlot(
										'person',
										courseInstructorOwnerId,
										slot.slotIndex,
										slot.baseKeyName
									)}
								removeDisabled={!slot.hasExistingKey || isSelectedCourseClosed}
								onRemove={() =>
									removeKeyForSlot(
										'person',
										courseInstructorOwnerId,
										slot.slotIndex,
										slot.baseKeyName
									)}
								showToggleActive={true}
								isKeyActive={slot.isActive}
								toggleActiveDisabled={!slot.hasExistingKey || isSelectedCourseClosed}
								onToggleActive={() =>
									setSlotActiveState(
										'person',
										courseInstructorOwnerId,
										slot.slotIndex,
										slot.baseKeyName,
										!slot.isActive
									)}
							/>
						{/each}
					{:else}
						<p class="section-text">
							No instructor key slots are available for this user in this course.
						</p>
					{/if}
				</div>
			{:else if activeTab === 'students'}
				<div class="section-content home-panel-stack">
					{#if instructorVisibleStudents.length === 0}
						<p class="section-text">No students are enrolled in this course yet.</p>
					{:else}
						<div class="course-group-create-row">
							<select
								class="text-input"
								value={selectedInstructorStudentId}
								onchange={(event) => {
									const target = event.currentTarget as HTMLSelectElement;
									selectedInstructorStudentId = target.value;
								}}
							>
								{#each instructorVisibleStudents as member}
									<option value={getMemberIdentifier(member)}>
										{getMemberDisplayName(member)}
									</option>
								{/each}
							</select>
						</div>
						{#if courseApiKeysLoading}
							<p>Loading key slots...</p>
						{:else if courseApiKeysError}
							<p><strong>Error:</strong> {courseApiKeysError}</p>
						{:else}
							{#each instructorStudentKeySlots as slot (getSlotStateId('person', selectedInstructorStudentOwnerId, slot.slotIndex))}
								{@const slotStateId = getSlotStateId(
									'person',
									selectedInstructorStudentOwnerId,
									slot.slotIndex
								)}
								<CourseKeySlotCard
									title={`${selectedInstructorStudent ? getMemberDisplayName(selectedInstructorStudent) : 'Student'} Key ${slot.slotIndex + 1}`}
									keyName={getSlotKeyName(slotStateId, slot.baseKeyName)}
									hasExistingKey={slot.hasExistingKey}
									maskedPreview={slot.hasExistingKey ? buildMaskedApiKeyPreview(30) : ''}
									placeholderText="No key exists for this slot yet."
									slotIdentity={slotStateId}
									readOnly={isSelectedCourseClosed}
									generateDisabled={isSelectedCourseClosed}
									onKeyNameChange={(nextName) => setSlotKeyName(slotStateId, nextName)}
									onGenerate={() =>
										generateKeyForSlot(
											'person',
											selectedInstructorStudentOwnerId,
											slot.slotIndex,
											slot.baseKeyName
										)}
									removeDisabled={!slot.hasExistingKey || isSelectedCourseClosed}
									onRemove={() =>
										removeKeyForSlot(
											'person',
											selectedInstructorStudentOwnerId,
											slot.slotIndex,
											slot.baseKeyName
										)}
									showToggleActive={true}
									isKeyActive={slot.isActive}
									toggleActiveDisabled={!slot.hasExistingKey || isSelectedCourseClosed}
									onToggleActive={() =>
										setSlotActiveState(
											'person',
											selectedInstructorStudentOwnerId,
											slot.slotIndex,
											slot.baseKeyName,
											!slot.isActive
										)}
								/>
							{/each}
						{/if}
					{/if}
				</div>
			{:else if activeTab === 'groups'}
				<div class="section-content home-panel-stack">
					{#if selectedGroups.length === 0}
						<p class="section-text">No groups are available for this course yet.</p>
					{:else}
						<div class="course-group-create-row">
							<select
								class="text-input"
								value={selectedInstructorGroupId}
								onchange={(event) => {
									const target = event.currentTarget as HTMLSelectElement;
									selectedInstructorGroupId = target.value;
								}}
							>
								{#each selectedGroups as group}
									<option value={group.id}>{group.name}</option>
								{/each}
							</select>
						</div>
						{#if courseApiKeysLoading}
							<p>Loading key slots...</p>
						{:else if courseApiKeysError}
							<p><strong>Error:</strong> {courseApiKeysError}</p>
						{:else}
							{#each instructorGroupKeySlots as slot (getSlotStateId('group', selectedInstructorGroupId, slot.slotIndex))}
								{@const slotStateId = getSlotStateId(
									'group',
									selectedInstructorGroupId,
									slot.slotIndex
								)}
								<CourseKeySlotCard
									title={`${selectedInstructorGroup ? selectedInstructorGroup.name : 'Group'} Key ${slot.slotIndex + 1}`}
									keyName={getSlotKeyName(slotStateId, slot.baseKeyName)}
									hasExistingKey={slot.hasExistingKey}
									maskedPreview={slot.hasExistingKey ? buildMaskedApiKeyPreview(30) : ''}
									placeholderText="No key exists for this slot yet."
									slotIdentity={slotStateId}
									readOnly={isSelectedCourseClosed}
									generateDisabled={isSelectedCourseClosed}
									onKeyNameChange={(nextName) => setSlotKeyName(slotStateId, nextName)}
									onGenerate={() =>
										generateKeyForSlot(
											'group',
											selectedInstructorGroupId,
											slot.slotIndex,
											slot.baseKeyName
										)}
									removeDisabled={!slot.hasExistingKey || isSelectedCourseClosed}
									onRemove={() =>
										removeKeyForSlot(
											'group',
											selectedInstructorGroupId,
											slot.slotIndex,
											slot.baseKeyName
										)}
									showToggleActive={true}
									isKeyActive={slot.isActive}
									toggleActiveDisabled={!slot.hasExistingKey || isSelectedCourseClosed}
									onToggleActive={() =>
										setSlotActiveState(
											'group',
											selectedInstructorGroupId,
											slot.slotIndex,
											slot.baseKeyName,
											!slot.isActive
										)}
								/>
							{/each}
						{/if}
					{/if}
				</div>
			{:else if isGroupTab(activeTab) && !canEditPeopleAndGroups && activeStudentGroup}
				<div class="section-content home-panel-stack">
					{#if courseApiKeysLoading}
						<p>Loading key slots...</p>
					{:else if courseApiKeysError}
						<p><strong>Error:</strong> {courseApiKeysError}</p>
					{:else}
						{#each activeStudentGroupKeySlots as slot (getSlotStateId('group', activeStudentGroup.id, slot.slotIndex))}
							{@const slotStateId = getSlotStateId('group', activeStudentGroup.id, slot.slotIndex)}
							<CourseKeySlotCard
								title={`${activeStudentGroup.name} Key ${slot.slotIndex + 1}`}
								keyName={getSlotKeyName(slotStateId, slot.baseKeyName)}
								hasExistingKey={slot.hasExistingKey}
								maskedPreview={slot.hasExistingKey ? buildMaskedApiKeyPreview(30) : ''}
								placeholderText="No key exists for this slot yet."
								slotIdentity={slotStateId}
								readOnly={true}
								readOnlyMessage="Group keys are managed by your course instructor or teaching assistant."
								showToggleActive={false}
								isKeyActive={slot.isActive}
							/>
						{/each}
					{/if}
				</div>
			{:else if activeTab === 'edit-roster' && canEditPeopleAndGroups}
				<div class="section-content">
					<div class="course-people-actions">
						<input
							type="text"
							placeholder="Search users"
							bind:value={searchQuery}
							class="view-btn"
						/>
						<button type="button" class="view-btn" onclick={openAddEmailPopup}>Add Email</button>
						<button type="button" class="view-btn" onclick={triggerCsvImportPicker}
							>Import Canvas CSV</button
						>
						<input
							class="course-hidden-input"
							type="file"
							accept=".csv,text/csv"
							bind:this={importCsvInput}
							onchange={importPeopleFromCanvasCsv}
						/>
					</div>

					<div class="table-container">
						<table class="data-table course-people-table">
							<colgroup>
								<col />
								<col />
								<col />
								<col />
								<col class="course-table-actions-col" />
							</colgroup>
							<thead>
								<tr>
									<th
										style="cursor: pointer; user-select: none;"
										onclick={() => (sortByName = !sortByName)}>Name {sortByName ? '▲' : '▼'}</th
									>
									<th>Email</th>
									<th>Role</th>
									<th>Keys</th>
									<th class="table-actions-head">Actions</th>
								</tr>
							</thead>
							<tbody>
								{#if filteredMembers.length}
									{#each sortedMembers as member}
										{@const memberIdentifier = getMemberIdentifier(member)}
										<tr>
											<td
												>{member.isInstructor
													? selectedCourse.instructor || 'Unknown Instructor'
													: getMemberDisplayName(member)}</td
											>
											<td>{member.email}</td>
											<td>{getRosterRole(member)}</td>
											<td>
												{#if member.isInstructor}
													{#if isCurrentUserAdmin}
														<div class="course-group-add-row">
															{#if isSelectedCourseClosed}
																<div class="text-input course-locked-field">
																	{pendingInstructorKeyLimit}
																</div>
															{:else}
																<input
																	class="text-input"
																	type="number"
																	min="0"
																	value={pendingInstructorKeyLimit}
																	onchange={(event) => {
																		const target = event.currentTarget as HTMLInputElement;
																		pendingInstructorKeyLimit = Number.isFinite(
																			Number(target.value)
																		)
																			? Math.max(0, Number(target.value))
																			: 0;
																	}}
																/>
															{/if}
															{#if !isSelectedCourseClosed}
																<button
																	type="button"
																	class="list-go-btn"
																	onclick={saveInstructorKeyLimit}>Save</button
																>
															{/if}
														</div>
													{:else}
														<span class="section-text">{getRosterKeyLimit(member)}</span>
													{/if}
												{:else if member.isTeacherAssistant}
													<span class="section-text">{getRosterKeyLimit(member)}</span>
												{:else if canEditPeopleAndGroups}
													<div class="course-group-add-row">
														{#if isSelectedCourseClosed}
															<div class="text-input course-locked-field">
																{pendingMemberKeyLimitById[memberIdentifier] ?? member.keyLimit}
															</div>
														{:else}
															<input
																class="text-input"
																type="number"
																min="0"
																max={courseStudentKeyLimit}
																value={pendingMemberKeyLimitById[memberIdentifier] ??
																	member.keyLimit}
																onchange={(event) => {
																	const target = event.currentTarget as HTMLInputElement;
																	pendingMemberKeyLimitById = {
																		...pendingMemberKeyLimitById,
																		[memberIdentifier]: Number.isFinite(Number(target.value))
																			? Math.max(0, Number(target.value))
																			: 0
																	};
																}}
															/>
														{/if}
														{#if !isSelectedCourseClosed}
															<button
																type="button"
																class="list-go-btn"
																onclick={() => saveMemberKeyLimit(memberIdentifier)}>Save</button
															>
														{/if}
													</div>
												{:else}
													<span class="section-text">{member.keyLimit}</span>
												{/if}
											</td>
											<td class="table-actions-cell">
												{#if member.isInstructor}
													<span class="section-text">Root instructor</span>
												{:else if member.isTeacherAssistant}
													<span class="section-text">Teacher assistant</span>
												{:else if canEditPeopleAndGroups}
													{#if isSelectedCourseClosed}
														<span class="section-text">Read-only</span>
													{:else}
														<button
															type="button"
															class="list-go-btn"
															onclick={() => removeMember(memberIdentifier)}>Remove</button
														>
													{/if}
												{:else}
													<span class="section-text">Member</span>
												{/if}
											</td>
										</tr>
									{/each}
								{:else}
									<tr>
										<td colspan="5">No members in this course yet.</td>
									</tr>
								{/if}
							</tbody>
						</table>
					</div>
				</div>
			{:else if activeTab === 'edit-groups' && canEditPeopleAndGroups}
				<div class="section-content">
					<div class="course-people-actions">
						<div class="course-group-create-row">
							{#if isSelectedCourseClosed}
								<div class="text-input course-locked-field">{newGroupName || 'New group name'}</div>
							{:else}
								<input
									class="text-input"
									type="text"
									bind:value={newGroupName}
									placeholder="New group name"
								/>
							{/if}
							{#if !isSelectedCourseClosed}
								<button type="button" class="view-btn" onclick={createGroup}>Create Group</button>
							{/if}
						</div>
					</div>
					<div class="table-container">
						<table class="data-table group-table">
							<colgroup>
								<col class="group-col-name" />
								<col class="group-col-members" />
								<col class="group-col-add" />
								<col class="group-col-add" />
							</colgroup>
							<thead>
								<tr>
									<th>Group Name</th>
									<th>Members</th>
									<th>Keys</th>
									<th>Add User</th>
								</tr>
							</thead>
							<tbody>
								{#if selectedGroups.length}
									{#each selectedGroups as group}
										<tr>
											<td>{group.name}</td>
											<td>
												{#if group.memberIds.length}
													<ul class="course-inline-list">
														{#each group.memberIds as memberId}
															{@const member = resolveMemberByIdentifier(memberId)}
															<li>
																{member ? getMemberDisplayName(member) : 'Unknown user'}
																{#if !isSelectedCourseClosed}
																	<button
																		type="button"
																		class="list-go-btn"
																		onclick={() => removeGroupMember(group.id, memberId)}
																		>Remove</button
																	>
																{/if}
															</li>
														{/each}
													</ul>
												{:else}
													No members assigned.
												{/if}
											</td>
											<td>
												<div class="course-group-add-row">
													{#if isSelectedCourseClosed}
														<div class="text-input course-locked-field">
															{pendingGroupKeyLimitById[group.id] ?? group.keyLimit}
														</div>
													{:else}
														<input
															class="text-input"
															type="number"
															min="0"
															max={courseStudentKeyLimit}
															value={pendingGroupKeyLimitById[group.id] ?? group.keyLimit}
															onchange={(event) => {
																const target = event.currentTarget as HTMLInputElement;
																pendingGroupKeyLimitById = {
																	...pendingGroupKeyLimitById,
																	[group.id]: Number.isFinite(Number(target.value))
																		? Math.max(0, Number(target.value))
																		: 0
																};
															}}
														/>
													{/if}
													{#if !isSelectedCourseClosed}
														<button
															type="button"
															class="list-go-btn"
															onclick={() => saveGroupKeyLimit(group.id)}>Save</button
														>
													{/if}
												</div>
											</td>
											<td>
												<div class="course-group-add-row">
													{#if isSelectedCourseClosed}
														<div class="text-input course-locked-field">
															{pendingGroupMemberIdByGroupId[group.id] || 'Select course member'}
														</div>
													{:else}
														<select
															class="text-input"
															value={pendingGroupMemberIdByGroupId[group.id] || ''}
															onchange={(event) => {
																const target = event.currentTarget as HTMLSelectElement;
																pendingGroupMemberIdByGroupId = {
																	...pendingGroupMemberIdByGroupId,
																	[group.id]: target.value
																};
															}}
														>
															<option value="">Select course member</option>
															{#each getAvailableMembersForGroup(group) as member}
																<option value={getMemberIdentifier(member)}
																	>{getMemberDisplayName(member)}</option
																>
															{/each}
														</select>
													{/if}
													{#if !isSelectedCourseClosed}
														<button
															type="button"
															class="list-go-btn"
															onclick={() => addGroupMember(group.id)}>Add</button
														>
													{/if}
												</div>
											</td>
										</tr>
									{/each}
								{:else}
									<tr>
										<td colspan="4">No groups found for this course yet.</td>
									</tr>
								{/if}
							</tbody>
						</table>
					</div>
				</div>
			{:else if activeTab === 'course-settings' && canEditCourse}
				<div class="section-content">
					<CourseEditorCard
						title="Course Settings"
						submitLabel="Save Course"
						idPrefix="course-settings"
						users={accountUsers}
						form={editCourseForm}
						readOnly={isSelectedCourseClosed}
						useSemesterPicker={true}
						semesterYearMin={COURSE_EDITOR_SEMESTER_YEAR_MIN}
						semesterYearMax={COURSE_EDITOR_SEMESTER_YEAR_MAX}
						on:submit={saveCourseEdits}
					/>
					<div class="course-panel">
						<h3>Course Status</h3>
						<p class="section-text">Closing a course makes it read-only until reopened.</p>
						{#if isCurrentUserAdmin}
							<button
								type="button"
								class="view-btn"
								onclick={toggleSelectedCourseActiveStatus}
								disabled={courseStatusActionPending}
							>
								{getCourseStatusActionLabel()}
							</button>
						{/if}
					</div>
					{#if isCurrentUserAdmin}
						<div class="course-panel">
							<h3>Max Student Keys</h3>
							<p class="section-text">
								Caps the key allowance for each student and group in this course.
							</p>
							<div class="course-group-add-row">
								{#if isSelectedCourseClosed}
									<div class="text-input course-locked-field">{pendingInstructorHandoutLimit}</div>
								{:else}
									<input
										class="text-input"
										type="number"
										min="0"
										value={pendingInstructorHandoutLimit}
										onchange={(event) => {
											const target = event.currentTarget as HTMLInputElement;
											pendingInstructorHandoutLimit = Number.isFinite(Number(target.value))
												? Math.max(0, Number(target.value))
												: 0;
										}}
									/>
									<button type="button" class="list-go-btn" onclick={saveInstructorHandoutLimit}
										>Save</button
									>
								{/if}
							</div>
						</div>
					{/if}
				</div>
			{/if}
		</section>
	{/if}
	{#if showAddEmailPopup}
		<div class="popup-backdrop">
			<div class="popup-card">
				<h3>Add User by Email</h3>
				<p class="section-text">Enter a user email to add them to this course.</p>

				<input
					class="text-input"
					type="email"
					bind:value={newMemberEmail}
					placeholder="student@kent.edu"
				/>

				{#if addEmailError}
					<p class="popup-error">{addEmailError}</p>
				{/if}

				<div class="popup-actions">
					<button type="button" class="view-btn" onclick={closeAddEmailPopup}>Cancel</button>
					<button type="button" class="view-btn" onclick={submitAddEmailPopup}>Add User</button>
				</div>
			</div>
		</div>
	{/if}
</ViewShell>
