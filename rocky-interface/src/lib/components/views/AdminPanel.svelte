<script lang="ts">
	import '$lib/styles/components/modules/admin-panel.css';
	import { onMount } from 'svelte';
	import { fetchUsersForViews } from '$lib/api/users';
	import { fetchCourses } from '$lib/api/content';
	import { fetchCourseApiKeys } from '$lib/api/courses';
	import { fetchAnalyticsBreakdown } from '$lib/api/analytics';
	import { fetchAuditLogs } from '$lib/api/audit';
	import { currentFrame } from '$lib/stores/frameStore';
	import { analyticsCourseLabel } from '$lib/analytics/courseLabels';

	import {
		IconUsers,
		IconBooks,
		IconKey,
		IconShieldCheck,
		IconChartBar,
		IconListDetails
	} from '@tabler/icons-svelte';

	let stats = [
		{ title: 'Total Users', value: '—', icon: IconUsers },
		{ title: 'Active Users', value: '—', icon: IconUsers },
		{ title: 'Total Courses', value: '—', icon: IconBooks },
		{ title: 'API Keys Issued', value: '—', icon: IconKey }
	];

	type ServiceHealth = { name: string; ok: boolean; latencyMs: number };
	type HealthReport = { services?: ServiceHealth[] };

	const serviceLabels: Record<string, string> = {
		backend: 'Backend API',
		granite: 'Granite Bridge',
		'chat-api': 'Chat API',
		ollama: 'Ollama / Model'
	};

	function formatActivityTime(timestamp: string): string {
		const date = new Date(timestamp);
		return Number.isNaN(date.getTime()) ? timestamp : date.toLocaleString();
	}

	let statsError = '';
	let auditError = '';
	let topCoursesError = '';
	let healthError = '';
	let healthCheckedAt = '';

	async function loadStats() {
		statsError = '';
		try {
			const [users, courses] = await Promise.all([fetchUsersForViews(), fetchCourses()]);
			const courseApiKeys = await Promise.all(
				courses.map((course) => fetchCourseApiKeys(course.id))
			);
			stats[0] = { ...stats[0], value: String(users.length) };
			stats[1] = { ...stats[1], value: String(users.filter((user) => user.isActive).length) };
			stats[2] = { ...stats[2], value: String(courses.length) };
			stats[3] = {
				...stats[3],
				value: String(
					courseApiKeys.reduce(
						(total, keys) => total + keys.filter((key) => key.has_hash !== false).length,
						0
					)
				)
			};
			stats = [...stats];
		} catch (err) {
			console.error('[admin panel] failed to load dashboard totals', err);
			statsError = 'Dashboard totals are unavailable right now.';
		}
	}

	async function loadAuditActivity() {
		auditError = '';
		try {
			const activityEntries = await fetchAuditLogs();
			audit = activityEntries.slice(0, 5).map((event) => ({
				time: formatActivityTime(event.created),
				user:
					event.userName && event.userEmail
						? `${event.userName} (${event.userEmail})`
						: event.userName || event.userEmail || event.userId,
				action: event.action.replace(/-/g, ' '),
				course: event.course
			}));
		} catch (err) {
			console.error('[admin panel] failed to load audit activity', err);
			auditError = 'Recent audit activity is unavailable right now.';
		}
	}

	async function loadTopCourses() {
		topCoursesError = '';
		try {
			const [courses, courseUsage] = await Promise.all([
				fetchCourses(),
				fetchAnalyticsBreakdown('30d', 'course')
			]);
			const attributedCourses = courseUsage.rows.filter((row) => row.id !== 'unattributed');
			const highestRequestCount = Math.max(...attributedCourses.map((row) => row.requests), 1);
			topCourses = attributedCourses.slice(0, 5).map((row) => ({
				name: analyticsCourseLabel(row, courses),
				requests: row.requests,
				width: `${(row.requests / highestRequestCount) * 100}%`
			}));
		} catch (err) {
			console.error('[admin panel] failed to load top courses', err);
			topCoursesError = 'Course usage is unavailable right now.';
		}
	}

	async function loadAdminData() {
		await Promise.all([loadStats(), loadAuditActivity(), loadTopCourses()]);
	}

	async function loadServiceHealth() {
		healthError = '';
		try {
			const response = await fetch('/api/server-health');
			const report = (await response.json()) as HealthReport;
			if (!Array.isArray(report.services)) throw new Error('Invalid health response.');
			services = report.services
				.filter((service) => service.name !== 'web')
				.map((service) => ({
					name: serviceLabels[service.name] || service.name,
					status: service.ok ? 'Healthy' : 'Unavailable',
					ok: service.ok
				}));
			healthCheckedAt = new Date().toLocaleTimeString();
		} catch (err) {
			console.error('[admin panel] failed to load service health', err);
			services = services.map((service) => ({ ...service, status: 'Unknown', ok: false }));
			healthError = 'System status could not be refreshed.';
		}
	}

	onMount(() => {
		void loadAdminData();
		void loadServiceHealth();
	});

	let services = [
		{ name: 'Backend API', status: 'Checking…', ok: false },
		{ name: 'Granite Bridge', status: 'Checking…', ok: false },
		{ name: 'Chat API', status: 'Checking…', ok: false },
		{ name: 'Ollama / Model', status: 'Checking…', ok: false }
	];

	let topCourses: { name: string; requests: number; width: string }[] = [];

	let audit: { time: string; user: string; action: string; course: string }[] = [];
