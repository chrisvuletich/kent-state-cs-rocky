import { describe, expect, it } from 'vitest';
import { privateBoolean, requireProductionSecret } from './privateConfig';

describe('privateBoolean', () => {
	it('uses its fallback for missing values and accepts exact booleans', () => {
		expect(privateBoolean('ROCKY_TEST_FLAG', undefined, false)).toBe(false);
		expect(privateBoolean('ROCKY_TEST_FLAG', ' true ', false)).toBe(true);
		expect(privateBoolean('ROCKY_TEST_FLAG', 'false', true)).toBe(false);
	});

	it('rejects ambiguous values with the setting name', () => {
		expect(() => privateBoolean('ROCKY_TEST_FLAG', 'yes', false)).toThrow(
			/ROCKY_TEST_FLAG must be exactly true or false/
		);
	});
});

describe('requireProductionSecret', () => {
	it('preserves optional development values', () => {
		expect(requireProductionSecret('ROCKY_TEST_SECRET', '  local-secret  ', 'development')).toBe(
			'local-secret'
		);
	});

	it.each(['', 'short', 'replace-with-a-long-random-secret-value'])(
		'rejects an unsafe production value: %s',
		(value) => {
			expect(() => requireProductionSecret('ROCKY_TEST_SECRET', value, 'production')).toThrow(
				/ROCKY_TEST_SECRET.*32 characters/
			);
		}
	);

	it('accepts a strong production value', () => {
		const value = 'a-synthetic-production-secret-value-12345';
		expect(requireProductionSecret('ROCKY_TEST_SECRET', value, 'production')).toBe(value);
	});
});
