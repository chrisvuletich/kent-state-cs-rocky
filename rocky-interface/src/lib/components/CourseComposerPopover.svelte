<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { createCourse } from '$lib/api/courses';
	import { currentFrame } from '$lib/stores/frameStore';
	import { selectedCourseId } from '$lib/stores/courseStore';
	import { fetchUsersForViews } from '$lib/api/users';
	import CourseEditorCard from '$lib/components/cards/CourseEditorCard.svelte';
	import { showErrorFeedback } from '$lib/stores/feedbackStore';
	import {
		COURSE_EDITOR_SEMESTER_YEAR_MAX,
		COURSE_EDITOR_SEMESTER_YEAR_MIN,
		randomCourseEditorColor
	} from '$lib/config/courseEditor';
	import { closeCourseComposer, courseComposerState } from '$lib/stores/courseComposerStore';
	import type { User } from '$lib/types/user';

	let users: User[] = [];
	let form = {
		name: '',
		code: '',
		semester: '',
		color: randomCourseEditorColor(),
		instructorId: '',
		taIds: [] as string[]
	};

	onMount(async () => {
		try {
			if ($page.data.currentUser?.isAdmin) {
				users = await fetchUsersForViews();
			}
		} catch (error) {
			console.error('Unable to load users for course composer', error);
		}
	});

	$: accountUsers = users.filter(
		(user) => !user.isAdmin && user.email && user.email.trim() && user.email !== 'N/A'
	);
	$: if ($courseComposerState.isOpen) {
		form = {
			name: '',
			code: '',
			semester: '',
			color: randomCourseEditorColor(),
			instructorId: '',
			taIds: []
		};
	}

	async function createCourseFromForm() {
		const courseName = form.name.trim();
		if (!courseName) {
			showErrorFeedback('Course name is required.');
			return;
		}

		const normalizedInstructorId = form.instructorId.trim();
		const normalizedTaIds = form.taIds.filter((id) => id !== normalizedInstructorId);
		const created = await createCourse({
			name: courseName,
			code: form.code.trim(),
			semester: form.semester.trim() || '',
			color: form.color.trim() || randomCourseEditorColor(),
			instructorId: normalizedInstructorId,
			taIds: normalizedTaIds,
			instructorName: accountUsers.find((user) => user.id === normalizedInstructorId)?.displayName
		});

		selectedCourseId.set(created.id);
		currentFrame.set('courses');
		closeCourseComposer();
	}
</script>

{#if $courseComposerState.isOpen}
	<div
		class="course-composer-layer"
		role="presentation"
		tabindex="-1"
		onclick={closeCourseComposer}
		onkeydown={(event) => {
			if (event.key === 'Escape' || event.key === 'Enter' || event.key === ' ') {
				closeCourseComposer();
			}
		}}
	>
		<div
			class="course-composer-popout"
			role="dialog"
			aria-modal="true"
			aria-label="Create Course"
			tabindex="0"
			onclick={(event) => event.stopPropagation()}
			onkeydown={(event) => event.stopPropagation()}
		>
			<div class="course-composer-title-row">
				<h3>Create Course</h3>
				<button type="button" class="list-go-btn" onclick={closeCourseComposer}>Close</button>
			</div>
			<CourseEditorCard
				title="Course Details"
				submitLabel="Create Course"
				idPrefix="global-create-course"
				users={accountUsers}
				{form}
				useSemesterPicker={true}
				semesterYearMin={COURSE_EDITOR_SEMESTER_YEAR_MIN}
				semesterYearMax={COURSE_EDITOR_SEMESTER_YEAR_MAX}
				on:submit={createCourseFromForm}
			/>
		</div>
	</div>
{/if}
