import { readdirSync, readFileSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const STYLE_ROOT = fileURLToPath(new URL('.', import.meta.url));

function cssFiles(directory: string): string[] {
	return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
		const path = join(directory, entry.name);
		if (entry.isDirectory()) return cssFiles(path);
		return entry.isFile() && entry.name.endsWith('.css') ? [path] : [];
	});
}

function ownersOf(selector: string): string[] {
	const escapedSelector = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
	const declaration = new RegExp(`(^|\\n)${escapedSelector}\\s*\\{`);
	return cssFiles(STYLE_ROOT)
		.filter((path) => declaration.test(readFileSync(path, 'utf8')))
		.map((path) => relative(STYLE_ROOT, path));
}

describe('CSS ownership and foundation policy', () => {
	it.each([
		['.topbar', 'components/modules/topbar.css'],
		['.sidebar', 'components/modules/sidebar.css'],
		['.course-card', 'components/modules/course-card.css'],
		['.view-btn', 'components/modules/view-controls.css'],
		['.course-composer-layer', 'components/modules/course-composer.css'],
		['.popup-backdrop', 'components/modules/popup.css'],
		['.course-color-picker', 'components/modules/course-color-picker.css']
	])('keeps %s in one canonical stylesheet', (selector, owner) => {
		expect(ownersOf(selector)).toEqual([owner]);
	});

	it('uses an explicit local system font stack', () => {
		const tokens = readFileSync(join(STYLE_ROOT, 'foundation/tokens.css'), 'utf8');
		expect(tokens).toContain('--font-family-base: system-ui');
		expect(tokens).not.toContain("'Lato'");
	});

	it('loads the reduced-motion policy from the single global entrypoint', () => {
		const globalStyles = readFileSync(join(STYLE_ROOT, 'foundation/global.css'), 'utf8');
		const motion = readFileSync(join(STYLE_ROOT, 'foundation/motion.css'), 'utf8');
		expect(globalStyles.match(/@import '\.\/motion\.css';/g)).toHaveLength(1);
		expect(motion).toContain('@media (prefers-reduced-motion: reduce)');
	});
});
