export type ApiAccountProfile = Partial<{
	username: string;
	email: string;
	role: string;
}>;

export type AccountProfile = {
	username: string;
	email: string;
	role: string;
};

export function normalizeAccountProfile(raw: ApiAccountProfile): AccountProfile {
	return {
		username: raw.username?.trim() || 'N/A',
		email: raw.email?.trim() || 'N/A',
		role: raw.role?.trim() || 'N/A'
	};
}
