import { error, json, type RequestHandler } from '@sveltejs/kit';
import { API_BASE_URL, ENABLE_MICROSOFT_OAUTH } from '$lib/config/env';
import { SESSION_COOKIE_NAME, SESSION_COOKIE_OPTIONS } from '$lib/server/mockAuth';
import { internalProxyHeaders } from '$lib/server/backendSecurity';
import { verifyMicrosoftIdToken } from '$lib/server/microsoftAuth';
import { createSessionToken } from '$lib/server/sessionAuth';

const FRAME_COOKIE_NAME = 'rocky_current_frame';
const FRAME_COOKIE_OPTIONS = {
	path: '/',
	maxAge: 60 * 60,
	sameSite: 'lax' as const
};

type MicrosoftLoginRequest = {
	idToken?: string;
};

export const POST: RequestHandler = async ({ request, cookies }) => {
	if (!ENABLE_MICROSOFT_OAUTH) {
		throw error(404, 'Not found.');
	}

	let body: MicrosoftLoginRequest;
	try {
		body = (await request.json()) as MicrosoftLoginRequest;
	} catch {
		throw error(400, 'Request body must be valid JSON.');
	}
	if (typeof body.idToken !== 'string' || !body.idToken.trim()) {
		throw error(400, 'A Microsoft identity token is required.');
	}
	let identity;
	try {
		identity = await verifyMicrosoftIdToken(body.idToken);
	} catch (caught) {
		console.warn('[oauth] microsoft token verification failed', {
			errorType: caught instanceof Error ? caught.name : 'UnknownError'
		});
		throw error(
			401,
			caught instanceof Error ? caught.message : 'Microsoft identity token verification failed.'
		);
	}
	const backendResponse = await fetch(`${API_BASE_URL}/auth/microsoft/login`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...internalProxyHeaders()
		},
		cache: 'no-store',
		body: JSON.stringify(identity)
	});

	const responseText = await backendResponse.text();
	let payload: unknown = null;
	if (responseText.length > 0) {
		try {
			payload = JSON.parse(responseText);
		} catch {
			payload = { error: responseText };
		}
	}

	if (!backendResponse.ok) {
		const backendError =
			typeof payload === 'object' && payload !== null && 'error' in payload
				? String((payload as { error: unknown }).error)
				: 'Microsoft login failed.';
		throw error(backendResponse.status, backendError);
	}

	const userEmail =
		typeof payload === 'object' && payload !== null && 'user' in payload
			? String((payload as { user: { email?: string } }).user?.email ?? '')
			: '';

	if (!userEmail) {
		throw error(500, 'Microsoft login succeeded but no user email was returned.');
	}

	cookies.set(SESSION_COOKIE_NAME, createSessionToken(userEmail), SESSION_COOKIE_OPTIONS);
	cookies.set(FRAME_COOKIE_NAME, 'dashboard', FRAME_COOKIE_OPTIONS);
	return json(payload);
};
