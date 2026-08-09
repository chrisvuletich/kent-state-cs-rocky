import { toActivityRow, toKpiMetric, type ActivityRow, type KpiMetric } from '$lib/types/analytics';
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
import { normalizeFaqItems, type ApiFaqItem, type FaqItem } from '$lib/types/help';

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

export async function fetchAnalyticsKpis(): Promise<KpiMetric[]> {
	const url = '/api/backend/analytics/kpis';
	const rawKpis = await fetchJson<Array<Partial<KpiMetric>>>(url);
	return rawKpis.map(toKpiMetric);
}

export async function fetchAnalyticsActivity(): Promise<ActivityRow[]> {
	const url = '/api/backend/analytics/activity';
	const rawRows = await fetchJson<Array<Partial<ActivityRow>>>(url);
	return rawRows.map(toActivityRow);
}

export async function fetchFaqItems(): Promise<FaqItem[]> {
	const url = '/api/backend/help/faq';
	const rawItems = await fetchJson<ApiFaqItem[]>(url);
	return normalizeFaqItems(rawItems);
}

/**
 * Derives assigned course IDs for a user based on courses where they appear as a member.
 * Courses are the authoritative source of truth for user-course relationships.
 * @param userId - The user id used for relational matching in course members
 * @param courseDetails - The list of course details with member information to search through
 * @returns Array of course IDs where the user is a member
 */
export function getUserAssignedCourseIds(userId: string, courseDetails: CourseDetail[]): number[] {
	const normalizedId = userId.trim();
	const normalizedEmail = userId.trim().toLowerCase();
	return courseDetails
		.filter((course) => {
			return course.members.some(
				(member) => member.id === normalizedId || member.email.toLowerCase() === normalizedEmail
			);
		})
		.map((course) => course.id)
		.filter((id): id is number => typeof id === 'number');
}
