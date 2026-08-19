import { json, type RequestHandler } from '@sveltejs/kit';
import { CHAT_API_BASE_URL, requireChatUser } from '$lib/server/chatProxy';
import { imageCapabilitiesFromReadiness } from '$lib/server/chatImageInput';

export const GET: RequestHandler = async ({ fetch, locals, request }) => {
	requireChatUser(locals);
	try {
		const response = await fetch(`${CHAT_API_BASE_URL}/ready`, {
			headers: { Accept: 'application/json' },
			signal: request.signal,
			cache: 'no-store'
		});
		const payload = await response.json().catch(() => null);
		if (!response.ok || payload?.ok !== true) {
			return json(
				{ imageInput: { enabled: false, limits: null } },
				{ status: 502, headers: { 'Cache-Control': 'no-store' } }
			);
		}
		const imageInput = imageCapabilitiesFromReadiness(payload);
		if (!imageInput.limits) {
			return json(
				{ imageInput: { enabled: false, limits: null } },
				{ status: 502, headers: { 'Cache-Control': 'no-store' } }
			);
		}
		return json({ imageInput }, { headers: { 'Cache-Control': 'no-store' } });
	} catch {
		return json(
			{ imageInput: { enabled: false, limits: null } },
			{ status: 502, headers: { 'Cache-Control': 'no-store' } }
		);
	}
};
