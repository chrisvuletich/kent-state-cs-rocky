const STREAM_PREFIX = [
	'response.created',
	'response.in_progress',
	'response.output_item.added',
	'response.content_part.added'
] as const;

const STREAM_SUFFIX = [
	'response.output_text.done',
	'response.content_part.done',
	'response.output_item.done',
	'response.completed'
] as const;

const MAX_BUFFERED_FRAME_CHARACTERS = 1024 * 1024;

type StreamEvent = Record<string, unknown> & {
	type: string;
	sequence_number: number;
};

export type RockyCompletedStream = {
	outputText: string;
	response: Record<string, unknown>;
};

export class RockyResponseStreamError extends Error {
	readonly code: string;

	constructor(message: string, code: string) {
		super(message);
		this.name = 'RockyResponseStreamError';
		this.code = code;
	}
}

function invalidStream(message = 'Rocky returned an invalid streaming response.'): never {
	throw new RockyResponseStreamError(message, 'invalid_model_response');
}

class SseFrameDecoder {
	private readonly decoder = new TextDecoder('utf-8', { fatal: true });
	private buffer = '';

	push(chunk: Uint8Array): StreamEvent[] {
		try {
			this.buffer += this.decoder.decode(chunk, { stream: true });
		} catch {
			invalidStream();
		}
		return this.extractFrames();
	}

	finish(): StreamEvent[] {
		try {
			this.buffer += this.decoder.decode();
		} catch {
			invalidStream();
		}
		const events = this.extractFrames();
		if (this.buffer.trim()) invalidStream('Rocky returned an incomplete streaming response.');
		return events;
	}

	private extractFrames(): StreamEvent[] {
		const events: StreamEvent[] = [];
		while (true) {
			const separator = /\r?\n\r?\n/.exec(this.buffer);
			if (!separator || separator.index === undefined) break;
			const frame = this.buffer.slice(0, separator.index);
			this.buffer = this.buffer.slice(separator.index + separator[0].length);
			if (frame.length > MAX_BUFFERED_FRAME_CHARACTERS) invalidStream();
			const event = this.parseFrame(frame);
			if (event) events.push(event);
		}
		if (this.buffer.length > MAX_BUFFERED_FRAME_CHARACTERS) invalidStream();
		return events;
	}

	private parseFrame(frame: string): StreamEvent | null {
		const lines = frame.split(/\r?\n/);
		if (lines.length === 1 && lines[0] === ': keepalive') return null;
		if (lines.length !== 2 || !lines[0].startsWith('event: ') || !lines[1].startsWith('data: ')) {
			invalidStream();
		}

		const eventName = lines[0].slice('event: '.length);
		let payload: unknown;
		try {
			payload = JSON.parse(lines[1].slice('data: '.length));
		} catch {
			invalidStream();
		}
		if (
			!payload ||
			typeof payload !== 'object' ||
			!('type' in payload) ||
			(payload as { type?: unknown }).type !== eventName
		) {
			invalidStream();
		}
		return payload as StreamEvent;
	}
}

function streamResponseObject(event: StreamEvent): Record<string, unknown> {
	const response = event.response;
	if (!response || typeof response !== 'object' || Array.isArray(response)) invalidStream();
	return response as Record<string, unknown>;
}

export async function consumeRockyResponseStream(
	response: Response,
	onDelta: (outputText: string, delta: string) => void = () => undefined
): Promise<RockyCompletedStream> {
	if (!response.ok || !response.body) invalidStream();
	const contentType = response.headers.get('content-type')?.toLowerCase() || '';
	if (!contentType.startsWith('text/event-stream')) invalidStream();

	const reader = response.body.getReader();
	const decoder = new SseFrameDecoder();
	let expectedSequence = 0;
	let prefixIndex = 0;
	let suffixIndex = 0;
	let outputText = '';
	let sawDelta = false;
	let completed: RockyCompletedStream | null = null;

	const consumeEvent = (event: StreamEvent) => {
		if (
			!Number.isSafeInteger(event.sequence_number) ||
			event.sequence_number !== expectedSequence
		) {
			invalidStream();
		}
		expectedSequence += 1;

		if (event.type === 'error') {
			const code = typeof event.code === 'string' ? event.code.trim() : '';
			const message = typeof event.message === 'string' ? event.message.trim() : '';
			if (!code || !message) invalidStream();
			throw new RockyResponseStreamError(message, code);
		}
		if (completed) invalidStream();

		if (prefixIndex < STREAM_PREFIX.length) {
			if (event.type !== STREAM_PREFIX[prefixIndex]) invalidStream();
			prefixIndex += 1;
			return;
		}

		if (suffixIndex === 0 && event.type === 'response.output_text.delta') {
			if (typeof event.delta !== 'string' || !event.delta) invalidStream();
			outputText += event.delta;
			sawDelta = true;
			onDelta(outputText, event.delta);
			return;
		}

		if (!sawDelta || event.type !== STREAM_SUFFIX[suffixIndex]) invalidStream();
		if (event.type === 'response.output_text.done' && event.text !== outputText) {
			invalidStream();
		}
		if (event.type === 'response.completed') {
			const completedResponse = streamResponseObject(event);
			if (
				completedResponse.status !== 'completed' ||
				completedResponse.output_text !== outputText
			) {
				invalidStream();
			}
			completed = { outputText, response: completedResponse };
		}
		suffixIndex += 1;
	};

	let streamFinished = false;
	try {
		while (true) {
			const { done, value } = await reader.read();
			if (done) break;
			for (const event of decoder.push(value)) consumeEvent(event);
		}
		for (const event of decoder.finish()) consumeEvent(event);
		streamFinished = true;
		if (!completed || suffixIndex !== STREAM_SUFFIX.length) {
			invalidStream('Rocky ended the stream before completing its response.');
		}
		return completed;
	} finally {
		if (!streamFinished) await reader.cancel().catch(() => undefined);
		reader.releaseLock();
	}
}
