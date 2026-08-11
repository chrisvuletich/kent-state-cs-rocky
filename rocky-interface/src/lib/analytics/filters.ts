import {
	analyticsDimensions,
	analyticsReviewStatuses,
	analyticsWindows,
	type AnalyticsDimension,
	type AnalyticsOutcome,
	type AnalyticsReviewStatus,
	type AnalyticsWindow
} from '$lib/types/analytics';

export const analyticsOperations = ['models.list', 'responses.create', 'unknown'] as const;
export const analyticsOutcomes = [
	'completed',
	'rejected',
	'failed',
	'timed_out',
	'active'
] as const;
export type AnalyticsOperation = (typeof analyticsOperations)[number];
export type AnalyticsReviewFilter = 'all' | 'flagged' | AnalyticsReviewStatus;

export type AnalyticsFilterState = {
	window: AnalyticsWindow;
	dimension: AnalyticsDimension;
	user: string;
	course: string;
	key: string;
	model: string;
	operation: AnalyticsOperation | '';
	outcome: AnalyticsOutcome | 'active' | '';
	source: string;
	errorType: string;
	review: AnalyticsReviewFilter;
	requestId: string;
};

export const defaultAnalyticsFilters: AnalyticsFilterState = {
	window: '24h',
	dimension: 'user',
	user: '',
	course: '',
	key: '',
	model: '',
	operation: '',
	outcome: '',
	source: '',
	errorType: '',
	review: 'all',
	requestId: ''
};

const managedKeys = [
	'range',
	'dimension',
	'user',
	'course',
	'key',
	'model',
	'operation',
	'outcome',
	'source',
	'error_type',
	'review',
	'request',
	'analytics_window',
	'analytics_dimension',
	'analytics_request',
	'analytics_outcome',
	'analytics_review'
] as const;

function bounded(value: string | null, maximum = 256): string {
	return (value || '').trim().slice(0, maximum);
}

function recognized<T extends string>(value: string, allowed: readonly T[], fallback: T): T {
	return allowed.includes(value as T) ? (value as T) : fallback;
}

export function parseAnalyticsFilters(params: URLSearchParams): AnalyticsFilterState {
	const windowValue = bounded(params.get('range') || params.get('analytics_window'), 16);
	const dimensionValue = bounded(params.get('dimension') || params.get('analytics_dimension'), 32);
	const operationValue = bounded(params.get('operation'), 64);
	const outcomeValue = bounded(params.get('outcome') || params.get('analytics_outcome'), 32);
	const reviewValue = bounded(params.get('review') || params.get('analytics_review'), 32);
	return {
		window: recognized(windowValue, analyticsWindows, defaultAnalyticsFilters.window),
		dimension: recognized(dimensionValue, analyticsDimensions, defaultAnalyticsFilters.dimension),
		user: bounded(params.get('user')),
		course: bounded(params.get('course')),
		key: bounded(params.get('key')),
		model: bounded(params.get('model')),
		operation: recognized(operationValue, ['', ...analyticsOperations], ''),
		outcome: recognized(outcomeValue, ['', ...analyticsOutcomes], ''),
		source: bounded(params.get('source'), 128),
		errorType: bounded(params.get('error_type'), 128),
		review: recognized(reviewValue, ['all', 'flagged', ...analyticsReviewStatuses], 'all'),
		requestId: bounded(params.get('request') || params.get('analytics_request'))
	};
}

export function analyticsUrl(current: URL, state: AnalyticsFilterState): URL {
	const url = new URL(current);
	for (const key of managedKeys) url.searchParams.delete(key);
	url.searchParams.set('frame', 'analytics');
	if (state.window !== defaultAnalyticsFilters.window) url.searchParams.set('range', state.window);
	if (state.dimension !== defaultAnalyticsFilters.dimension)
		url.searchParams.set('dimension', state.dimension);
	for (const [key, value] of [
		['user', state.user],
		['course', state.course],
		['key', state.key],
		['model', state.model],
		['operation', state.operation],
		['outcome', state.outcome],
		['source', state.source],
		['error_type', state.errorType]
	] as const) {
		if (value) url.searchParams.set(key, value);
	}
	if (state.review !== 'all') url.searchParams.set('review', state.review);
	if (state.requestId) url.searchParams.set('request', state.requestId);
	url.searchParams.sort();
	return url;
}

export function analyticsFilterCount(state: AnalyticsFilterState): number {
	return [
		state.user,
		state.course,
		state.key,
		state.model,
		state.operation,
		state.outcome,
		state.source,
		state.errorType,
		state.review === 'all' ? '' : state.review
	].filter(Boolean).length;
}

export function analyticsFilterSignature(state: AnalyticsFilterState): string {
	return JSON.stringify(state);
}
