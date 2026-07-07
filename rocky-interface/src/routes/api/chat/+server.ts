import { env } from '$env/dynamic/private';
import { json, type RequestHandler } from '@sveltejs/kit';

const CHAT_API_URL = (env.ROCKY_CHAT_API_URL ?? 'http://127.0.0.1:5003/rocky-api').trim();
const CHAT_API_KEY = (env.ROCKY_CHAT_API_KEY ?? 'SOME_API_KEY').trim();

export const POST: RequestHandler = async ({ request, fetch }) => {
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
				Accept: 'application/json'
			},
			body: JSON.stringify({
				'api-key': CHAT_API_KEY,
				message,
				...(conversation_id ? { conversation_id } : {})
			})
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
