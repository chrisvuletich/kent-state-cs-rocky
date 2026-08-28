import { json, type RequestHandler } from '@sveltejs/kit';
import {
	CHAT_API_URL,
	CHAT_MODEL,
	CHAT_STREAMING_ENABLED,
	chatApiPayload,
	chatRequestHeaders,
	requireChatUser
} from '$lib/server/chatProxy';
import {
	forwardedChatResponseHeaders,
	streamingChatResponseHeaders
} from '$lib/server/chatResponseHeaders';
import { ChatImageInputError, publicImageContentBlocks } from '$lib/server/chatImageInput';

export const POST: RequestHandler = async ({ request, fetch, locals }) => {
	const user = requireChatUser(locals);
	let body;
	try {
		body = await request.json();
	} catch (error) {
		const status =
			error && typeof error === 'object' && 'status' in error
				? (error as { status?: unknown }).status
				: null;
		if (status === 413) {
			return json(
				{
					error: {
						message: 'Request body is too large.',
						type: 'invalid_request_error',
						param: null,
						code: 'request_too_large'
					}
				},
				{ status: 413 }
			);
		}
		return json(
			{
				error: {
					message: 'Request body must be valid JSON.',
					type: 'invalid_request_error',
					param: null,
					code: 'invalid_json'
				}
			},
			{ status: 400 }
		);
	}
	const message = typeof body?.message === 'string' && body.message.trim() ? body.message : '';
	const conversation_id =
		typeof body?.conversation_id === 'string' ? body.conversation_id.trim() : '';
	let imageBlocks;
	try {
		imageBlocks = publicImageContentBlocks(body?.images);
	} catch (error) {
		if (!(error instanceof ChatImageInputError)) throw error;
		return json(
			{
				error: {
					message: error.message,
					type: 'invalid_request_error',
					param: 'images',
					code: 'invalid_image'
				}
			},
			{ status: 400 }
		);
	}

	if (!message && imageBlocks.length === 0) {
		return json({ error: 'Missing message or image.' }, { status: 400 });
	}
	const input =
		imageBlocks.length > 0
			? [
					{
						role: 'user',
						content: [...(message ? [{ type: 'input_text', text: message }] : []), ...imageBlocks]
					}
				]
			: message;

	try {
		const response = await fetch(CHAT_API_URL, {
			method: 'POST',
			signal: request.signal,
			headers: {
				'Content-Type': 'application/json',
				Accept: CHAT_STREAMING_ENABLED ? 'text/event-stream' : 'application/json',
				...chatRequestHeaders(user)
			},
			body: JSON.stringify(
				chatApiPayload({
					model: CHAT_MODEL,
					input,
					...(CHAT_STREAMING_ENABLED ? { stream: true } : {}),
					store: true,
					...(conversation_id ? { conversation_id } : {})
				})
			)
		});

		const contentType = response.headers.get('content-type')?.toLowerCase() || '';
		if (CHAT_STREAMING_ENABLED && response.ok) {
			if (!response.body || !contentType.startsWith('text/event-stream')) {
				await response.body?.cancel().catch(() => undefined);
				return json(
					{
						error: {
							message: 'Rocky chat API returned an invalid streaming response.',
							type: 'server_error',
							param: null,
							code: 'invalid_model_response'
						}
					},
					{ status: 502, headers: forwardedChatResponseHeaders(response.headers) }
				);
			}
			return new Response(response.body, {
				status: response.status,
				headers: streamingChatResponseHeaders(response.headers)
			});
		}

		const text = await response.text();
		let payload: unknown = null;

		if (text.length > 0) {
			try {
				payload = JSON.parse(text);
			} catch {
				payload = { raw: text };
			}
		}

		return json(payload, {
			status: response.status,
			headers: forwardedChatResponseHeaders(response.headers)
		});
	} catch {
		return json(
			{
				error: {
					message: 'Unable to reach Rocky chat API.',
					type: 'server_error',
					param: null,
					code: 'model_service_unavailable'
				}
			},
			{ status: 502 }
		);
	}
};
