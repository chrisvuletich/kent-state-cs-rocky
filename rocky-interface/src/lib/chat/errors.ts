export type ChatFailureKind =
	| 'authentication'
	| 'busy'
	| 'logging'
	| 'network'
	| 'rate_limit'
	| 'request'
	| 'service'
	| 'stopped'
	| 'timeout';

export type ChatFailure = {
	kind: ChatFailureKind;
	message: string;
	markUnavailable: boolean;
	retryAfterSeconds?: number;
};

export type ChatFailureContext = {
	retryAfter?: string | null;
	requestId?: string | null;
};

function errorDetails(payload: unknown): { code: string; message: string } {
	if (!payload || typeof payload !== 'object' || !('error' in payload)) {
		return { code: '', message: '' };
	}

	const error = (payload as { error?: unknown }).error;
	if (typeof error === 'string') {
		return { code: '', message: error.trim() };
	}
	if (!error || typeof error !== 'object') {
		return { code: '', message: '' };
	}

	const details = error as { code?: unknown; message?: unknown };
	return {
		code: typeof details.code === 'string' ? details.code.trim() : '',
		message: typeof details.message === 'string' ? details.message.trim() : ''
	};
}

function retryAfterSeconds(value: string | null | undefined): number | undefined {
	if (!value || !/^\d+$/.test(value.trim())) return undefined;
	const seconds = Number(value);
	return Number.isSafeInteger(seconds) && seconds > 0 && seconds <= 3600 ? seconds : undefined;
}

function withRequestId(message: string, requestId: string | null | undefined): string {
	const normalized = requestId?.trim().slice(0, 128);
	return normalized ? `${message} Request ID: ${normalized}` : message;
}

export function chatHttpFailure(
	status: number,
	payload: unknown,
	context: ChatFailureContext = {}
): ChatFailure {
	const { code, message } = errorDetails(payload);
	const requestId = context.requestId;

	if (status === 401 || status === 403 || code === 'invalid_api_key') {
		return {
			kind: 'authentication',
			message: withRequestId(
				'Your chat session could not be authenticated. Refresh the page and sign in again.',
				requestId
			),
			markUnavailable: false
		};
	}
	if (status === 429 || code === 'rate_limit_exceeded') {
		const retrySeconds = retryAfterSeconds(context.retryAfter);
		return {
			kind: 'rate_limit',
			message: withRequestId(
				retrySeconds
					? `Rocky's request limit was reached. Try again in ${retrySeconds} seconds.`
					: message || "Rocky's request limit was reached. Please retry shortly.",
				requestId
			),
			markUnavailable: false,
			...(retrySeconds ? { retryAfterSeconds: retrySeconds } : {})
		};
	}
	if (status === 504 || code === 'model_timeout') {
		return {
			kind: 'timeout',
			message: withRequestId(
				'Rocky took too long to respond. Try again with a shorter question.',
				requestId
			),
			markUnavailable: false
		};
	}
	if (code === 'model_busy') {
		return {
			kind: 'busy',
			message: withRequestId('Rocky is busy right now. Wait a moment and try again.', requestId),
			markUnavailable: true
		};
	}
	if (code === 'request_logging_unavailable') {
		return {
			kind: 'logging',
			message: withRequestId(
				'Rocky cannot save the required request log right now. Please try again later.',
				requestId
			),
			markUnavailable: true
		};
	}
	if (status === 502 || status === 503 || status >= 500) {
		return {
			kind: 'service',
			message: withRequestId(
				'The model service is temporarily unavailable. Please try again shortly.',
				requestId
			),
			markUnavailable: true
		};
	}

	return {
		kind: 'request',
		message: withRequestId(message || 'Rocky AI did not return a reply.', requestId),
		markUnavailable: false
	};
}

export function isAbortError(error: unknown): boolean {
	return Boolean(
		error && typeof error === 'object' && 'name' in error && error.name === 'AbortError'
	);
}

export function stoppedChatFailure(): ChatFailure {
	return {
		kind: 'stopped',
		message:
			'Stopped waiting for the response. Rocky may still finish it, so recent chats were refreshed before another request is sent.',
		markUnavailable: false
	};
}

export function chatExceptionFailure(error: unknown): ChatFailure {
	if (isAbortError(error)) return stoppedChatFailure();

	return {
		kind: 'network',
		message: 'Network connection lost. Check your connection and try again.',
		markUnavailable: true
	};
}
