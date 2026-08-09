import { SESSION_COOKIE_NAME, SESSION_COOKIE_OPTIONS } from '$lib/server/mockAuth';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ cookies }) => {
	cookies.delete(SESSION_COOKIE_NAME, SESSION_COOKIE_OPTIONS);
	cookies.delete('rocky_current_frame', { path: '/' });
	return {};
};
