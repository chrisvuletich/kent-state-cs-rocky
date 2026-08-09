import type { LayoutServerLoad } from './$types';

export const load: LayoutServerLoad = async ({ locals, url }) => {
	const requestedDocumentation = url.searchParams.get('doc')?.trim();

	return {
		currentUser: locals.currentUser,
		themePreference: locals.themePreference,
		userSettings: locals.userSettings,
		initialFrame: requestedDocumentation ? 'help' : locals.initialFrame
	};
};
