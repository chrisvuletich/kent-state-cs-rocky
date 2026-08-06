import { json, type RequestHandler } from '@sveltejs/kit';
import { CHAT_API_BASE_URL, chatApiPayload, chatRequestHeaders, requireChatUser } from '$lib/server/chatProxy';

export const POST: RequestHandler = async ({ fetch, locals }) => {
	const user = requireChatUser(locals);
	try {
		const response = await fetch(`${CHAT_API_BASE_URL}/conversations/list`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				Accept: 'application/json',
				...chatRequestHeaders(user)
			},
			body: JSON.stringify(chatApiPayload())
		});

		const payload = await response.json().catch(() => ({
			error: 'Unable to parse conversations response.'
		}));

		return json(payload, { status: response.status });
	} catch {
		return json({ error: 'Unable to load conversations.' }, { status: 502 });
	}
};
