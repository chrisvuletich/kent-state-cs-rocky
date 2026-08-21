import {
	normalizeCourseDetails,
	normalizeCourseGroups,
	normalizeCourses,
	type ApiCourse,
	type ApiCourseGroup,
	type Course,
	type CourseDetail,
	type CourseGroup
} from '$lib/types/course';

const USER_SAFE_ACTION_FAILURE = 'Action failed. Please try again.';
const USER_SAFE_NETWORK_FAILURE = 'Unable to reach the server. Please try again.';

async function fetchJson<T>(url: string): Promise<T> {
	let response: Response;
	try {
		response = await fetch(url);
	} catch (err) {
		console.error('[content api] network request failed', { url, err });
		throw new Error(USER_SAFE_NETWORK_FAILURE);
	}

	if (!response.ok) {
		const body = await response.text();
		console.error('[content api] request failed', { url, status: response.status, raw: body });
		throw new Error(USER_SAFE_ACTION_FAILURE);
	}
	return (await response.json()) as T;
}
export async function fetchCourses(): Promise<Course[]> {
	const url = '/api/backend/courses';
	const rawCourses = await fetchJson<ApiCourse[]>(url);
	return normalizeCourses(rawCourses);
}

export async function fetchCourseDetails(): Promise<CourseDetail[]> {
	const coursesUrl = '/api/backend/courses';
	const rawCourses = await fetchJson<ApiCourse[]>(coursesUrl);
	const rawDetails = rawCourses.map((course) => ({
		id: course.id,
		members: course.members
	}));
	return normalizeCourseDetails(rawDetails);
}

export async function fetchCourseGroups(): Promise<CourseGroup[]> {
	const coursesUrl = '/api/backend/courses';
	const rawCourses = await fetchJson<ApiCourse[]>(coursesUrl);
	const rawGroups: ApiCourseGroup[] = rawCourses.flatMap((course) => {
		const groups = Array.isArray(course.groups) ? course.groups : [];
		return groups.map((group) => ({
			...group,
			courseId: typeof group.courseId === 'number' ? group.courseId : course.id
		}));
	});
	return normalizeCourseGroups(rawGroups);
}
