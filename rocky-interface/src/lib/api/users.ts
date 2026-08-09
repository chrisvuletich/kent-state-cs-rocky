import {
	normalizeDbUsers,
	normalizeUsers,
	type ApiUser,
	type DbUser,
	type User,
	type CreateUserInput,
	toCreateUserPayload
} from '$lib/types/user';
import { showErrorFeedback, showSuccessFeedback } from '$lib/stores/feedbackStore';

const USER_SAFE_ACTION_FAILURE = 'Action failed. Please try again.';
const USER_SAFE_NETWORK_FAILURE = 'Unable to reach the server. Please try again.';

export type ApiWhitelistEntry = Partial<{
	first_name: string;
	last_name: string;
	email: string;
	id: string;
	is_admin: boolean;
	is_active: boolean;
	role: 'student' | 'instructor' | 'admin';
	created_at: string;
}>;

export type WhitelistEntry = {
	id: string;
	firstName: string;
	lastName: string;
	displayName: string;
	email: string;
	isAdmin: boolean;
	role: 'student' | 'instructor' | 'admin';
	isActive: boolean;
	createdAt: string;
};

export type CreateWhitelistEntryInput = {
	firstName: string;
	lastName: string;
	email: string;
	role: 'student' | 'instructor' | 'admin';
};

function normalizeWhitelistEntry(raw: ApiWhitelistEntry): WhitelistEntry {
	const firstName = raw.first_name?.trim() || '';
	const lastName = raw.last_name?.trim() || '';
	const displayName = `${firstName} ${lastName}`.trim() || 'N/A';
	const id = raw.id?.trim() || '';

	return {
		id,
		firstName,
		lastName,
		displayName,
		email: raw.email?.trim() || 'N/A',
		role:
			raw.role === 'admin' || raw.role === 'instructor' || raw.role === 'student'
				? raw.role
				: raw.is_admin
					? 'admin'
					: 'student',
		isAdmin: raw.role === 'admin' || (!raw.role && Boolean(raw.is_admin)),
		isActive: raw.is_active === undefined ? true : Boolean(raw.is_active),
		createdAt: raw.created_at?.trim() || ''
	};
}

async function fetchJson<T>(url: string): Promise<T> {
	let response: Response;
	try {
		response = await fetch(url);
	} catch (err) {
		console.error('[users api] network request failed', { url, err });
		throw new Error(USER_SAFE_NETWORK_FAILURE);
	}

	if (!response.ok) {
		const body = await response.text();
		console.error('[users api] request failed', { url, status: response.status, raw: body });
		throw new Error(USER_SAFE_ACTION_FAILURE);
	}
	return (await response.json()) as T;
}

function getErrorMessage(err: unknown, fallback: string): string {
	return err instanceof Error && err.message.trim() ? err.message : fallback;
}

export async function fetchUsersForViews(): Promise<User[]> {
	const url = '/api/backend/users';
	const rawUsers = await fetchJson<ApiUser[]>(url);
	return normalizeUsers(rawUsers);
}

export async function fetchUsersForDbTest(): Promise<DbUser[]> {
	const url = '/api/backend/users';
	const rawUsers = await fetchJson<ApiUser[]>(url);
	return normalizeDbUsers(rawUsers);
}

export async function createUser(input: CreateUserInput): Promise<void> {
	try {
		const response = await fetch('/api/backend/users', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify(toCreateUserPayload(input))
		});

		if (!response.ok) {
			throw new Error(`Failed to create user (${response.status}).`);
		}

		showSuccessFeedback('User created successfully.');
	} catch (err) {
		const message = getErrorMessage(err, 'Unable to create user.');
		showErrorFeedback(message);
		throw err;
	}
}

export async function setUserActive(id: string, isActive: boolean): Promise<void> {
	await updateUser(id, { is_active: isActive });
	showSuccessFeedback(isActive ? 'User activated successfully.' : 'User deactivated successfully.');
}

export async function setUserRole(
	id: string,
	role: 'student' | 'instructor' | 'admin'
): Promise<void> {
	await updateUser(id, { role });
	showSuccessFeedback(`Account role changed to ${role}.`);
}

