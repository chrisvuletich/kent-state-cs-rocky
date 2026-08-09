import type {
	AnalyticsBreakdown,
	AnalyticsCurrent,
	AnalyticsDimension,
	AnalyticsHardware,
	AnalyticsMyUsage,
	AnalyticsRequestDetail,
	AnalyticsRequestFilters,
	AnalyticsRequests,
	AnalyticsReviewPatch,
	AnalyticsSummary,
	AnalyticsTimeseries,
	AnalyticsWindow
} from '$lib/types/analytics';

const ANALYTICS_FAILURE = 'Unable to load analytics right now.';

async function fetchAnalyticsJson<T>(path: string, init?: RequestInit): Promise<T> {
	let response: Response;
	try {
		response = await fetch(`/api/backend${path}`, { cache: 'no-store', ...init });
	} catch (error) {
		console.error('[analytics api] network request failed', { path, error });
		throw new Error(ANALYTICS_FAILURE);
	}

	if (!response.ok) {
		const raw = await response.text();
		console.error('[analytics api] request failed', { path, status: response.status, raw });
		if (response.status === 400 || response.status === 409) {
			let validationMessage = '';
			try {
				const payload = JSON.parse(raw) as { error?: unknown };
				if (typeof payload.error === 'string' && payload.error.trim()) {
					validationMessage = payload.error.trim();
				}
			} catch {
				validationMessage = '';
			}
			if (validationMessage) throw new Error(validationMessage);
		}
		throw new Error(ANALYTICS_FAILURE);
	}
	return (await response.json()) as T;
}

function query(values: Record<string, string | number | boolean | null | undefined>): string {
	const params = new URLSearchParams();
	for (const [key, value] of Object.entries(values)) {
		if (value !== null && value !== undefined && value !== '') {
			params.set(key, String(value));
		}
	}
	return params.toString();
}

function filterQuery(
	filters: AnalyticsRequestFilters
): Record<string, string | boolean | undefined> {
	return {
		user_id: filters.user,
		course_id: filters.course,
		key_id: filters.key,
		model: filters.model,
		operation: filters.operation,
		outcome: filters.outcome,
		source: filters.source,
		flagged: filters.flagged,
		review_status: filters.reviewStatus
	};
}

export function fetchAnalyticsCurrent(): Promise<AnalyticsCurrent> {
	return fetchAnalyticsJson('/analytics/current');
}

export function fetchMyUsage(): Promise<AnalyticsMyUsage> {
	return fetchAnalyticsJson('/analytics/my-usage');
}

export function fetchAnalyticsSummary(
	window: AnalyticsWindow,
	filters: AnalyticsRequestFilters = {}
): Promise<AnalyticsSummary> {
	return fetchAnalyticsJson(`/analytics/summary?${query({ window, ...filterQuery(filters) })}`);
}

export function fetchAnalyticsTimeseries(
	window: AnalyticsWindow,
	filters: AnalyticsRequestFilters = {}
): Promise<AnalyticsTimeseries> {
	return fetchAnalyticsJson(`/analytics/timeseries?${query({ window, ...filterQuery(filters) })}`);
}

export function fetchAnalyticsHardware(
	window: AnalyticsWindow,
	filters: AnalyticsRequestFilters = {}
): Promise<AnalyticsHardware> {
	return fetchAnalyticsJson(`/analytics/hardware?${query({ window, ...filterQuery(filters) })}`);
}

export function fetchAnalyticsBreakdown(
	window: AnalyticsWindow,
	dimension: AnalyticsDimension,
	filters: AnalyticsRequestFilters = {}
): Promise<AnalyticsBreakdown> {
	return fetchAnalyticsJson(
		`/analytics/breakdown?${query({ window, dimension, limit: 50, ...filterQuery(filters) })}`
	);
}

export function fetchAnalyticsRequests(
	window: AnalyticsWindow,
	filters: AnalyticsRequestFilters = {}
): Promise<AnalyticsRequests> {
	return fetchAnalyticsJson(
		`/analytics/requests?${query({
			window,
			limit: 100,
			...filterQuery(filters)
		})}`
	);
}

export function analyticsExportUrl(
	window: AnalyticsWindow,
	format: 'json' | 'csv',
	filters: AnalyticsRequestFilters = {}
): string {
	return `/api/backend/analytics/export?${query({
		window,
		format,
		...filterQuery(filters)
	})}`;
}

export function fetchAnalyticsRequest(requestId: string): Promise<AnalyticsRequestDetail> {
	return fetchAnalyticsJson(`/analytics/requests/${encodeURIComponent(requestId)}`);
}

export function updateAnalyticsReview(
	requestId: string,
	review: AnalyticsReviewPatch
): Promise<AnalyticsRequestDetail> {
	return fetchAnalyticsJson(`/analytics/requests/${encodeURIComponent(requestId)}/review`, {
		method: 'PATCH',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(review)
	});
}
