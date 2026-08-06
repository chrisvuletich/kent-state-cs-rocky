import { json, type RequestHandler } from '@sveltejs/kit';

export const GET: RequestHandler = () => {
	const response = json(
		{
			ok: true,
			service: 'rocky-web'
		},
		{
			status: 200
		}
	);

	return response;
};
