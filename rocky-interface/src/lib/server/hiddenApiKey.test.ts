import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { deriveHiddenApiKey, normalizeHiddenApiKeyOwner } from './hiddenApiKey';

type ContractVector = {
	case_id: string;
	owner_id: string;
	normalized_owner_id: string;
	secret: string;
	expected_api_key: string;
};

const contractPath = new URL(
	'../../../../run-test/fixtures/hidden_api_key_contract.json',
	import.meta.url
);
const vectors = JSON.parse(readFileSync(contractPath, 'utf8')) as ContractVector[];

describe('hidden API key contract', () => {
	for (const vector of vectors) {
		it(`matches shared vector ${vector.case_id}`, () => {
			const derived = deriveHiddenApiKey(vector.owner_id, vector.secret);
			const derivedFromNormalizedOwner = deriveHiddenApiKey(
				vector.normalized_owner_id,
				vector.secret
			);

			expect(normalizeHiddenApiKeyOwner(vector.owner_id)).toBe(vector.normalized_owner_id);
			expect(derived).toBe(vector.expected_api_key);
			expect(derivedFromNormalizedOwner).toBe(vector.expected_api_key);
			expect(derived.startsWith('sk_kent_hidden_')).toBe(true);
		});
	}
});
