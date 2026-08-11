import { dev } from '$app/environment';
import { env } from '$env/dynamic/public';

const PUBLIC_APP_ENV = (env.PUBLIC_APP_ENV ?? (dev ? 'development' : 'production')).toString();
const PUBLIC_API_BASE_URL = (env.PUBLIC_API_BASE_URL ?? 'http://localhost:5001').toString();
const PUBLIC_ENABLE_DBTEST = (env.PUBLIC_ENABLE_DBTEST ?? 'false').toString();
const PUBLIC_ENABLE_MICROSOFT_OAUTH = (env.PUBLIC_ENABLE_MICROSOFT_OAUTH ?? 'false').toString();
const PUBLIC_MICROSOFT_CLIENT_ID = (env.PUBLIC_MICROSOFT_CLIENT_ID ?? '').toString();
const PUBLIC_MICROSOFT_TENANT_ID = (env.PUBLIC_MICROSOFT_TENANT_ID ?? '').toString();

const trimTrailingSlash = (value: string) => value.replace(/\/+$/, '');

function requirePublicEnv(name: string, value: string): string {
	const normalized = value.trim();
	if (!normalized) {
		throw new Error(`Missing required public environment variable: ${name}`);
	}
	return normalized;
}

function parseBooleanEnv(name: string, value: string): boolean {
	if (value === 'true') {
		return true;
	}
	if (value === 'false') {
		return false;
	}
	throw new Error(`Invalid ${name}: "${value}". Expected "true" or "false".`);
}

function parseAppEnv(value: string): 'development' | 'testing' | 'production' {
	if (value === 'development' || value === 'testing' || value === 'production') {
		return value;
	}
	throw new Error(
		`Invalid PUBLIC_APP_ENV: "${value}". Expected one of: development, testing, production.`
	);
}

export function parseApiBaseUrl(value: string): string {
	let parsed: URL;
	try {
		parsed = new URL(value);
	} catch {
		throw new Error(`Invalid PUBLIC_API_BASE_URL: "${value}". Expected a valid absolute URL.`);
	}

	if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
		throw new Error(
			`Invalid PUBLIC_API_BASE_URL protocol: "${parsed.protocol}". Expected http or https.`
		);
	}
	if (!parsed.hostname || parsed.username || parsed.password) {
		throw new Error(
			`Invalid PUBLIC_API_BASE_URL: "${value}". Expected an absolute URL without credentials.`
		);
	}
	if (parsed.search || parsed.hash) {
		throw new Error(
			`Invalid PUBLIC_API_BASE_URL: "${value}". Query strings and fragments are not allowed.`
		);
	}

	return trimTrailingSlash(parsed.toString());
}

export const APP_ENV = parseAppEnv(requirePublicEnv('PUBLIC_APP_ENV', PUBLIC_APP_ENV));
export const API_BASE_URL = parseApiBaseUrl(
	requirePublicEnv('PUBLIC_API_BASE_URL', PUBLIC_API_BASE_URL)
);
export const ENABLE_DBTEST = parseBooleanEnv(
	'PUBLIC_ENABLE_DBTEST',
	requirePublicEnv('PUBLIC_ENABLE_DBTEST', PUBLIC_ENABLE_DBTEST)
);

export type AuthMode = 'preview' | 'microsoft';

function resolveAuthMode(
	appEnv: 'development' | 'testing' | 'production',
	microsoftEnabledOverride: boolean
): AuthMode {
	if (appEnv === 'production') {
		return 'microsoft';
	}

	if (appEnv === 'testing') {
		return 'preview';
	}

	return microsoftEnabledOverride ? 'microsoft' : 'preview';
}

const microsoftEnabledOverride = parseBooleanEnv(
	'PUBLIC_ENABLE_MICROSOFT_OAUTH',
	requirePublicEnv('PUBLIC_ENABLE_MICROSOFT_OAUTH', PUBLIC_ENABLE_MICROSOFT_OAUTH)
);

export const AUTH_MODE = resolveAuthMode(APP_ENV, microsoftEnabledOverride);
export const ENABLE_MICROSOFT_OAUTH = AUTH_MODE === 'microsoft';
export const ENABLE_PREVIEW_AUTH = AUTH_MODE === 'preview';

const MICROSOFT_TENANT_ID = PUBLIC_MICROSOFT_TENANT_ID.trim();

export const MICROSOFT_OAUTH = {
	clientId: PUBLIC_MICROSOFT_CLIENT_ID.trim(),
	tenantId: MICROSOFT_TENANT_ID,
	authority: `https://login.microsoftonline.com/${MICROSOFT_TENANT_ID}`
};

if (ENABLE_MICROSOFT_OAUTH && !MICROSOFT_OAUTH.clientId) {
	throw new Error('Missing required public environment variable: PUBLIC_MICROSOFT_CLIENT_ID');
}
if (
	ENABLE_MICROSOFT_OAUTH &&
	(!MICROSOFT_OAUTH.tenantId ||
		['common', 'organizations', 'consumers'].includes(MICROSOFT_OAUTH.tenantId))
) {
	throw new Error(
		'PUBLIC_MICROSOFT_TENANT_ID must be the specific Kent tenant ID when Microsoft OAuth is active.'
	);
}
