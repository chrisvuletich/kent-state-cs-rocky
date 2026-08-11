import { env } from '$env/dynamic/private';
import { APP_ENV } from '$lib/config/env';
import { requireProductionSecret } from '$lib/server/privateConfig';

export const INTERNAL_PROXY_HEADER = 'X-Rocky-Internal-Secret';

const configuredSecret = requireProductionSecret(
	'ROCKY_INTERNAL_PROXY_SECRET',
	env.ROCKY_INTERNAL_PROXY_SECRET ?? '',
	APP_ENV
);

export function internalProxyHeaders(): Record<string, string> {
	return configuredSecret ? { [INTERNAL_PROXY_HEADER]: configuredSecret } : {};
}
