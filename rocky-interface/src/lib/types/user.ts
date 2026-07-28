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

export type DbUser = {
	id: string;
	firstName: string;
	lastName: string;
	displayName: string;
	email: string;
	isAdmin: boolean;
	role: 'student' | 'instructor' | 'admin';
	isActive: boolean;
};



export type CreateUserInput = {
	firstName: string;
	lastName: string;
	email: string;
	isAdmin?: boolean;
	role?: 'student' | 'instructor' | 'admin';
	id?: string;
};

export type CreateUserPayload = {
	first_name: string;
	last_name: string;
	email: string;
	id: string;
	is_admin: boolean;
	role: 'student' | 'instructor' | 'admin';
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
		role: raw.role === 'admin' || raw.role === 'instructor' || raw.role === 'student' ? raw.role : (raw.is_admin ? 'admin' : 'student'),
		isAdmin: raw.role === 'admin' || (!raw.role && Boolean(raw.is_admin)),
		isActive: raw.is_active === undefined ? true : Boolean(raw.is_active)
	};
}

export function normalizeUsers(rawUsers: ApiUser[]): User[] {
	return rawUsers.map(normalizeUser);
}

export function normalizeDbUser(raw: ApiUser): DbUser {
	const firstName = raw.first_name?.trim() || '';
	const lastName = raw.last_name?.trim() || '';
	const displayName = `${firstName} ${lastName}`.trim() || 'N/A';

	return {
		id: raw.id?.trim() || '',
		firstName,
		lastName,
		displayName,
		email: raw.email?.trim() || 'N/A',
		isAdmin: Boolean(raw.is_admin),
		role: raw.role === 'admin' || raw.role === 'instructor' || raw.role === 'student' ? raw.role : (raw.is_admin ? 'admin' : 'student'),
		isActive: raw.is_active === undefined ? true : Boolean(raw.is_active)
	};
}

export function normalizeDbUsers(rawUsers: ApiUser[]): DbUser[] {
	return rawUsers.map(normalizeDbUser).filter((user) => user.id.length > 0);
}

export function toCreateUserPayload(input: CreateUserInput): CreateUserPayload {
	return {
		first_name: input.firstName.trim(),
		last_name: input.lastName.trim(),
		email: input.email.trim(),
		id: input.id?.trim() || 'test123',
		is_admin: input.role === 'admin' || (!input.role && Boolean(input.isAdmin)),
		role: input.role || (input.isAdmin ? 'admin' : 'student')
	};
}
