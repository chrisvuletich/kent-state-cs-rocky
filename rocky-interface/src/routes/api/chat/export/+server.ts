import { env } from '$env/dynamic/private';
import { json, type RequestHandler } from '@sveltejs/kit';

const CHAT_API_URL = (env.ROCKY_CHAT_API_URL ?? 'http://127.0.0.1:5003/rocky-api').trim();
const CHAT_API_KEY = (env.ROCKY_CHAT_API_KEY ?? 'SOME_API_KEY').trim();

const CHAT_API_BASE_URL = CHAT_API_URL.replace(/\/rocky-api\/?$/, '');

export const POST: RequestHandler = async ({ request, fetch }) => {
	const body = await request.json().catch(() => null);

	const conversation_id =
		typeof body?.conversation_id === 'string' ? body.conversation_id.trim() : '';

	const format = typeof body?.format === 'string' ? body.format.trim() : 'markdown';

	if (!conversation_id) {
		return json({ error: 'Missing conversation_id.' }, { status: 400 });
	}

	try {
		const response = await fetch(`${CHAT_API_BASE_URL}/conversations/${conversation_id}/export`, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				Accept: format === 'json' ? 'application/json' : 'text/markdown'
			},
			body: JSON.stringify({
				'api-key': CHAT_API_KEY,
				format
			})
		});

		const text = await response.text();

		if (!response.ok) {
			let payload: unknown = { error: text || 'Export failed.' };

			try {
				payload = JSON.parse(text);
			} catch {
				// Keep plain text fallback.
			}

			return json(payload, { status: response.status });
		}

		return new Response(text, {
			status: 200,
			headers: {
				'Content-Type': format === 'json' ? 'application/json' : 'text/markdown',
				'Content-Disposition': `attachment; filename="rocky-conversation-${conversation_id}.${format === 'json' ? 'json' : 'md'}"`
			}
		});
	} catch {
		return json({ error: 'Unable to export conversation.' }, { status: 502 });
	}
};
