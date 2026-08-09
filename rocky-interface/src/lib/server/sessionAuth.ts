import { createHmac, timingSafeEqual } from 'node:crypto';
import { env } from '$env/dynamic/private';
import { APP_ENV } from '$lib/config/env';

const SESSION_VERSION = 1;
const SESSION_LIFETIME_SECONDS = 60 * 60 * 8;
const configuredSecret = (env.ROCKY_SESSION_SECRET ?? '').trim();
const sessionSecret =
	configuredSecret || (APP_ENV === 'production' ? '' : 'rocky-local-development-session');

if (!sessionSecret) {
	throw new Error('Missing required private environment variable: ROCKY_SESSION_SECRET');
}
if (APP_ENV === 'production' && sessionSecret.length < 32) {
	throw new Error('ROCKY_SESSION_SECRET must contain at least 32 characters in production.');
}

type SessionPayload = {
	v: number;
	email: string;
	exp: number;
};

function signature(payload: string): string {
	return createHmac('sha256', sessionSecret).update(payload).digest('base64url');
}

export function createSessionToken(email: string): string {
	const normalizedEmail = email.trim().toLowerCase();
	if (!normalizedEmail) throw new Error('A session email is required.');
	const payload = Buffer.from(
		JSON.stringify({
			v: SESSION_VERSION,
			email: normalizedEmail,
			exp: Math.floor(Date.now() / 1000) + SESSION_LIFETIME_SECONDS
		} satisfies SessionPayload)
	).toString('base64url');
	return `${payload}.${signature(payload)}`;
}

export function readSessionEmail(token: string | undefined): string | null {
	if (!token) return null;
	const [payload, providedSignature, ...extra] = token.split('.');
	if (!payload || !providedSignature || extra.length > 0) return null;

	const expected = Buffer.from(signature(payload));
	const provided = Buffer.from(providedSignature);
	if (expected.length !== provided.length || !timingSafeEqual(expected, provided)) return null;

	try {
		const parsed = JSON.parse(
			Buffer.from(payload, 'base64url').toString('utf8')
		) as Partial<SessionPayload>;
		const email = typeof parsed.email === 'string' ? parsed.email.trim().toLowerCase() : '';
		if (parsed.v !== SESSION_VERSION || !email || typeof parsed.exp !== 'number') return null;
		if (parsed.exp <= Math.floor(Date.now() / 1000)) return null;
		return email;
	} catch {
		return null;
	}
}
