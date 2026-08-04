import { createHmac } from 'node:crypto';

export const HIDDEN_API_KEY_PREFIX = 'sk_kent_hidden_';
export const HIDDEN_API_KEY_CONTEXT = 'rocky:user-default-api-key:v1:';


export function normalizeHiddenApiKeyOwner(ownerId: string): string {
	return ownerId.trim().toLowerCase()
}

export function deriveHiddenApiKey(ownerId: string, secret: string): string {
	const normalizedOwnerId = normalizeHiddenApiKeyOwner(ownerId)

	const digest = createHmac('sha256', secret.trim())
		.update(`${HIDDEN_API_KEY_CONTEXT}${normalizedOwnerId}`).digest('hex');
	
	return `${HIDDEN_API_KEY_PREFIX}${digest}`;
}
