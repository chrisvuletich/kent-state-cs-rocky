import { sveltekit } from '@sveltejs/kit/vite';
import { loadEnv } from 'vite';
import { defineConfig } from 'vitest/config';

export default defineConfig(({ mode }) => {
	const env = loadEnv(mode, '.', '');
	const baseConfig = {
		plugins: [sveltekit()],
		optimizeDeps: {
			exclude: ['@azure/msal-browser']
		},
		test: {
			coverage: {
				provider: 'v8' as const,
				include: ['src/**/*.{ts,svelte}'],
				exclude: ['src/**/*.test.ts', 'src/**/*.spec.ts', 'src/**/*.d.ts'],
				reporter: ['text-summary', 'json-summary'],
				reportsDirectory: 'coverage',
				reportOnFailure: true,
				skipFull: true,
				thresholds: {
					statements: 14,
					branches: 16,
					functions: 13,
					lines: 15
				}
			}
		}
	};

	if (mode === 'test') {
		return baseConfig;
	}

	if (mode === 'production') {
		return baseConfig;
	}

	const host = env.ROCKY_WEB_HOST?.trim();
	if (!host) {
		throw new Error('Missing required env var: ROCKY_WEB_HOST');
	}

	const rawPort = env.ROCKY_WEB_PORT?.trim();
	if (!rawPort) {
		throw new Error('Missing required env var: ROCKY_WEB_PORT');
	}

	const port = Number(rawPort);
	if (!Number.isInteger(port) || port < 1 || port > 65535) {
		throw new Error(
			`Invalid ROCKY_WEB_PORT: "${rawPort}". Expected an integer between 1 and 65535.`
		);
	}

	const rawAllowedHosts = env.ROCKY_ALLOWED_HOSTS?.trim();
	if (!rawAllowedHosts) {
		throw new Error('Missing required env var: ROCKY_ALLOWED_HOSTS');
	}

	const allowedHosts = rawAllowedHosts
		.split(',')
		.map((entry) => entry.trim())
		.filter((entry) => entry.length > 0);

	if (allowedHosts.length === 0) {
		throw new Error(
			'Invalid ROCKY_ALLOWED_HOSTS: provide at least one host, e.g. "localhost,127.0.0.1".'
		);
	}

	return {
		...baseConfig,
		server: {
			allowedHosts,
			host,
			port
		}
	};
});
