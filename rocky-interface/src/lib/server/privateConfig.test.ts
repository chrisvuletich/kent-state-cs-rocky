import { describe, expect, it } from 'vitest';
import { requireProductionSecret } from './privateConfig';

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
