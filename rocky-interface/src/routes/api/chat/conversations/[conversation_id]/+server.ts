import { json, type RequestHandler } from '@sveltejs/kit';
import { CHAT_API_BASE_URL, chatApiPayload, chatRequestHeaders, requireChatUser } from '$lib/server/chatProxy';

export const POST: RequestHandler = async ({ params, fetch, locals }) => {
	const user = requireChatUser(locals);
	const conversation_id = params.conversation_id;

	if (!conversation_id) {
		return json({ error: 'Missing conversation_id.' }, { status: 400 });
	}

	try {
		const response = await fetch(`${CHAT_API_BASE_URL}/conversations/${conversation_id}`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				Accept: 'application/json',
				...chatRequestHeaders(user)
			},
			body: JSON.stringify(chatApiPayload())
		});

		const payload = await response.json().catch(() => ({
			error: 'Unable to parse conversation response.'
		}));

		return json(payload, { status: response.status });
	} catch {
		return json({ error: 'Unable to load conversation.' }, { status: 502 });
	}
};
