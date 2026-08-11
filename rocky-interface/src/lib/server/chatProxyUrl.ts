const GENERATION_PATH = '/v1/responses';

export type ChatApiUrls = {
	generationUrl: string;
	baseUrl: string;
};

function invalidChatApiUrl(): never {
	throw new Error(
		'Invalid ROCKY_CHAT_API_URL. Expected an absolute http(s) service URL or /v1/responses endpoint without credentials, a query string, or a fragment.'
	);
}

export function resolveChatApiUrls(configuredUrl: string): ChatApiUrls {
	configuredUrl = configuredUrl.trim();
	let parsed: URL;
	try {
		parsed = new URL(configuredUrl);
	} catch {
		return invalidChatApiUrl();
	}

	if (
		!['http:', 'https:'].includes(parsed.protocol) ||
		!parsed.hostname ||
		parsed.username ||
		parsed.password ||
		parsed.search ||
		parsed.hash
	) {
		return invalidChatApiUrl();
	}

	let basePath = parsed.pathname.replace(/\/+$/, '');
	if (basePath.endsWith(GENERATION_PATH)) {
		basePath = basePath.slice(0, -GENERATION_PATH.length);
	}

	const baseUrl = `${parsed.origin}${basePath}`;
	return {
		generationUrl: `${baseUrl}${GENERATION_PATH}`,
		baseUrl
	};
}

export function deriveChatApiBaseUrl(configuredUrl: string): string {
	return resolveChatApiUrls(configuredUrl).baseUrl;
}
