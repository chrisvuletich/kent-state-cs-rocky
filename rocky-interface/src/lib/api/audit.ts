export type AuditLog = {
	userId: string;
	userName: string;
	userEmail: string;
	userRole: 'admin' | 'instructor' | 'student';
	course: string;
	action: string;
	created: string;
};

type ApiAuditLog = Partial<{
	u_id: string;
	user_name: string;
	user_email: string;
	user_role: 'admin' | 'instructor' | 'student';
	c_id: string;
	event_type: string;
	created: string;
}>;

export async function fetchAuditLogs(filters: Record<string, string> = {}): Promise<AuditLog[]> {
	const params = new URLSearchParams(Object.entries(filters).filter(([, value]) => value.trim()));
	const response = await fetch(`/api/backend/audit-logs${params.size ? `?${params}` : ''}`);
	if (!response.ok) throw new Error('Unable to load audit logs.');
	const rows = (await response.json()) as ApiAuditLog[];
	return rows.map((row) => ({
		userId: row.u_id?.trim() || '',
		userName: row.user_name?.trim() || row.user_email?.trim() || 'Unknown user',
		userEmail: row.user_email?.trim() || '',
		userRole:
			row.user_role === 'admin' || row.user_role === 'instructor' ? row.user_role : 'student',
		course: row.c_id?.trim() || 'No course',
		action: row.event_type?.trim() || 'unknown',
		created: row.created?.trim() || ''
	}));
}

export function auditExportUrl(filters: Record<string, string>, format: 'json' | 'csv'): string {
	const params = new URLSearchParams(
		Object.entries({ ...filters, format }).filter(([, value]) => value.trim())
	);
	return `/api/backend/audit/export?${params}`;
}
