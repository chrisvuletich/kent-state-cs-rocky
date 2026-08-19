import { json, type RequestHandler } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';

type ServiceName = 'web' | 'backend' | 'granite' | 'chat-api' | 'ollama';

type ServiceHealth = {
	name: ServiceName;
	ok: boolean;
	latencyMs: number;
};

type ServiceDefinition = {
	name: Exclude<ServiceName, 'web'>;
	url: string;
};

type CachedHealth = {
	expiresAt: number;
	services: ServiceHealth[];
};

const HEALTH_CACHE_TTL_MS = 5_000;
let cachedHealth: CachedHealth | null = null;
let healthCheckInFlight: Promise<ServiceHealth[]> | null = null;

const SERVICES: ServiceDefinition[] = [
	{
		name: 'backend',
		url: env.ROCKY_BACKEND_HEALTH_URL?.trim() || 'http://127.0.0.1:5001/health'
	},
	{
		name: 'granite',
		url: env.ROCKY_GRANITE_HEALTH_URL?.trim() || 'http://127.0.0.1:5002/health'
	},
	{
		name: 'chat-api',
		url: env.ROCKY_CHAT_API_HEALTH_URL?.trim() || 'http://127.0.0.1:5003/health'
	},
	{
		name: 'ollama',
		url: env.ROCKY_OLLAMA_HEALTH_URL?.trim() || 'http://granite.cs.kent.edu:11434/api/tags'
	}
];

async function probeServices(fetch: typeof globalThis.fetch): Promise<ServiceHealth[]> {
	return Promise.all(
		SERVICES.map(async (service) => {
			const startedAt = Date.now();

			try {
				const serviceResponse = await fetch(service.url, {
					signal: AbortSignal.timeout(3000)
				});

				return {
					name: service.name,
					ok: serviceResponse.ok,
					latencyMs: Date.now() - startedAt
				};
			} catch {
				return {
					name: service.name,
					ok: false,
					latencyMs: Date.now() - startedAt
				};
			}
		})
	);
}

async function getCheckedServices(
	fetch: typeof globalThis.fetch,
	forceRefresh: boolean
): Promise<ServiceHealth[]> {
	const now = Date.now();
	if (!forceRefresh && cachedHealth && cachedHealth.expiresAt > now) {
		return cachedHealth.services;
	}

	if (!healthCheckInFlight) {
		healthCheckInFlight = probeServices(fetch).then((services) => {
			cachedHealth = {
				expiresAt: Date.now() + HEALTH_CACHE_TTL_MS,
				services
			};
			return services;
		});
	}

	try {
		return await healthCheckInFlight;
	} finally {
		healthCheckInFlight = null;
	}
}

export const GET: RequestHandler = async ({ fetch, url }) => {
	const checkedServices = await getCheckedServices(fetch, url.searchParams.get('refresh') === '1');

	const services: ServiceHealth[] = [
		{
			name: 'web',
			ok: true,
			latencyMs: 0
		},
		...checkedServices
	];

	const allHealthy = services.every((service) => service.ok);

	return json(
		{
			ok: allHealthy,
			services
		},
		{
			status: allHealthy ? 200 : 503,
			headers: { 'Cache-Control': 'no-store' }
		}
	);
};
