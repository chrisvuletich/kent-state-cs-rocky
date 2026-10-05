import { afterEach, describe, expect, it, vi } from 'vitest';

import {
	addGroupMembers,
	fetchCourseApiHistory,
	joinCourseGroup,
	updateCourseGroup,
	deleteCourseGroup,
	removeGroupMember,
	updateGroupJoinSettings
} from './courses';

afterEach(() => {
	vi.unstubAllGlobals();
});

describe('group management', () => {
	it('returns the saved membership after removal without a second fetch', async () => {
		const result = { id: 1, groups: [{ id: 'group-a', memberIds: [] }] };
		const fetchMock = vi
			.fn()
			.mockResolvedValue({ ok: true, text: async () => JSON.stringify(result) });
		vi.stubGlobal('fetch', fetchMock);
		await expect(removeGroupMember(1, 'group-a', 'student@kent.edu')).resolves.toEqual(result);
		expect(fetchMock).toHaveBeenCalledTimes(1);
		expect(fetchMock).toHaveBeenCalledWith(
			'/api/backend/courses/1/groups/group-a/members',
			expect.objectContaining({
				method: 'DELETE',
				body: JSON.stringify({ id: 'student@kent.edu' })
			})
		);
	});
	it('sends only the supplied settings and encodes group identifiers', async () => {
		const fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			text: async () => JSON.stringify({ group: { id: 'a/b', is_active: false } })
		});
		vi.stubGlobal('fetch', fetchMock);
		await updateCourseGroup(1, 'a/b', { isActive: false });
		expect(fetchMock).toHaveBeenCalledWith(
			'/api/backend/courses/1/groups/a%2Fb',
			expect.objectContaining({ method: 'PATCH', body: '{"is_active":false}' })
		);
		await updateCourseGroup(1, 'a/b', {
			name: 'Project',
			keyLimit: 0,
			maxMembers: null,
			selfJoinEnabled: false
		});
		expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({
			name: 'Project',
			key_limit: 0,
			max_members: null,
			self_join_enabled: false
		});
	});
	it('deletes only the requested group and leaves failures available for inline display', async () => {
		const fetchMock = vi.fn().mockResolvedValue({
			ok: false,
			status: 409,
			text: async () => JSON.stringify({ error: 'The course changed while saving.' })
		});
		vi.stubGlobal('fetch', fetchMock);
		await expect(deleteCourseGroup(1, 'group-a')).rejects.toThrow(
			'The course changed while saving.'
		);
		expect(fetchMock).toHaveBeenCalledTimes(1);
		expect(fetchMock).toHaveBeenCalledWith(
			'/api/backend/courses/1/groups/group-a',
			expect.objectContaining({ method: 'DELETE' })
		);
	});
});

describe('addGroupMembers', () => {
	it('sends the selection in one request and returns actual addition counts', async () => {
		const result = {
			group: { id: 'group-a', memberIds: ['student@kent.edu'] },
			added_count: 1,
			already_member_count: 2
		};
		const fetchMock = vi
			.fn()
			.mockResolvedValue({ ok: true, text: async () => JSON.stringify(result) });
		vi.stubGlobal('fetch', fetchMock);
		const selection = ['student@kent.edu', 'existing1@kent.edu', 'existing2@kent.edu'];
		await expect(addGroupMembers(1, 'group-a', selection)).resolves.toEqual(result);
		expect(fetchMock).toHaveBeenCalledTimes(1);
		expect(fetchMock).toHaveBeenCalledWith('/api/backend/courses/1/groups/group-a/members', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
			body: JSON.stringify({ memberIds: selection })
		});
	});

	it('passes validation and conflict messages to the dialog without retrying', async () => {
		const fetchMock = vi.fn().mockResolvedValue({
			ok: false,
			status: 409,
			text: async () =>
				JSON.stringify({ error: 'The course changed. Review your selection and try again.' })
		});
		vi.stubGlobal('fetch', fetchMock);
		await expect(addGroupMembers(1, 'group-a', ['student@kent.edu'])).rejects.toThrow(
			'The course changed. Review your selection and try again.'
		);
		expect(fetchMock).toHaveBeenCalledTimes(1);
	});

	it('handles a lost connection without an automatic duplicate request', async () => {
		const fetchMock = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'));
		vi.stubGlobal('fetch', fetchMock);
		await expect(addGroupMembers(1, 'group-a', ['student@kent.edu'])).rejects.toThrow(
			'Unable to reach the server. Please try again.'
		);
		expect(fetchMock).toHaveBeenCalledTimes(1);
	});
});

describe('fetchCourseApiHistory', () => {
	it('maps backend history payload to frontend shape', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue({
				ok: true,
				json: async () => [
					{
						u_id: 'KSUID0001',
						c_id: 'SE 3010',
						course_id: 1,
						event_type: 'request',
						group_id: 'group-a',
						group_name: 'Group A',
						is_group_member: true,
						meta: { path: '/v1/ask' },
						created: '2026-04-01T00:00:00Z'
					}
				]
			})
		);

		const rows = await fetchCourseApiHistory(1);
		expect(rows).toEqual([
			{
				userId: 'KSUID0001',
				courseCode: 'SE 3010',
				courseId: 1,
				eventType: 'request',
				groupId: 'group-a',
				groupName: 'Group A',
				isGroupMember: true,
				meta: { path: '/v1/ask' },
				created: '2026-04-01T00:00:00Z'
			}
		]);
	});

	it('throws when request fails', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue({
				ok: false,
				status: 500,
				text: async () => 'boom'
			})
		);

		await expect(fetchCourseApiHistory(1)).rejects.toThrow('Action failed. Please try again.');
	});
});

describe('group self-joining', () => {
	it('shows a structured account-inactive error clearly', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue({
				ok: false,
				status: 403,
				text: async () => JSON.stringify({ error: { message: 'This account is inactive.' } })
			})
		);
		await expect(joinCourseGroup(1, 'group-a')).rejects.toThrow('This account is inactive.');
	});
	it('joins as the signed-in student with no client-supplied identity', async () => {
		const result = { group: { id: 'group-a' }, already_member: false };
		const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => result });
		vi.stubGlobal('fetch', fetchMock);
		await expect(joinCourseGroup(1, 'group-a')).resolves.toEqual(result);
		expect(fetchMock).toHaveBeenCalledWith(
			'/api/backend/courses/1/groups/group-a/join',
			expect.objectContaining({ method: 'POST', body: '{}' })
		);
	});

	it('saves the explicit opt-in policy and optional limit together', async () => {
		const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ group: {} }) });
		vi.stubGlobal('fetch', fetchMock);
		await updateGroupJoinSettings(1, 'group-a', { selfJoinEnabled: false, maxMembers: null });
		expect(fetchMock).toHaveBeenCalledWith(
			'/api/backend/courses/1/groups/group-a/join-settings',
			expect.objectContaining({
				method: 'PATCH',
				body: JSON.stringify({ self_join_enabled: false, max_members: null })
			})
		);
	});

	it('surfaces a group filling up without silently retrying the request', async () => {
		const fetchMock = vi.fn().mockResolvedValue({
			ok: false,
			status: 409,
			text: async () => JSON.stringify({ error: 'This group is full.' })
		});
		vi.stubGlobal('fetch', fetchMock);
		await expect(joinCourseGroup(1, 'group-a')).rejects.toThrow('This group is full.');
		expect(fetchMock).toHaveBeenCalledTimes(1);
	});
});
