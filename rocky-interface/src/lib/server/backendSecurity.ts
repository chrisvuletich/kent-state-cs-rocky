import { env } from '$env/dynamic/private';
import { APP_ENV } from '$lib/config/env';

export const INTERNAL_PROXY_HEADER = 'X-Rocky-Internal-Secret';

const configuredSecret = (env.ROCKY_INTERNAL_PROXY_SECRET ?? '').trim();

if (APP_ENV === 'production' && !configuredSecret) {
	throw new Error('Missing required private environment variable: ROCKY_INTERNAL_PROXY_SECRET');
}
if (APP_ENV === 'production' && configuredSecret.length < 32) {
	throw new Error('ROCKY_INTERNAL_PROXY_SECRET must contain at least 32 characters in production.');
}

export function internalProxyHeaders(): Record<string, string> {
	return configuredSecret ? { [INTERNAL_PROXY_HEADER]: configuredSecret } : {};
}
