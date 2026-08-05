import { json, type RequestHandler } from '@sveltejs/kit';

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

const SERVICES: ServiceDefinition[] = [
	{
		name: 'backend',
		url: 'http://127.0.0.1:5001/health'
	},
	{
		name: 'granite',
		url: 'http://127.0.0.1:5002/health'
	},
	{
		name: 'chat-api',
		url: 'http://127.0.0.1:5003/health'
	},
	{
		name: 'ollama',
		url: 'http://granite.cs.kent.edu:11434/api/tags'
	}
];

export const GET: RequestHandler = async ({ fetch }) => {
	const checkedServices: ServiceHealth[] = await Promise.all(
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
			status: allHealthy ? 200 : 503
		}
	);
};
