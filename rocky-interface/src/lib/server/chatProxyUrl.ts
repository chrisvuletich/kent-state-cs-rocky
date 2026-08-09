// Must match the Chat API generation route.
// No trailing slash because the URL is normalized before this suffix check.
const GENERATION_PATH = '/v1/responses';

export function deriveChatApiBaseUrl(chatApiUrl: string): string {
	chatApiUrl = chatApiUrl.trim();

	if (chatApiUrl.endsWith('/')) {
		chatApiUrl = chatApiUrl.slice(0, -1);
	}

	if (chatApiUrl.endsWith(GENERATION_PATH)) {
		chatApiUrl = chatApiUrl.slice(0, -GENERATION_PATH.length);
	}

	return chatApiUrl;
}
