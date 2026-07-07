import { env } from '$env/dynamic/private';
import { json, type RequestHandler } from '@sveltejs/kit';

const CHAT_API_URL = (env.ROCKY_CHAT_API_URL ?? 'http://127.0.0.1:5003/rocky-api').trim();
const CHAT_API_KEY = (env.ROCKY_CHAT_API_KEY ?? 'SOME_API_KEY').trim();

const CHAT_API_BASE_URL = CHAT_API_URL.replace(/\/rocky-api\/?$/, '');

export const POST: RequestHandler = async ({ params, fetch }) => {
	const conversation_id = params.conversation_id;

	if (!conversation_id) {
		return json({ error: 'Missing conversation_id.' }, { status: 400 });
	}

	try {
		const response = await fetch(`${CHAT_API_BASE_URL}/conversations/${conversation_id}`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				Accept: 'application/json'
			},
			body: JSON.stringify({
				'api-key': CHAT_API_KEY
			})
		});

		const payload = await response.json().catch(() => ({
			error: 'Unable to parse conversation response.'
		}));

		return json(payload, { status: response.status });
	} catch {
		return json({ error: 'Unable to load conversation.' }, { status: 502 });
	}
};
