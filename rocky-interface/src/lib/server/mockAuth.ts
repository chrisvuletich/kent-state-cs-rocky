import { API_BASE_URL, APP_ENV, ENABLE_PREVIEW_AUTH } from '$lib/config/env';
import { internalProxyHeaders } from '$lib/server/backendSecurity';
import { normalizeUsers, type ApiUser, type User } from '$lib/types/user';

export const SESSION_COOKIE_NAME = 'rocky_session';

export const SESSION_COOKIE_OPTIONS = {
	path: '/',
	httpOnly: true,
	sameSite: 'lax' as const,
	secure: APP_ENV === 'production',
	maxAge: 60 * 60 * 8
};

async function loadMockUsers(): Promise<User[]> {
	if (!ENABLE_PREVIEW_AUTH) {
		return [];
	}

	const response = await fetch(`${API_BASE_URL}/auth/preview-users`, {
		method: 'GET',
		headers: {
			Accept: 'application/json'
		},
		cache: 'no-store'
	});

	if (!response.ok) {
		return [];
	}

	const parsed = (await response.json()) as ApiUser[];
	return normalizeUsers(parsed);
}

export async function getUserByEmail(email: string): Promise<User | null> {
	const normalizedEmail = email.trim().toLowerCase();
	if (!normalizedEmail) {
		return null;
	}

	const lookupUrl = new URL(`${API_BASE_URL}/auth/session-user`);
	lookupUrl.searchParams.set('email', normalizedEmail);

	const sessionResponse = await fetch(lookupUrl, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			...internalProxyHeaders()
		},
		cache: 'no-store'
	});

	if (sessionResponse.ok) {
		const rawUser = (await sessionResponse.json()) as ApiUser;
		return normalizeUsers([rawUser])[0] ?? null;
	}

	const users = await loadMockUsers();
	return users.find((user) => user.email.toLowerCase() === normalizedEmail) ?? null;
}
