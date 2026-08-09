import { error, type RequestHandler } from '@sveltejs/kit';
import { API_BASE_URL } from '$lib/config/env';
import { internalProxyHeaders } from '$lib/server/backendSecurity';

function joinApiUrl(path: string, search: string): string {
	const normalizedPath = path.replace(/^\/+/, '');
	return `${API_BASE_URL}/${normalizedPath}${search}`;
}

async function forward(request: Request, locals: App.Locals, path: string): Promise<Response> {
	const headers = new Headers();
	headers.set('Accept', 'application/json');
	for (const [name, value] of Object.entries(internalProxyHeaders())) headers.set(name, value);

	const contentType = request.headers.get('content-type');
	if (contentType) {
		headers.set('Content-Type', contentType);
	}

	if (locals.currentUser) {
		headers.set('X-Rocky-User-Email', locals.currentUser.email);
		headers.set('X-Rocky-User-Is-Admin', String(locals.currentUser.isAdmin));
	}

	const init: RequestInit = {
		method: request.method,
		headers,
		cache: 'no-store'
	};

	if (request.method !== 'GET' && request.method !== 'HEAD') {
		init.body = await request.text();
	}

	const url = new URL(request.url);
	return fetch(joinApiUrl(path, url.search), init);
}

function ensureAuthorized(path: string, currentUser: App.Locals['currentUser']): void {
	if (path === 'auth/preview-users') {
		return;
	}

	if (!currentUser) {
		throw error(401, 'Not authenticated.');
	}

	if (!currentUser.isActive) {
		throw error(403, 'This account is inactive.');
	}
}

const passthrough: RequestHandler = async ({ params, request, locals }) => {
	const path = params.path;
	if (!path) {
		throw error(400, 'Missing backend path.');
	}

	ensureAuthorized(path, locals.currentUser);

	const backendResponse = await forward(request, locals, path);
	const headers = new Headers();
	for (const name of ['content-type', 'content-disposition', 'cache-control']) {
		const value = backendResponse.headers.get(name);
		if (value) headers.set(name, value);
	}
	return new Response(backendResponse.body, {
		status: backendResponse.status,
		headers
	});
};

export const GET = passthrough;
export const POST = passthrough;
export const PUT = passthrough;
export const PATCH = passthrough;
export const DELETE = passthrough;
