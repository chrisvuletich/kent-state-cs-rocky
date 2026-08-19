import type { ChatImageLimits, ChatImageMimeType } from '$lib/types/chat';

const SUPPORTED_MIME_TYPES = new Set<ChatImageMimeType>(['image/jpeg', 'image/png', 'image/webp']);
const MAX_PROXY_IMAGES = 16;
const MAX_PROXY_IMAGE_CHARACTERS = 10 * 1024 * 1024;
const BASE64_PATTERN = /^[A-Za-z0-9+/]+={0,2}$/;

export type PublicImageContentBlock = {
	type: 'input_image';
	image_url: string;
	detail: 'auto';
};

export class ChatImageInputError extends Error {
	constructor(message: string) {
		super(message);
		this.name = 'ChatImageInputError';
	}
}

function parseDataUrl(value: unknown): string {
	if (typeof value !== 'string') {
		throw new ChatImageInputError('Each attached image must contain a valid image URL.');
	}
	const match = /^data:(image\/(?:jpeg|png|webp));base64,(.*)$/.exec(value);
	if (!match || !SUPPORTED_MIME_TYPES.has(match[1] as ChatImageMimeType)) {
		throw new ChatImageInputError('Attached images must be JPEG, PNG, or WebP files.');
	}
	const encoded = match[2];
	if (!encoded || encoded.length % 4 !== 0 || !BASE64_PATTERN.test(encoded)) {
		throw new ChatImageInputError('An attached image contains invalid Base64 data.');
	}
	const padding = encoded.length - encoded.replace(/=+$/, '').length;
	const decodedBytes = (encoded.length / 4) * 3 - padding;
	if (!Number.isSafeInteger(decodedBytes) || decodedBytes < 1) {
		throw new ChatImageInputError('An attached image is empty or invalid.');
	}
	return value;
}

export function publicImageContentBlocks(value: unknown): PublicImageContentBlock[] {
	if (value === undefined) return [];
	if (!Array.isArray(value)) {
		throw new ChatImageInputError('Images must be submitted as a list.');
	}
	if (value.length > MAX_PROXY_IMAGES) {
		throw new ChatImageInputError(`A message may contain at most ${MAX_PROXY_IMAGES} images.`);
	}

	let totalCharacters = 0;
	return value.map((item) => {
		if (!item || typeof item !== 'object' || Array.isArray(item)) {
			throw new ChatImageInputError('Each attached image must be an object.');
		}
		const record = item as Record<string, unknown>;
		const unsupportedFields = Object.keys(record).filter(
			(field) => field !== 'image_url' && field !== 'detail'
		);
		if (unsupportedFields.length > 0 || (record.detail !== undefined && record.detail !== 'auto')) {
			throw new ChatImageInputError('An attached image contains unsupported options.');
		}
		const imageUrl = parseDataUrl(record.image_url);
		totalCharacters += imageUrl.length;
		if (totalCharacters > MAX_PROXY_IMAGE_CHARACTERS) {
			throw new ChatImageInputError('The combined attached image payload is too large.');
		}
		return { type: 'input_image', image_url: imageUrl, detail: 'auto' };
	});
}

function positiveInteger(value: unknown): number | null {
	return Number.isSafeInteger(value) && typeof value === 'number' && value > 0 ? value : null;
}

export function imageCapabilitiesFromReadiness(payload: unknown): {
	enabled: boolean;
	limits: ChatImageLimits | null;
} {
	if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
		return { enabled: false, limits: null };
	}
	const readiness = payload as Record<string, unknown>;
	const imageInput = readiness.image_input;
	if (!imageInput || typeof imageInput !== 'object' || Array.isArray(imageInput)) {
		return { enabled: false, limits: null };
	}
	const imageRecord = imageInput as Record<string, unknown>;
	const rawLimits = imageRecord.rocky_limits;
	if (!rawLimits || typeof rawLimits !== 'object' || Array.isArray(rawLimits)) {
		return { enabled: false, limits: null };
	}
	const limitRecord = rawLimits as Record<string, unknown>;
	const maxImages = positiveInteger(limitRecord.max_images);
	const maxImageBytes = positiveInteger(limitRecord.max_image_bytes);
	const maxTotalBytes = positiveInteger(limitRecord.max_total_bytes);
	const maxPixels = positiveInteger(limitRecord.max_pixels);
	const maxTotalPixels = positiveInteger(limitRecord.max_total_pixels);
	if (!maxImages || !maxImageBytes || !maxTotalBytes || !maxPixels || !maxTotalPixels) {
		return { enabled: false, limits: null };
	}
	const limits = { maxImages, maxImageBytes, maxTotalBytes, maxPixels, maxTotalPixels };
	const enabled =
		readiness.ok === true &&
		imageRecord.rocky_enabled === true &&
		imageRecord.granite_enabled === true &&
		imageRecord.limits_match === true;
	return { enabled, limits };
}