async function updateUser(
	id: string,
	changes: { is_active?: boolean; is_admin?: boolean; role?: 'student' | 'instructor' | 'admin' }
): Promise<void> {
	try {
		const response = await fetch(`/api/backend/users/${id}`, {
			method: 'PUT',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify(changes)
		});

		if (!response.ok) {
			const payload = (await response.json().catch(() => ({ error: '' }))) as { error?: string };
			throw new Error(payload.error || `Failed to update user status (${response.status}).`);
		}
	} catch (err) {
		const message = getErrorMessage(err, 'Unable to update user status.');
		showErrorFeedback(message);
		throw err;
	}
}

export async function setUsersActive(
	ids: string[],
	isActive: boolean
): Promise<{ updatedIds: string[]; missingIds: string[] }> {
	try {
		const response = await fetch('/api/backend/users/bulk-status', {
			method: 'PATCH',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ user_ids: ids, is_active: isActive })
		});
		const payload = (await response.json().catch(() => ({}))) as {
			updated_ids?: string[];
			missing_ids?: string[];
			error?: string;
		};
		if (!response.ok) {
			throw new Error(payload.error || `Failed to update users (${response.status}).`);
		}
		const updatedIds = payload.updated_ids || [];
		const missingIds = payload.missing_ids || [];
		showSuccessFeedback(
			`${updatedIds.length} user${updatedIds.length === 1 ? '' : 's'} ${isActive ? 'activated' : 'deactivated'}.`
		);
		return { updatedIds, missingIds };
	} catch (err) {
		const message = getErrorMessage(err, 'Unable to update selected users.');
		showErrorFeedback(message);
		throw err;
	}
}

export async function fetchOAuthWhitelistEntries(): Promise<WhitelistEntry[]> {
	const url = '/api/backend/auth/microsoft/whitelist';
	const rawEntries = await fetchJson<ApiWhitelistEntry[]>(url);
	return rawEntries.map(normalizeWhitelistEntry).filter((entry) => entry.id.length > 0);
}

export async function createOAuthWhitelistEntry(input: CreateWhitelistEntryInput): Promise<void> {
	try {
		const response = await fetch('/api/backend/auth/microsoft/whitelist', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				firstName: input.firstName.trim(),
				lastName: input.lastName.trim(),
				email: input.email.trim(),
				role: input.role
			})
		});

		if (!response.ok) {
			const payload = (await response.json().catch(() => ({ error: '' }))) as { error?: string };
			throw new Error(payload.error || `Failed to add whitelist entry (${response.status}).`);
		}

		showSuccessFeedback('Whitelist entry added successfully.');
	} catch (err) {
		const message = getErrorMessage(err, 'Unable to add whitelist entry.');
		showErrorFeedback(message);
		throw err;
	}
}

export async function setWhitelistUserActive(id: string, isActive: boolean): Promise<void> {
	await updateWhitelistEntry(id, { is_active: isActive });
	showSuccessFeedback(
		isActive ? 'Whitelist user activated successfully.' : 'Whitelist user deactivated successfully.'
	);
}

export async function setWhitelistUserRole(
	id: string,
	role: 'student' | 'instructor' | 'admin'
): Promise<void> {
	await updateWhitelistEntry(id, { role });
	showSuccessFeedback(`Whitelist account role changed to ${role}.`);
}

async function updateWhitelistEntry(
	id: string,
	changes: { is_active?: boolean; role?: 'student' | 'instructor' | 'admin' }
): Promise<void> {
	try {
		const response = await fetch(`/api/backend/auth/microsoft/whitelist/${id}`, {
			method: 'PATCH',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify(changes)
		});

		if (!response.ok) {
			const payload = (await response.json().catch(() => ({ error: '' }))) as { error?: string };
			throw new Error(
				payload.error || `Failed to update whitelist user status (${response.status}).`
			);
		}
	} catch (err) {
		const message = getErrorMessage(err, 'Unable to update whitelist account.');
		showErrorFeedback(message);
		throw err;
	}
}
