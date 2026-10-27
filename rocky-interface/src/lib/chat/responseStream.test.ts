import { describe, expect, it, vi } from 'vitest';
import { consumeRockyResponseStream, RockyResponseStreamError } from '$lib/chat/responseStream';

function event(type: string, sequence_number: number, fields: Record<string, unknown> = {}) {
	return { type, sequence_number, ...fields };
}

function successfulEvents() {
	return [
		event('response.created', 0),
		event('response.in_progress', 1),
		event('response.output_item.added', 2),
		event('response.content_part.added', 3),
		event('response.output_text.delta', 4, { delta: 'Olá ' }),
		event('response.output_text.delta', 5, { delta: '🪨' }),
		event('response.output_text.done', 6, { text: 'Olá 🪨' }),
		event('response.content_part.done', 7),
		event('response.output_item.done', 8),
		event('response.completed', 9, {
			response: {
				id: 'resp_synthetic',
				status: 'completed',
				output_text: 'Olá 🪨',
				conversation_id: 'conversation-synthetic',
				message_stored: true
			}
		})
	];
}

function encodeEvents(events: Array<Record<string, unknown>>, newline = '\n') {
	return events
		.map((item) => `event: ${item.type}${newline}data: ${JSON.stringify(item)}${newline}${newline}`)
		.join('');
}

function streamingResponse(chunks: Uint8Array[], contentType = 'text/event-stream') {
	return new Response(
		new ReadableStream<Uint8Array>({
			start(controller) {
				for (const chunk of chunks) controller.enqueue(chunk);
				controller.close();
			}
		}),
		{ status: 200, headers: { 'Content-Type': contentType } }
	);
}

describe('consumeRockyResponseStream', () => {
	it.each(['', '   ', 'Partial answer'])(
		'accepts token-limited output %j without treating it as a broken stream',
		async (text) => {
			const events = successfulEvents().slice(0, 4);
			if (text) events.push(event('response.output_text.delta', events.length, { delta: text }));
			for (const type of [
				'response.output_text.done',
				'response.content_part.done',
				'response.output_item.done'
			]) {
				events.push(event(type, events.length, { text }));
			}
			events.push(
				event('response.incomplete', events.length, {
					response: {
						status: 'incomplete',
						output_text: text,
						incomplete_details: { reason: 'max_output_tokens' }
					}
				})
			);
			const result = await consumeRockyResponseStream(
				streamingResponse([new TextEncoder().encode(encodeEvents(events))])
			);
			expect(result.response.status).toBe('incomplete');
			expect(result.outputText).toBe(text);

			for (const final of [
				{ type: 'response.completed', response: { status: 'completed', output_text: '' } },
				{ type: 'response.incomplete', response: { status: 'incomplete', output_text: text } },
				{ type: 'response.incomplete', response: { status: 'completed', output_text: text } }
			]) {
				events[events.length - 1] = event(final.type, events.length - 1, {
					response: final.response
				});
				await expect(
					consumeRockyResponseStream(
						streamingResponse([new TextEncoder().encode(encodeEvents(events))])
					)
				).rejects.toMatchObject({ code: 'invalid_model_response' });
			}
		}
	);

	it('decodes split UTF-8 chunks and reports cumulative text deltas', async () => {
		const encoded = new TextEncoder().encode(encodeEvents(successfulEvents(), '\r\n'));
		const emoji = new TextEncoder().encode('🪨');
		const emojiIndex = encoded.findIndex((_value, index) =>
			emoji.every((emojiByte, offset) => encoded[index + offset] === emojiByte)
		);
		const chunks = [encoded.slice(0, emojiIndex + 1), encoded.slice(emojiIndex + 1)];
		const onDelta = vi.fn();

		const result = await consumeRockyResponseStream(streamingResponse(chunks), onDelta);

		expect(result.outputText).toBe('Olá 🪨');
		expect(result.response.conversation_id).toBe('conversation-synthetic');
		expect(onDelta.mock.calls).toEqual([
			['Olá ', 'Olá '],
			['Olá 🪨', '🪨']
		]);
	});

	it('ignores queue keepalive comments without consuming sequence numbers', async () => {
		const events = successfulEvents();
		const encoded = [
			encodeEvents(events.slice(0, 4)),
			': keepalive\n\n',
			encodeEvents(events.slice(4, 6)),
			': keepalive\n\n',
			encodeEvents(events.slice(6))
		].join('');

		const result = await consumeRockyResponseStream(
			streamingResponse([new TextEncoder().encode(encoded)])
		);

		expect(result.outputText).toBe('Olá 🪨');
		expect(result.response.status).toBe('completed');
	});

	it('surfaces a typed terminal stream error', async () => {
		const events = successfulEvents().slice(0, 5);
		events[4] = event('error', 4, {
			code: 'model_timeout',
			message: 'Model request timed out.',
			param: null
		});
		const response = streamingResponse([new TextEncoder().encode(encodeEvents(events))]);

		await expect(consumeRockyResponseStream(response)).rejects.toEqual(
			expect.objectContaining<Partial<RockyResponseStreamError>>({
				name: 'RockyResponseStreamError',
				code: 'model_timeout',
				message: 'Model request timed out.'
			})
		);
	});

	it('rejects sequence gaps, incomplete streams, and non-SSE responses', async () => {
		const sequenceGap = successfulEvents();
		sequenceGap[4] = event('response.output_text.delta', 8, { delta: 'Olá ' });

		for (const response of [
			streamingResponse([new TextEncoder().encode(encodeEvents(sequenceGap))]),
			streamingResponse([new TextEncoder().encode(encodeEvents(successfulEvents().slice(0, 5)))]),
			streamingResponse([new TextEncoder().encode('{}')], 'application/json')
		]) {
			await expect(consumeRockyResponseStream(response)).rejects.toMatchObject({
				code: 'invalid_model_response'
			});
		}
	});
});
