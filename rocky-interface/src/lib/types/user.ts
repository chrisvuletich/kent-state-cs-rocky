export type ApiUser = Partial<{
	first_name: string;
	last_name: string;
	email: string;
	id: string;
	api_key_owner_id: string;
	is_admin: boolean;
	is_active: boolean;
	role: 'student' | 'instructor' | 'admin';
}>;

export type User = {
	id: string;
	firstName: string;
	lastName: string;
	displayName: string;
	email: string;
	apiKeyOwnerId: string;
	isAdmin: boolean;
	role: 'student' | 'instructor' | 'admin';
	isActive: boolean;
};

export function normalizeUser(raw: ApiUser): User {
	const email = raw.email?.trim() || 'N/A';
	const firstName = raw.first_name?.trim() || '';
	const lastName = raw.last_name?.trim() || '';
	const displayName = `${firstName} ${lastName}`.trim() || 'N/A';
	const id = raw.id?.trim() || (email !== 'N/A' ? email.toLowerCase() : 'unknown');
	const apiKeyOwnerId = raw.api_key_owner_id?.trim().toLowerCase() || id.toLowerCase();

	return {
		id,
		firstName,
		lastName,
		displayName,
		email,
		apiKeyOwnerId,
		role:
			raw.role === 'admin' || raw.role === 'instructor' || raw.role === 'student'
				? raw.role
				: raw.is_admin
					? 'admin'
					: 'student',
		isAdmin: raw.role === 'admin' || (!raw.role && Boolean(raw.is_admin)),
		isActive: raw.is_active === undefined ? true : Boolean(raw.is_active)
	};
}

export function normalizeUsers(rawUsers: ApiUser[]): User[] {
	return rawUsers.map(normalizeUser);
}
