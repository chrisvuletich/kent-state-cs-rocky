import { afterEach, describe, expect, it, vi } from 'vitest';

import { auditExportUrl, fetchAuditLogs } from './audit';

afterEach(() => {
	vi.unstubAllGlobals();
});

describe('fetchAuditLogs', () => {
	it('filters the query and maps backend rows to the view model', async () => {
		const fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			json: async () => [
				{
					u_id: ' KSUID0001 ',
					user_name: ' Grace Hopper ',
					user_email: ' grace@example.edu ',
					user_role: 'instructor',
					c_id: ' CS 10001 ',
					event_type: ' request ',
					created: ' 2026-08-19T12:00:00Z '
				},
				{
					user_email: ' student@example.edu ',
					user_role: 'unexpected',
					c_id: ' ',
					event_type: ''
				}
			]
		});
		vi.stubGlobal('fetch', fetchMock);

		await expect(fetchAuditLogs({ course: 'CS 10001', empty: '   ' })).resolves.toEqual([
			{
				userId: 'KSUID0001',
				userName: 'Grace Hopper',
				userEmail: 'grace@example.edu',
				userRole: 'instructor',
				course: 'CS 10001',
				action: 'request',
				created: '2026-08-19T12:00:00Z'
			},
			{
				userId: '',
				userName: 'student@example.edu',
				userEmail: 'student@example.edu',
				userRole: 'student',
				course: 'No course',
				action: 'unknown',
				created: ''
			}
		]);
		expect(fetchMock).toHaveBeenCalledWith('/api/backend/audit-logs?course=CS+10001');
	});

	it('loads the unfiltered endpoint without an empty query string', async () => {
		const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => [] });
		vi.stubGlobal('fetch', fetchMock);

		await expect(fetchAuditLogs()).resolves.toEqual([]);
		expect(fetchMock).toHaveBeenCalledWith('/api/backend/audit-logs');
	});

	it('uses a safe error when the backend request fails', async () => {
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }));

		await expect(fetchAuditLogs()).rejects.toThrow('Unable to load audit logs.');
	});
});

describe('auditExportUrl', () => {
	it('builds an encoded export URL and omits blank filters', () => {
		expect(auditExportUrl({ user: 'KSUID0001', course: 'CS 10001', empty: ' ' }, 'csv')).toBe(
			'/api/backend/audit/export?user=KSUID0001&course=CS+10001&format=csv'
		);
	});
});
