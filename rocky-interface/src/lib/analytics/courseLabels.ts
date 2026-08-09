import type { AnalyticsBreakdownRow } from '$lib/types/analytics';
import type { Course } from '$lib/types/course';

export function analyticsCourseLabel(
	row: Pick<AnalyticsBreakdownRow, 'id' | 'label'>,
	courses: Course[]
): string {
	const identifier = row.id.trim();
	const telemetryLabel = row.label.trim();
	if (telemetryLabel && telemetryLabel.toLowerCase() !== identifier.toLowerCase())
		return telemetryLabel;

	const matchedCourse = courses.find((course) => String(course.id) === identifier);
	if (matchedCourse?.code) return matchedCourse.code;
	if (matchedCourse?.name) return matchedCourse.name;
	return identifier ? `Course ${identifier}` : 'Unknown course';
}
