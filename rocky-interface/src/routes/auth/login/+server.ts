import { error, json, type RequestHandler } from '@sveltejs/kit';
import { getUserByEmail, SESSION_COOKIE_NAME, SESSION_COOKIE_OPTIONS } from '$lib/server/mockAuth';
import { ENABLE_PREVIEW_AUTH } from '$lib/config/env';
import { createSessionToken } from '$lib/server/sessionAuth';

const FRAME_COOKIE_NAME = 'rocky_current_frame';
const FRAME_COOKIE_OPTIONS = {
	path: '/',
	maxAge: 60 * 60,
	sameSite: 'lax' as const
};

// Preview-only login endpoint. Microsoft OAuth issues sessions through /auth/microsoft/login.
export const POST: RequestHandler = async ({ request, cookies }) => {
	if (!ENABLE_PREVIEW_AUTH) {
		throw error(404, 'Not found.');
	}

	const body = (await request.json()) as Partial<{ email: string }>;
	const email = body.email?.trim();

	if (!email) {
		throw error(400, 'Email is required.');
	}

	const user = await getUserByEmail(email);
	if (!user) {
		throw error(401, 'Invalid login user.');
	}

	cookies.set(SESSION_COOKIE_NAME, createSessionToken(user.email), SESSION_COOKIE_OPTIONS);
	cookies.set(FRAME_COOKIE_NAME, 'dashboard', FRAME_COOKIE_OPTIONS);
	return json({ ok: true, user });
};
