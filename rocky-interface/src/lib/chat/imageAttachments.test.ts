import { describe, expect, it } from 'vitest';
import type { ChatImageLimits } from '$lib/types/chat';
import {
	ImageAttachmentError,
	prepareImageAttachments,
	storedChatImages
} from './imageAttachments';

const limits: ChatImageLimits = {
	maxImages: 2,
	maxImageBytes: 100,
	maxTotalBytes: 150,
	maxPixels: 100,
	maxTotalPixels: 150
};

function fakeFile(name: string, type: string, size: number): File {
	return { name, type, size } as File;
}

const dependencies = {
	readDataUrl: async (file: File) => `data:${file.type};base64,QUJDRA==`,
	inspectImage: async () => ({ width: 5, height: 10 }),
	id: () => 'image-one'
};

describe('prepareImageAttachments', () => {
	it('atomically prepares a supported image with measured dimensions', async () => {
		await expect(
			prepareImageAttachments([fakeFile('diagram.png', 'image/png', 50)], [], limits, dependencies)
		).resolves.toEqual([
			{
				id: 'image-one',
				imageUrl: 'data:image/png;base64,QUJDRA==',
				mimeType: 'image/png',
				byteLength: 50,
				width: 5,
				height: 10,
				name: 'diagram.png'
			}
		]);
	});

	it('rejects unsupported types, count, byte, and pixel overages', async () => {
		await expect(
			prepareImageAttachments(
				[fakeFile('notes.svg', 'image/svg+xml', 20)],
				[],
				limits,
				dependencies
			)
		).rejects.toBeInstanceOf(ImageAttachmentError);
		await expect(
			prepareImageAttachments(
				[fakeFile('one.png', 'image/png', 20), fakeFile('two.png', 'image/png', 20)],
				[
					{
						id: 'existing',
						imageUrl: 'data:image/png;base64,QUJDRA==',
						mimeType: 'image/png',
						byteLength: 20
					}
				],
				limits,
				dependencies
			)
		).rejects.toThrow('at most 2 images');
		await expect(
			prepareImageAttachments([fakeFile('large.png', 'image/png', 101)], [], limits, dependencies)
		).rejects.toThrow('per-image limit');
		await expect(
			prepareImageAttachments([fakeFile('pixels.png', 'image/png', 20)], [], limits, {
				...dependencies,
				inspectImage: async () => ({ width: 11, height: 10 })
			})
		).rejects.toThrow('pixel limit');
	});
});

describe('storedChatImages', () => {
	it('restores only supported Base64 data URLs from owned history', () => {
		expect(
			storedChatImages(
				[
					{ type: 'input_image', image_url: 'data:image/webp;base64,QUJDRA==' },
					{ type: 'input_image', image_url: 'https://example.invalid/image.png' },
					{ type: 'input_image', image_url: 'data:image/svg+xml;base64,QUJDRA==' }
				],
				'message-one'
			)
		).toEqual([
			{
				id: 'message-one-image-0',
				imageUrl: 'data:image/webp;base64,QUJDRA==',
				mimeType: 'image/webp',
				byteLength: 4,
				name: 'Attached image 1'
			}
		]);
	});
});
