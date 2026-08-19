import { canAccessFrame, isFrameName, type FrameName } from '$lib/types/frame';

export type AppDestination = {
	frame: FrameName;
	courseId?: number | null;
	conversationId?: string | null;
	documentId?: string | null;
};

export const appFrameQueryKeys: Record<FrameName, readonly string[]> = {
	dashboard: [],
	analytics: [
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
	],
	users: [],
	courses: ['course'],
	admin: [],
	audit: [],
	'api-keys': [],
	account: [],
	chat: ['conversation'],
	help: ['doc']
};

const frameSpecificQueryKeys = new Set(Object.values(appFrameQueryKeys).flat());

function trimmed(value: string | null | undefined, maximum = 256): string {
	return (value || '').trim().slice(0, maximum);
}

export function resolveAppFrame(
	params: URLSearchParams,
	rememberedFrame: FrameName,
	isAdmin: boolean
): FrameName {
	if (trimmed(params.get('doc'))) {
		return 'help';
	}

	const requestedFrame = params.get('frame');
	if (requestedFrame === null) {
		return canAccessFrame(rememberedFrame, isAdmin) ? rememberedFrame : 'dashboard';
	}

	const normalizedFrame = requestedFrame.trim().toLowerCase();
	if (isFrameName(normalizedFrame) && canAccessFrame(normalizedFrame, isAdmin)) {
		return normalizedFrame;
	}

	return 'dashboard';
}

export function isAccessibleRequestedFrame(value: string | null, isAdmin: boolean): boolean {
	if (value === null) return true;
	const normalizedFrame = value.trim().toLowerCase();
	return isFrameName(normalizedFrame) && canAccessFrame(normalizedFrame, isAdmin);
}

export function buildAppUrl(current: URL, destination: AppDestination): URL {
	const url = new URL(current);
	url.pathname = '/';
	url.hash = '';

	for (const key of frameSpecificQueryKeys) {
		url.searchParams.delete(key);
	}

	url.searchParams.set('frame', destination.frame);

	if (
		destination.frame === 'courses' &&
		Number.isSafeInteger(destination.courseId) &&
		(destination.courseId ?? 0) > 0
	) {
		url.searchParams.set('course', String(destination.courseId));
	}

	if (destination.frame === 'chat') {
		const conversationId = trimmed(destination.conversationId);
		if (conversationId) url.searchParams.set('conversation', conversationId);
	}

	if (destination.frame === 'help') {
		const documentId = trimmed(destination.documentId, 128);
		if (documentId) url.searchParams.set('doc', documentId);
	}

	url.searchParams.sort();
	return url;
}

export function appHref(current: URL, destination: AppDestination): string {
	const url = buildAppUrl(current, destination);
	return `${url.pathname}${url.search}`;
}

export function parseCourseId(value: string | null): number | null {
	const normalized = trimmed(value, 32);
	if (!/^[1-9]\d*$/.test(normalized)) return null;
	const courseId = Number(normalized);
	return Number.isSafeInteger(courseId) ? courseId : null;
}

export function parseConversationId(value: string | null): string | null {
	return trimmed(value) || null;
}
