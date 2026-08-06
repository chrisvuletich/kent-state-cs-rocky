import { env } from '$env/dynamic/private';
import { error } from '@sveltejs/kit';
import { deriveHiddenApiKey } from '$lib/server/hiddenApiKey';
import { deriveChatApiBaseUrl } from './chatProxyUrl';

export const CHAT_API_URL = (env.ROCKY_CHAT_API_URL ?? 'http://127.0.0.1:5003/v1/responses').trim();
export const CHAT_API_BASE_URL = deriveChatApiBaseUrl(CHAT_API_URL);
const HIDDEN_API_KEY_SECRET = (env.ROCKY_HIDDEN_API_KEY_SECRET ?? env.ROCKY_CHAT_API_KEY ?? '').trim();

export function requireChatUser(locals: App.Locals): NonNullable<App.Locals['currentUser']> {
	const user = locals.currentUser;
	if (!user) {
		throw error(401, 'Not authenticated.');
	}
	if (!user.isActive) {
		throw error(403, 'Your account is deactivated.');
	}
	return user;
}

export function chatIdentityHeaders(user: NonNullable<App.Locals['currentUser']>): Record<string, string> {
	return {
		'X-Rocky-User-Id': user.id,
		'X-Rocky-User-Email': user.email,
		'X-Rocky-User-Name': user.displayName,
		'X-Rocky-User-Is-Admin': String(user.isAdmin)
	};
}

export function chatRequestHeaders(user: NonNullable<App.Locals['currentUser']>): Record<string, string> {
	return {
		Authorization: `Bearer ${hiddenApiKeyForUser(user)}`,
		...chatIdentityHeaders(user)
	};
}

export function hiddenApiKeyForUser(user: NonNullable<App.Locals['currentUser']>): string {
	const ownerId = (user.apiKeyOwnerId || user.id).trim().toLowerCase();
	if (!ownerId) {
		throw error(500, 'Unable to resolve chat API key owner.');
	}
	if (!HIDDEN_API_KEY_SECRET) {
		throw error(500, 'Hidden chat API key secret is not configured.');
	}

	return deriveHiddenApiKey(ownerId, HIDDEN_API_KEY_SECRET);
}

export function chatApiPayload(extra: Record<string, unknown> = {}): Record<string, unknown> {
	return { ...extra };
}
