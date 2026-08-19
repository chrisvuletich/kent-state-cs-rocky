const SAFE_CHAT_RESPONSE_HEADERS = [
	'retry-after',
	'x-request-id',
	'x-rocky-conversation-id',
	'x-rocky-message-stored',
	'x-rocky-request-id',
	'x-ratelimit-limit-requests',
	'x-ratelimit-remaining-requests',
	'x-ratelimit-reset-requests'
] as const;

export function forwardedChatResponseHeaders(upstream: Headers): Headers {
	const forwarded = new Headers();
	for (const name of SAFE_CHAT_RESPONSE_HEADERS) {
		const value = upstream.get(name);
		if (value) forwarded.set(name, value);
	}
	return forwarded;
}

export function streamingChatResponseHeaders(upstream: Headers): Headers {
	const forwarded = forwardedChatResponseHeaders(upstream);
	forwarded.set('Content-Type', 'text/event-stream; charset=utf-8');
	forwarded.set('Cache-Control', 'no-cache, no-transform');
	forwarded.set('X-Accel-Buffering', 'no');
	return forwarded;
}
