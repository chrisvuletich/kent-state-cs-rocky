<script lang="ts">
	import { onMount } from 'svelte';
	import { auditExportUrl, fetchAuditLogs, type AuditLog } from '$lib/api/audit';
	import ViewShell from '$lib/components/ViewShell.svelte';
	import '$lib/styles/routes/modules/audit-logs.css';
	let logs: AuditLog[] = [];
	let loading = true;
	let error = '';
	let search = '';
	let role = '';
	let course = '';
	let action = '';
	let dateFrom = '';
	let dateTo = '';
	let exportLoading: 'json' | 'csv' | null = null;
	let exportMessage = '';

	onMount(loadLogs);
	async function loadLogs(): Promise<void> {
		loading = true;
		error = '';
		try {
			logs = await fetchAuditLogs({
				search,
				role,
				course,
				action,
				date_from: dateFrom,
				date_to: dateTo
			});
		} catch (err) {
			error = err instanceof Error ? err.message : 'Unable to load audit logs.';
		} finally {
			loading = false;
		}
	}
	function clearFilters(): void {
		search = '';
		role = '';
		course = '';
		action = '';
		dateFrom = '';
		dateTo = '';
		loadLogs();
	}
	function filters(): Record<string, string> {
		return {
			search,
			role,
			course,
			action,
			date_from: dateFrom,
			date_to: dateTo
		};
	}
	async function downloadExport(format: 'json' | 'csv'): Promise<void> {
		if (exportLoading) return;
		exportLoading = format;
		exportMessage = '';
		try {
			const response = await fetch(auditExportUrl(filters(), format), { cache: 'no-store' });
			if (!response.ok) {
				const payload = (await response.json().catch(() => null)) as { error?: unknown } | null;
				throw new Error(
					typeof payload?.error === 'string' ? payload.error : 'Unable to export audit logs.'
				);
			}
			const blob = await response.blob();
			const disposition = response.headers.get('content-disposition') || '';
			const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1] || `rocky-audit.${format}`;
			const objectUrl = URL.createObjectURL(blob);
			const anchor = document.createElement('a');
			anchor.href = objectUrl;
			anchor.download = filename;
			anchor.click();
			URL.revokeObjectURL(objectUrl);
			exportMessage = `${format.toUpperCase()} export downloaded.`;
		} catch (caught) {
			exportMessage = caught instanceof Error ? caught.message : 'Unable to export audit logs.';
		} finally {
			exportLoading = null;
		}
	}
	function formatDate(value: string): string {
		const date = new Date(value);
		return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
	}
</script>

<ViewShell title="Audit Logs">
	<section class="section section-flat audit-log-view">
		<p class="audit-intro">
			Review administrative and course activity. Filters can be combined to narrow the results.
		</p>
		<form
			class="audit-filters"
			onsubmit={(event) => {
				event.preventDefault();
				loadLogs();
			}}
		>
			<input
				bind:value={search}
				type="search"
				placeholder="Search name, email, course, or action"
				aria-label="Search audit logs"
			/>
			<select bind:value={role} aria-label="Filter by role"
				><option value="">All user roles</option><option value="student">Students</option><option
					value="instructor">Instructors</option
				><option value="admin">Admins</option></select
			>
			<input bind:value={course} placeholder="Course" aria-label="Filter by course" />
			<input bind:value={action} placeholder="Action type" aria-label="Filter by action type" />
			<label>From <input bind:value={dateFrom} type="date" /></label><label
				>To <input bind:value={dateTo} type="date" /></label
			>
			<button class="view-btn" type="submit">Apply filters</button><button
				class="view-btn"
				type="button"
				onclick={clearFilters}>Clear</button
			>
			<button
				class="view-btn"
				type="button"
				disabled={Boolean(exportLoading)}
				onclick={() => downloadExport('json')}
				>{exportLoading === 'json' ? 'Exporting…' : 'Export JSON'}</button
			>
			<button
				class="view-btn"
				type="button"
				disabled={Boolean(exportLoading)}
				onclick={() => downloadExport('csv')}
				>{exportLoading === 'csv' ? 'Exporting…' : 'Export CSV'}</button
			>
		</form>
		{#if exportMessage}<p class="audit-export-message" role="status">{exportMessage}</p>{/if}
		{#if loading}<div class="empty-state"><p>Loading audit logs...</p></div>
		{:else if error}<div class="empty-state"><p>{error}</p></div>
		{:else}<p class="audit-count">{logs.length} log {logs.length === 1 ? 'entry' : 'entries'}</p>
			<div class="table-container">
				<table class="data-table audit-table">
					<thead
						><tr><th>Time</th><th>User</th><th>Role</th><th>Action</th><th>Course</th></tr></thead
					><tbody
						>{#if logs.length === 0}<tr><td colspan="5">No logs match these filters.</td></tr
							>{:else}{#each logs as log (`${log.created}-${log.userId}-${log.action}`)}<tr
									><td>{formatDate(log.created)}</td><td
										><strong>{log.userName}</strong><br /><span>{log.userEmail}</span></td
									><td>{log.userRole}</td><td>{log.action.replace(/-/g, ' ')}</td><td
										>{log.course}</td
									></tr
								>{/each}{/if}</tbody
					>
				</table>
			</div>{/if}
	</section>
</ViewShell>
