import type { PageServerLoad } from './$types';

export const prerender = false;

export const load: PageServerLoad = async ({ fetch }) => {
	const response = await fetch('/api/server-health');
	const health = await response.json();

	return {
		health
	};
};
