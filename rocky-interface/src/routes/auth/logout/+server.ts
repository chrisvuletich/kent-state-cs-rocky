import { json, type RequestHandler } from '@sveltejs/kit';
import { SESSION_COOKIE_NAME, SESSION_COOKIE_OPTIONS } from '$lib/server/mockAuth';

export const POST: RequestHandler = async ({ cookies }) => {
	cookies.delete(SESSION_COOKIE_NAME, SESSION_COOKIE_OPTIONS);
	cookies.delete('rocky_current_frame', { path: '/' });
	return json({ ok: true });
};
