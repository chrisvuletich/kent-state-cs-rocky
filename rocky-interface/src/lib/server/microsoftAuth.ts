import { createPublicKey, verify as verifySignature, type JsonWebKey } from 'node:crypto';
import { MICROSOFT_OAUTH } from '$lib/config/env';

const CLOCK_SKEW_SECONDS = 60;
const JWKS_CACHE_MILLISECONDS = 60 * 60 * 1000;

type JwtHeader = { alg?: unknown; kid?: unknown };
type JwtClaims = Record<string, unknown> & {
	aud?: unknown;
	exp?: unknown;
	iss?: unknown;
	nbf?: unknown;
	tid?: unknown;
};
type MicrosoftJwk = JsonWebKey & { kid?: string; use?: string };

let cachedKeys: MicrosoftJwk[] = [];
let keysExpireAt = 0;

function decodeSegment<T>(segment: string): T {
	return JSON.parse(Buffer.from(segment, 'base64url').toString('utf8')) as T;
}

async function signingKey(kid: string): Promise<MicrosoftJwk> {
	if (Date.now() >= keysExpireAt || !cachedKeys.some((key) => key.kid === kid)) {
		const response = await fetch(
			`https://login.microsoftonline.com/${encodeURIComponent(MICROSOFT_OAUTH.tenantId)}/discovery/v2.0/keys`,
			{ headers: { Accept: 'application/json' }, signal: AbortSignal.timeout(5_000) }
		);
		if (!response.ok) throw new Error('Microsoft signing keys are unavailable.');
		const payload = (await response.json()) as { keys?: unknown };
		if (!Array.isArray(payload.keys)) throw new Error('Microsoft signing keys are invalid.');
		cachedKeys = payload.keys.filter((key): key is MicrosoftJwk => Boolean(key && typeof key === 'object'));
		keysExpireAt = Date.now() + JWKS_CACHE_MILLISECONDS;
	}
	const key = cachedKeys.find((candidate) => candidate.kid === kid && candidate.use !== 'enc');
	if (!key) throw new Error('Microsoft token signing key was not found.');
	return key;
}

function claim(claims: JwtClaims, ...names: string[]): string {
	for (const name of names) {
		const value = claims[name];
		if (typeof value === 'string' && value.trim()) return value.trim();
	}
	return '';
}

export async function verifyMicrosoftIdToken(token: string): Promise<{
	email: string;
	firstName: string;
	lastName: string;
	id: string;
}> {
	const normalizedToken = token.trim();
	const [encodedHeader, encodedClaims, encodedSignature, ...extra] = normalizedToken.split('.');
	if (!encodedHeader || !encodedClaims || !encodedSignature || extra.length > 0) {
		throw new Error('Microsoft returned an invalid identity token.');
	}

	let header: JwtHeader;
	let claims: JwtClaims;
	try {
		header = decodeSegment<JwtHeader>(encodedHeader);
		claims = decodeSegment<JwtClaims>(encodedClaims);
	} catch {
		throw new Error('Microsoft returned an invalid identity token.');
	}
	if (header.alg !== 'RS256' || typeof header.kid !== 'string' || !header.kid) {
		throw new Error('Microsoft returned an unsupported identity token.');
	}

	const key = await signingKey(header.kid);
	const publicKey = createPublicKey({ key, format: 'jwk' });
	const verified = verifySignature(
		'RSA-SHA256',
		Buffer.from(`${encodedHeader}.${encodedClaims}`),
		publicKey,
		Buffer.from(encodedSignature, 'base64url')
	);
	if (!verified) throw new Error('Microsoft identity token verification failed.');

	const now = Math.floor(Date.now() / 1000);
	const expectedIssuer = `https://login.microsoftonline.com/${MICROSOFT_OAUTH.tenantId}/v2.0`.toLowerCase();
	const clientId = MICROSOFT_OAUTH.clientId.toLowerCase();
	const audienceValid = typeof claims.aud === 'string'
		? claims.aud.toLowerCase() === clientId
		: Array.isArray(claims.aud) && claims.aud.some((value) => typeof value === 'string' && value.toLowerCase() === clientId);
	if (!audienceValid || String(claims.iss || '').toLowerCase() !== expectedIssuer || String(claims.tid || '').toLowerCase() !== MICROSOFT_OAUTH.tenantId.toLowerCase()) {
		throw new Error('Microsoft identity token is not for this Rocky application.');
	}
	if (typeof claims.exp !== 'number' || claims.exp <= now - CLOCK_SKEW_SECONDS) {
		throw new Error('Microsoft identity token has expired.');
	}
	if (typeof claims.nbf === 'number' && claims.nbf > now + CLOCK_SKEW_SECONDS) {
		throw new Error('Microsoft identity token is not active yet.');
	}

	const email = claim(claims, 'preferred_username', 'email', 'upn', 'unique_name').toLowerCase();
	if (!email) throw new Error('Microsoft identity token has no usable email claim.');
	const displayName = claim(claims, 'name');
	const nameParts = displayName.split(/\s+/).filter(Boolean);
	return {
		email,
		firstName: claim(claims, 'given_name') || nameParts[0] || email.split('@')[0],
		lastName: claim(claims, 'family_name') || nameParts.slice(1).join(' '),
		id: claim(claims, 'oid', 'sub')
	};
}