</script>

<div class="admin-panel">
	<div class="header">
		<div>
			<h1>Admin Dashboard</h1>
			<p>Monitor users, courses, API usage, and overall Rocky system activity.</p>
		</div>
	</div>

	<section class="stats-grid">
		{#each stats as stat}
			<div class="panel-card stat-card">
				<svelte:component this={stat.icon} size={28} />
				<div class="stat-value">{stat.value}</div>
				<div class="stat-title">{stat.title}</div>
			</div>
		{/each}
	</section>
	{#if statsError}<div class="admin-panel-error" role="alert">
			<span>{statsError}</span><button type="button" onclick={loadStats}>Try again</button>
		</div>{/if}

	<section class="admin-content-grid">
		<section class="panel-card audit-section">
			<div class="card-header">
				<IconListDetails size={20} />
				<h2>Recent Audit Logs</h2>
				<button type="button" onclick={() => currentFrame.set('audit')}>View All Logs</button>
			</div>

			<div class="admin-audit-table-wrap">
				{#if auditError}<div class="admin-panel-error" role="alert">
						<span>{auditError}</span><button type="button" onclick={loadAuditActivity}
							>Try again</button
						>
					</div>{/if}
				<table>
					<thead>
						<tr>
							<th>Time</th>
							<th>User</th>
							<th>Action</th>
							<th>Course</th>
						</tr>
					</thead>

					<tbody>
						{#each audit as row}
							<tr>
								<td>{row.time}</td>
								<td>{row.user}</td>
								<td>{row.action}</td>
								<td>{row.course}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		</section>

		<aside class="admin-side-stack">
			<section class="panel-card">
				<div class="card-header">
					<IconShieldCheck size={20} />
					<h2>System Status</h2>
				</div>

				{#each services as service}
					<div class="status-row">
						<span>{service.name}</span>
						<span class:healthy={service.ok} class:unhealthy={!service.ok}>{service.status}</span>
					</div>
				{/each}
				{#if healthError}<div class="admin-panel-error" role="alert">
						<span>{healthError}</span><button type="button" onclick={loadServiceHealth}
							>Try again</button
						>
					</div>{/if}
				{#if healthCheckedAt}<p class="panel-empty-state">Last checked {healthCheckedAt}</p>{/if}
			</section>

			<section class="panel-card">
				<div class="card-header">
					<IconChartBar size={20} />
					<h2>Top Courses — Last 30 Days</h2>
				</div>

				{#if topCoursesError}<div class="admin-panel-error" role="alert">
						<span>{topCoursesError}</span><button type="button" onclick={loadTopCourses}
							>Try again</button
						>
					</div>{/if}
				{#each topCourses as course}
					<div class="course-row">
						<div class="course-top">
							<span>{course.name}</span>
							<span>{course.requests} requests</span>
						</div>

						<div class="progress">
							<div class="fill" style={`width:${course.width}`}></div>
						</div>
					</div>
				{/each}
				{#if !topCoursesError && topCourses.length === 0}
					<p class="panel-empty-state">
						No attributed course requests were recorded in the last 30 days.
					</p>
				{/if}
			</section>
		</aside>
	</section>
</div>
