import { json, type RequestHandler } from '@sveltejs/kit';
import { CHAT_API_URL, chatApiPayload, chatRequestHeaders, requireChatUser } from '$lib/server/chatProxy';

export const POST: RequestHandler = async ({ request, fetch, locals }) => {
	const user = requireChatUser(locals);
	const body = await request.json().catch(() => null);
	const message = typeof body?.message === 'string' ? body.message.trim() : '';
	const conversation_id = typeof body?.conversation_id === 'string' ? body.conversation_id.trim() : '';

	if (!message) {
		return json({ error: 'Missing message.' }, { status: 400 });
	}

	try {
		const response = await fetch(CHAT_API_URL, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				Accept: 'application/json',
				...chatRequestHeaders(user)
			},
			body: JSON.stringify(chatApiPayload({
				model: 'rocky',
				input: message,
				store: true,
				...(conversation_id ? { conversation_id } : {})
			}))
		});

		const text = await response.text();
		let payload: unknown = null;

		if (text.length > 0) {
			try {
				payload = JSON.parse(text);
			} catch {
				payload = { raw: text };
			}
		}

		return json(payload, { status: response.status });
	} catch {
		return json({ error: 'Unable to reach Rocky chat API.' }, { status: 502 });
	}
};
