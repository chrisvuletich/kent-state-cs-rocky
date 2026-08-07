import { browser } from '$app/environment';
import { MICROSOFT_OAUTH } from '$lib/config/env';

let clientPromise: Promise<any> | null = null;

export async function getMicrosoftAuthClient(): Promise<any> {
	if (!browser) throw new Error('Microsoft authentication is only available in the browser.');
	if (!clientPromise) {
		clientPromise = (async () => {
			const { PublicClientApplication } = await import('@azure/msal-browser');
			const client = new PublicClientApplication({
				auth: {
					clientId: MICROSOFT_OAUTH.clientId,
					authority: MICROSOFT_OAUTH.authority,
					redirectUri: new URL('/login', window.location.origin).toString()
				},
				cache: {
					cacheLocation: 'sessionStorage'
				}
			});
			await client.initialize();
			return client;
		})();
	}
	return clientPromise;
}

export async function clearMicrosoftAuthCache(): Promise<void> {
	const client = await getMicrosoftAuthClient();
	await client.clearCache();
}
