import { describe, expect, it } from 'vitest';

import { normalizeUser, normalizeUsers } from './user';

describe('user normalization', () => {
	it('normalizes a complete API user', () => {
		expect(
			normalizeUser({
				id: ' KSUID0001 ',
				first_name: ' Grace ',
				last_name: ' Hopper ',
				email: ' grace@example.edu ',
				api_key_owner_id: ' OWNER-A ',
				role: 'instructor',
				is_admin: true,
				is_active: false
			})
		).toEqual({
			id: 'KSUID0001',
			firstName: 'Grace',
			lastName: 'Hopper',
			displayName: 'Grace Hopper',
			email: 'grace@example.edu',
			apiKeyOwnerId: 'owner-a',
			role: 'instructor',
			isAdmin: false,
			isActive: false
		});
	});

	it('derives missing identifiers, roles, names, and active state safely', () => {
		expect(normalizeUser({ email: ' Student@Example.edu ' })).toEqual({
			id: 'student@example.edu',
			firstName: '',
			lastName: '',
			displayName: 'N/A',
			email: 'Student@Example.edu',
			apiKeyOwnerId: 'student@example.edu',
			role: 'student',
			isAdmin: false,
			isActive: true
		});

		expect(normalizeUser({ is_admin: true })).toMatchObject({
			id: 'unknown',
			apiKeyOwnerId: 'unknown',
			role: 'admin',
			isAdmin: true,
			isActive: true
		});
	});

	it('normalizes user collections', () => {
		const users = normalizeUsers([
			{ id: 'one', role: 'student' },
			{ id: 'two', role: 'admin' }
		]);

		expect(users.map((user) => user.id)).toEqual(['one', 'two']);
		expect(users.map((user) => user.isAdmin)).toEqual([false, true]);
	});
});
