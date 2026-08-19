import { describe, expect, it } from 'vitest';
import {
	ChatImageInputError,
	imageCapabilitiesFromReadiness,
	publicImageContentBlocks
} from './chatImageInput';

const tinyPng = 'data:image/png;base64,iVBORw0KGgo=';

describe('publicImageContentBlocks', () => {
	it('constructs the deliberately small Responses image block subset', () => {
		expect(publicImageContentBlocks([{ image_url: tinyPng }])).toEqual([
			{ type: 'input_image', image_url: tinyPng, detail: 'auto' }
		]);
	});

	it('rejects remote, malformed, and extended image objects', () => {
		for (const images of [
			[{ image_url: 'https://example.invalid/image.png' }],
			[{ image_url: 'data:image/png;base64,%%%%' }],
			[{ image_url: tinyPng, detail: 'high' }],
			[{ image_url: tinyPng, file_id: 'file-one' }]
		]) {
			expect(() => publicImageContentBlocks(images)).toThrow(ChatImageInputError);
		}
	});
});

describe('imageCapabilitiesFromReadiness', () => {
	it('enables attachments only when both services and their limits agree', () => {
		expect(
			imageCapabilitiesFromReadiness({
				ok: true,
				image_input: {
					rocky_enabled: true,
					granite_enabled: true,
					limits_match: true,
					rocky_limits: {
						max_images: 4,
						max_image_bytes: 4_194_304,
						max_total_bytes: 6_291_456,
						max_pixels: 20_000_000,
						max_total_pixels: 40_000_000
					}
				}
			})
		).toEqual({
			enabled: true,
			limits: {
				maxImages: 4,
				maxImageBytes: 4_194_304,
				maxTotalBytes: 6_291_456,
				maxPixels: 20_000_000,
				maxTotalPixels: 40_000_000
			}
		});
	});

	it('fails closed on disagreement or malformed limits', () => {
		expect(
			imageCapabilitiesFromReadiness({
				ok: true,
				image_input: {
					rocky_enabled: true,
					granite_enabled: false,
					limits_match: true,
					rocky_limits: { max_images: 4 }
				}
			})
		).toEqual({ enabled: false, limits: null });
	});

	it('does not enable attachments from an unhealthy readiness payload', () => {
		expect(
			imageCapabilitiesFromReadiness({
				ok: false,
				image_input: {
					rocky_enabled: true,
					granite_enabled: true,
					limits_match: true,
					rocky_limits: {
						max_images: 4,
						max_image_bytes: 4_194_304,
						max_total_bytes: 6_291_456,
						max_pixels: 20_000_000,
						max_total_pixels: 40_000_000
					}
				}
			})
		).toEqual({
			enabled: false,
			limits: {
				maxImages: 4,
				maxImageBytes: 4_194_304,
				maxTotalBytes: 6_291_456,
				maxPixels: 20_000_000,
				maxTotalPixels: 40_000_000
			}
		});
	});
});
