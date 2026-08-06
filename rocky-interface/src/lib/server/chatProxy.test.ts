import { afterEach, describe, expect, it, vi } from 'vitest';

type ChatUser = NonNullable<App.Locals['currentUser']>;
type PrivateEnvironment = Record<string, string | undefined>;

const SYNTHETIC_DERIVED_KEY = 'synthetic-derived-hidden-key';

function syntheticUser(overrides: Partial<ChatUser> = {}): ChatUser {
	return {
		id: 'synthetic-user-id',
		firstName: 'Synthetic',
		lastName: 'Student',
		displayName: 'Synthetic Student',
		email: 'synthetic.user@example.invalid',
		apiKeyOwnerId: 'synthetic-owner-id',
		isAdmin: false,
		role: 'student',
		isActive: true,
		...overrides
	};
}

async function loadChatProxy(
	privateEnvironment: PrivateEnvironment,
	derivedKey = SYNTHETIC_DERIVED_KEY
) {
	vi.resetModules();
	const deriveHiddenApiKey = vi.fn(() => derivedKey);

	vi.doMock('$env/dynamic/private', () => ({ env: privateEnvironment }));
	vi.doMock('$lib/server/hiddenApiKey', () => ({ deriveHiddenApiKey }));

	const { chatRequestHeaders, hiddenApiKeyForUser } = await import('./chatProxy');
	return { chatRequestHeaders, deriveHiddenApiKey, hiddenApiKeyForUser };
}

function expectServerError(call: () => unknown, message: string) {
	try {
		call();
	} catch (error) {
		expect(error).toMatchObject({ status: 500, body: { message } });
		return;
	}
	throw new Error('Expected hiddenApiKeyForUser to throw a server error.');
}

afterEach(() => {
	vi.clearAllMocks();
	vi.resetModules();
	vi.doUnmock('$env/dynamic/private');
	vi.doUnmock('$lib/server/hiddenApiKey');
});

describe('hiddenApiKeyForUser', () => {
	it('prefers apiKeyOwnerId when it is present', async () => {
		const { deriveHiddenApiKey, hiddenApiKeyForUser } = await loadChatProxy({
			ROCKY_HIDDEN_API_KEY_SECRET: ' synthetic-primary-secret ',
			ROCKY_CHAT_API_KEY: 'synthetic-fallback-secret'
		});
		const user = syntheticUser({
			apiKeyOwnerId: ' Synthetic-Preferred-Owner ',
			id: 'synthetic-fallback-owner'
		});

		expect(hiddenApiKeyForUser(user)).toBe(SYNTHETIC_DERIVED_KEY);
		expect(deriveHiddenApiKey).toHaveBeenCalledWith(
			'synthetic-preferred-owner',
			'synthetic-primary-secret'
		);
	});

	it('uses user.id when apiKeyOwnerId is absent', async () => {
		const { deriveHiddenApiKey, hiddenApiKeyForUser } = await loadChatProxy({
			ROCKY_CHAT_API_KEY: ' synthetic-fallback-secret '
		});
		const user = syntheticUser({
			apiKeyOwnerId: '',
			id: ' Synthetic-User-Fallback '
		});

		expect(hiddenApiKeyForUser(user)).toBe(SYNTHETIC_DERIVED_KEY);
		expect(deriveHiddenApiKey).toHaveBeenCalledWith(
			'synthetic-user-fallback',
			'synthetic-fallback-secret'
		);
	});

	it('rejects a whitespace-only selected owner after normalization', async () => {
		const { deriveHiddenApiKey, hiddenApiKeyForUser } = await loadChatProxy({
			ROCKY_HIDDEN_API_KEY_SECRET: 'synthetic-primary-secret'
		});
		const user = syntheticUser({
			apiKeyOwnerId: '   ',
			id: 'synthetic-valid-fallback'
		});

		expectServerError(
			() => hiddenApiKeyForUser(user),
			'Unable to resolve chat API key owner.'
		);
		expect(deriveHiddenApiKey).not.toHaveBeenCalled();
	});

	it('rejects a missing configured secret', async () => {
		const { deriveHiddenApiKey, hiddenApiKeyForUser } = await loadChatProxy({});
		const user = syntheticUser();

		expectServerError(
			() => hiddenApiKeyForUser(user),
			'Hidden chat API key secret is not configured.'
		);
		expect(deriveHiddenApiKey).not.toHaveBeenCalled();
	});

	it('returns the result from deriveHiddenApiKey', async () => {
		const syntheticHelperResult = 'synthetic-helper-result';
		const { deriveHiddenApiKey, hiddenApiKeyForUser } = await loadChatProxy(
			{ ROCKY_HIDDEN_API_KEY_SECRET: 'synthetic-primary-secret' },
			syntheticHelperResult
		);
		const user = syntheticUser();

		expect(hiddenApiKeyForUser(user)).toBe(syntheticHelperResult);
		expect(deriveHiddenApiKey).toHaveBeenCalledOnce();
	});

	it('sends the derived key as a Bearer credential', async () => {
		const { chatRequestHeaders } = await loadChatProxy({
			ROCKY_HIDDEN_API_KEY_SECRET: 'synthetic-primary-secret'
		});
		const user = syntheticUser();

		expect(chatRequestHeaders(user)).toMatchObject({
			Authorization: `Bearer ${SYNTHETIC_DERIVED_KEY}`,
			'X-Rocky-User-Id': user.id,
			'X-Rocky-User-Email': user.email
		});
	});
});
