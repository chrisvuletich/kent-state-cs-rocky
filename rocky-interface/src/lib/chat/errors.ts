export type ChatFailureKind =
	| 'authentication'
	| 'busy'
	| 'logging'
	| 'network'
	| 'request'
	| 'service'
	| 'stopped'
	| 'timeout';

export type ChatFailure = {
	kind: ChatFailureKind;
	message: string;
	markUnavailable: boolean;
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

export function chatHttpFailure(status: number, payload: unknown): ChatFailure {
	const { code, message } = errorDetails(payload);

	if (status === 401 || status === 403 || code === 'invalid_api_key') {
		return {
			kind: 'authentication',
			message: 'Your chat session could not be authenticated. Refresh the page and sign in again.',
			markUnavailable: false
		};
	}
	if (status === 504 || code === 'model_timeout') {
		return {
			kind: 'timeout',
			message: 'Rocky took too long to respond. Try again with a shorter question.',
			markUnavailable: false
		};
	}
	if (code === 'model_busy') {
		return {
			kind: 'busy',
			message: 'Rocky is busy right now. Wait a moment and try again.',
			markUnavailable: true
		};
	}
	if (code === 'request_logging_unavailable') {
		return {
			kind: 'logging',
			message: 'Rocky cannot save the required request log right now. Please try again later.',
			markUnavailable: true
		};
	}
	if (status === 502 || status === 503 || status >= 500) {
		return {
			kind: 'service',
			message: 'The model service is temporarily unavailable. Please try again shortly.',
			markUnavailable: true
		};
	}

	return {
		kind: 'request',
		message: message || 'Rocky AI did not return a reply.',
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
