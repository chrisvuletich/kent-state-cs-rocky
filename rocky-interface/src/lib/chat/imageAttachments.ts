import type { ChatImage, ChatImageLimits, ChatImageMimeType } from '$lib/types/chat';

const SUPPORTED_IMAGE_TYPES = new Set<ChatImageMimeType>(['image/jpeg', 'image/png', 'image/webp']);

export class ImageAttachmentError extends Error {
	constructor(message: string) {
		super(message);
		this.name = 'ImageAttachmentError';
	}
}

type ImageDimensions = { width: number; height: number };

type AttachmentDependencies = {
	readDataUrl: (file: File) => Promise<string>;
	inspectImage: (dataUrl: string) => Promise<ImageDimensions>;
	id: () => string;
};

function formatBytes(bytes: number): string {
	if (bytes >= 1024 * 1024) return `${Math.floor(bytes / (1024 * 1024))} MB`;
	return `${Math.floor(bytes / 1024)} KB`;
}

function defaultId(): string {
	return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
}

function readDataUrl(file: File): Promise<string> {
	return new Promise((resolve, reject) => {
		const reader = new FileReader();
		reader.onerror = () => reject(new ImageAttachmentError(`Unable to read ${file.name}.`));
		reader.onload = () => {
			if (typeof reader.result !== 'string') {
				reject(new ImageAttachmentError(`Unable to read ${file.name}.`));
				return;
			}
			resolve(reader.result);
		};
		reader.readAsDataURL(file);
	});
}

function inspectImage(dataUrl: string): Promise<ImageDimensions> {
	return new Promise((resolve, reject) => {
		const image = new Image();
		image.onload = () => {
			if (!image.naturalWidth || !image.naturalHeight) {
				reject(new ImageAttachmentError('An attached image has invalid dimensions.'));
				return;
			}
			resolve({ width: image.naturalWidth, height: image.naturalHeight });
		};
		image.onerror = () => reject(new ImageAttachmentError('Unable to decode an attached image.'));
		image.src = dataUrl;
	});
}

const DEFAULT_DEPENDENCIES: AttachmentDependencies = {
	readDataUrl,
	inspectImage,
	id: defaultId
};

function validateLimits(limits: ChatImageLimits): void {
	for (const value of Object.values(limits)) {
		if (!Number.isSafeInteger(value) || value < 1) {
			throw new ImageAttachmentError('Image attachment limits are unavailable.');
		}
	}
}

export async function prepareImageAttachments(
	files: readonly File[],
	existing: readonly ChatImage[],
	limits: ChatImageLimits,
	dependencies: AttachmentDependencies = DEFAULT_DEPENDENCIES
): Promise<ChatImage[]> {
	validateLimits(limits);
	if (files.length === 0) return [];
	if (existing.length + files.length > limits.maxImages) {
		throw new ImageAttachmentError(`You can attach at most ${limits.maxImages} images.`);
	}

	let totalBytes = existing.reduce((total, image) => total + image.byteLength, 0);
	let totalPixels = existing.reduce(
		(total, image) => total + (image.width || 0) * (image.height || 0),
		0
	);
	for (const file of files) {
		if (!SUPPORTED_IMAGE_TYPES.has(file.type as ChatImageMimeType)) {
			throw new ImageAttachmentError(
				`${file.name || 'That file'} is not a JPEG, PNG, or WebP image.`
			);
		}
		if (!Number.isSafeInteger(file.size) || file.size < 1) {
			throw new ImageAttachmentError(`${file.name || 'That image'} is empty or invalid.`);
		}
		if (file.size > limits.maxImageBytes) {
			throw new ImageAttachmentError(
				`${file.name || 'That image'} exceeds the ${formatBytes(limits.maxImageBytes)} per-image limit.`
			);
		}
		totalBytes += file.size;
		if (totalBytes > limits.maxTotalBytes) {
			throw new ImageAttachmentError(
				`Attached images may total at most ${formatBytes(limits.maxTotalBytes)}.`
			);
		}
	}

	const prepared: ChatImage[] = [];
	for (const file of files) {
		const dataUrl = await dependencies.readDataUrl(file);
		const expectedPrefix = `data:${file.type};base64,`;
		if (!dataUrl.startsWith(expectedPrefix)) {
			throw new ImageAttachmentError(`${file.name || 'That image'} could not be encoded safely.`);
		}
		const dimensions = await dependencies.inspectImage(dataUrl);
		const pixelCount = dimensions.width * dimensions.height;
		if (!Number.isSafeInteger(pixelCount) || pixelCount < 1) {
			throw new ImageAttachmentError(`${file.name || 'That image'} has invalid dimensions.`);
		}
		if (pixelCount > limits.maxPixels) {
			throw new ImageAttachmentError(
				`${file.name || 'That image'} exceeds the ${limits.maxPixels.toLocaleString()} pixel limit.`
			);
		}
		totalPixels += pixelCount;
		if (totalPixels > limits.maxTotalPixels) {
			throw new ImageAttachmentError(
				`Attached images may total at most ${limits.maxTotalPixels.toLocaleString()} pixels.`
			);
		}
		prepared.push({
			id: dependencies.id(),
			imageUrl: dataUrl,
			mimeType: file.type as ChatImageMimeType,
			byteLength: file.size,
			width: dimensions.width,
			height: dimensions.height,
			name: file.name || undefined
		});
	}
	return prepared;
}

function decodedDataUrl(
	value: unknown
): { imageUrl: string; mimeType: ChatImageMimeType; bytes: number } | null {
	if (typeof value !== 'string') return null;
	const match = /^data:(image\/(?:jpeg|png|webp));base64,([A-Za-z0-9+/]+={0,2})$/.exec(value);
	if (!match || match[2].length % 4 !== 0) return null;
	const padding = match[2].length - match[2].replace(/=+$/, '').length;
	const bytes = (match[2].length / 4) * 3 - padding;
	if (!Number.isSafeInteger(bytes) || bytes < 1) return null;
	return { imageUrl: value, mimeType: match[1] as ChatImageMimeType, bytes };
}

export function storedChatImages(value: unknown, messageId: string): ChatImage[] {
	if (!Array.isArray(value)) return [];
	return value.slice(0, 16).flatMap((item, index) => {
		if (!item || typeof item !== 'object' || Array.isArray(item)) return [];
		const record = item as Record<string, unknown>;
		if (record.type !== 'input_image') return [];
		const decoded = decodedDataUrl(record.image_url);
		if (!decoded) return [];
		return [
			{
				id: `${messageId}-image-${index}`,
				imageUrl: decoded.imageUrl,
				mimeType: decoded.mimeType,
				byteLength: decoded.bytes,
				name: `Attached image ${index + 1}`
			}
		];
	});
}
