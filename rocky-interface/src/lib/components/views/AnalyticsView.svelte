<script lang="ts">
	import { onMount } from 'svelte';
	import { fetchAnalyticsActivity, fetchAnalyticsKpis } from '$lib/api/content';
	import { toActivityRow, toKpiMetric, type ActivityRow, type KpiMetric } from '$lib/types/analytics';
	import ViewShell from '$lib/components/ViewShell.svelte';

	let kpis: KpiMetric[] = [];
	let recentActivity: ActivityRow[] = [];
	let isLoading = true;
	let error: string | null = null;

	onMount(async () => {
		try {
			const [rawKpis, rawActivity] = await Promise.all([fetchAnalyticsKpis(), fetchAnalyticsActivity()]);
			kpis = rawKpis.map(toKpiMetric);
			recentActivity = rawActivity.map(toActivityRow);
		} catch (err) {
			error = err instanceof Error ? err.message : 'An error occurred while loading analytics.';
		} finally {
			isLoading = false;
		}
	});
</script>

<ViewShell title="Analytics">
		<section class="section">
			<div class="section-header">
				<h2>Overview</h2>
			</div>

			{#if isLoading}
				<div class="empty-state">
					<p>Loading analytics...</p>
				</div>
			{:else if error}
				<div class="empty-state">
					<p><strong>Error:</strong> {error}</p>
				</div>
			{:else}
				<p class="section-text">Main trend area for workload, health, and moderation metrics.</p>

				<div class="kpi-grid">
					{#each kpis as kpi}
						<article class="kpi-card">
							<p>{kpi.label}</p>
							<strong>{kpi.value}</strong>
							<span>{kpi.delta}</span>
						</article>
					{/each}
				</div>

				<div class="graph-placeholder">
					<div class="graph-grid" aria-hidden="true"></div>
					<div class="graph-line" aria-hidden="true"></div>
					<div class="graph-label">Detailed analytics graph area</div>
				</div>

				<div class="table-wrap">
					<table class="data-table">
						<thead>
							<tr>
								<th>Window</th>
								<th>Requests</th>
								<th>Flagged</th>
								<th>Success Rate</th>
							</tr>
						</thead>
						<tbody>
							{#each recentActivity as row}
								<tr>
									<td>{row.window}</td>
									<td>{row.requests}</td>
									<td>{row.flagged}</td>
									<td>{row.successRate}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}
		</section>
</ViewShell>
