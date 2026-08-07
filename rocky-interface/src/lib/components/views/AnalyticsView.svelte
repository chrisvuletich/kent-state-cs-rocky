<script lang="ts">
	import { browser } from '$app/environment';
	import { onMount } from 'svelte';
	import {
		fetchAnalyticsBreakdown,
		fetchAnalyticsCurrent,
		fetchAnalyticsHardware,
		fetchAnalyticsRequest,
		fetchAnalyticsRequests,
		fetchAnalyticsSummary,
		fetchAnalyticsTimeseries,
		updateAnalyticsReview
	} from '$lib/api/analytics';
	import HardwareCorrelationChart from '$lib/components/analytics/HardwareCorrelationChart.svelte';
	import ThroughputChart from '$lib/components/analytics/ThroughputChart.svelte';
	import ViewShell from '$lib/components/ViewShell.svelte';
	import {
		analyticsDimensions,
		analyticsReviewReasons,
		analyticsReviewStatuses,
		analyticsWindows,
		type AnalyticsBreakdown,
		type AnalyticsBreakdownRow,
		type AnalyticsCurrent,
		type AnalyticsDimension,
		type AnalyticsHardware,
		type AnalyticsOutcome,
		type AnalyticsRequestDetail,
		type AnalyticsRequestFilters,
		type AnalyticsRequestSummary,
		type AnalyticsRequests,
		type AnalyticsReviewReason,
		type AnalyticsReviewStatus,
		type AnalyticsSummary,
		type AnalyticsTimeseries,
		type AnalyticsWindow
	} from '$lib/types/analytics';
	import '$lib/styles/routes/modules/analytics-view.css';

	const windowLabels: Record<AnalyticsWindow, string> = {
		'15m': '15 minutes',
		'1h': '1 hour',
		'6h': '6 hours',
		'24h': '24 hours',
		'7d': '7 days',
		'30d': '30 days'
	};
	const dimensionLabels: Record<AnalyticsDimension, string> = {
		user: 'User',
		course: 'Course',
		key: 'API key',
		group: 'Group',
		model: 'Model',
		source: 'Source',
		outcome: 'Outcome'
	};
	const reviewReasonLabels: Record<AnalyticsReviewReason, string> = {
		academic_integrity: 'Academic integrity',
		harmful_content: 'Harmful content',
		security_abuse: 'Security abuse',
		policy_violation: 'Policy violation',
		system_quality: 'System quality',
		other: 'Other'
	};

	let selectedWindow: AnalyticsWindow = '24h';
	let selectedDimension: AnalyticsDimension = 'user';
	let summary: AnalyticsSummary | null = null;
	let current: AnalyticsCurrent | null = null;
	let series: AnalyticsTimeseries | null = null;
	let hardware: AnalyticsHardware | null = null;
	let breakdown: AnalyticsBreakdown | null = null;
	let recent: AnalyticsRequests | null = null;
	let selectedRequestId: string | null = null;
	let selectedRequest: AnalyticsRequestDetail | null = null;
	let detailLoading = false;
	let detailDismissed = false;
	let isLoading = true;
	let isRefreshing = false;
	let error: string | null = null;
	let lastUpdated: Date | null = null;
	let search = '';
	let outcomeFilter: AnalyticsOutcome | 'active' | '' = '';
	let reviewFilter: 'all' | 'flagged' | AnalyticsReviewStatus = 'all';
	let requestListLoading = false;
	let mobilePanel: 'breakdown' | 'requests' = 'breakdown';
	let loadRevision = 0;
	let reviewFlagged = false;
	let reviewReasons: AnalyticsReviewReason[] = [];
	let reviewStatus: AnalyticsReviewStatus = 'unreviewed';
	let reviewNotes = '';
	let reviewSaving = false;
	let reviewMessage: string | null = null;
	let reviewError: string | null = null;
	let reviewBaseline = '';
	let detailRevision = 0;

	$: filteredBreakdown = filterBreakdown(breakdown?.rows ?? [], search);
	$: reviewDirty = Boolean(selectedRequest) && reviewSignature() !== reviewBaseline;

	onMount(() => {
		restoreUrlState();
		void loadAnalytics();
		const interval = window.setInterval(() => {
			if (document.visibilityState === 'visible') void loadAnalytics(true);
		}, 30_000);
		return () => window.clearInterval(interval);
	});

	function restoreUrlState(): void {
		if (!browser) return;
		const params = new URLSearchParams(window.location.search);
		const requestedWindow = params.get('analytics_window');
		const requestedDimension = params.get('analytics_dimension');
		const requestId = params.get('analytics_request');
		const requestedOutcome = params.get('analytics_outcome');
		const requestedReview = params.get('analytics_review');
		if (analyticsWindows.includes(requestedWindow as AnalyticsWindow)) selectedWindow = requestedWindow as AnalyticsWindow;
		if (analyticsDimensions.includes(requestedDimension as AnalyticsDimension)) selectedDimension = requestedDimension as AnalyticsDimension;
		if (requestId?.trim()) selectedRequestId = requestId.trim();
		if (['completed', 'rejected', 'failed', 'timed_out', 'active'].includes(requestedOutcome || '')) outcomeFilter = requestedOutcome as AnalyticsOutcome | 'active';
		if (requestedReview === 'all' || requestedReview === 'flagged' || analyticsReviewStatuses.includes(requestedReview as AnalyticsReviewStatus)) reviewFilter = requestedReview as typeof reviewFilter;
	}

	function syncUrlState(): void {
		if (!browser) return;
		const url = new URL(window.location.href);
		url.searchParams.set('analytics_window', selectedWindow);
		url.searchParams.set('analytics_dimension', selectedDimension);
		if (selectedRequestId) url.searchParams.set('analytics_request', selectedRequestId);
		else url.searchParams.delete('analytics_request');
		if (outcomeFilter) url.searchParams.set('analytics_outcome', outcomeFilter);
		else url.searchParams.delete('analytics_outcome');
		if (reviewFilter !== 'all') url.searchParams.set('analytics_review', reviewFilter);
		else url.searchParams.delete('analytics_review');
		window.history.replaceState(window.history.state, '', url);
	}

	async function loadAnalytics(background = false): Promise<void> {
		const revision = ++loadRevision;
		if (background || summary) isRefreshing = true;
		else isLoading = true;
		error = null;
		try {
			const [nextCurrent, nextSummary, nextSeries, nextHardware, nextBreakdown, nextRecent] = await Promise.all([
				fetchAnalyticsCurrent(),
				fetchAnalyticsSummary(selectedWindow),
				fetchAnalyticsTimeseries(selectedWindow),
				fetchAnalyticsHardware(selectedWindow),
				fetchAnalyticsBreakdown(selectedWindow, selectedDimension),
				fetchAnalyticsRequests(selectedWindow, requestFilters())
			]);
			if (revision !== loadRevision) return;
			current = nextCurrent;
			summary = nextSummary;
			series = nextSeries;
			hardware = nextHardware;
			breakdown = nextBreakdown;
			recent = nextRecent;
			lastUpdated = new Date(nextCurrent.generated_at);
			if (selectedRequestId) {
				if (!reviewDirty && !reviewSaving && !detailLoading) {
					void selectRequest(selectedRequestId, false);
				}
			} else if (!detailDismissed && nextRecent.requests[0]) {
				void selectRequest(nextRecent.requests[0].request_id, false);
			}
		} catch (caught) {
			error = caught instanceof Error ? caught.message : 'Unable to load analytics right now.';
		} finally {
			if (revision === loadRevision) {
				isLoading = false;
				isRefreshing = false;
			}
		}
	}

	async function changeWindow(windowValue: AnalyticsWindow): Promise<void> {
		if (windowValue === selectedWindow) return;
		if (!canDiscardReview()) return;
		detailRevision += 1;
		selectedWindow = windowValue;
		selectedRequestId = null;
		selectedRequest = null;
		detailDismissed = false;
		syncUrlState();
		await loadAnalytics();
	}

	async function changeDimension(dimension: AnalyticsDimension): Promise<void> {
		if (dimension === selectedDimension) return;
		selectedDimension = dimension;
		search = '';
		syncUrlState();
		try {
			breakdown = await fetchAnalyticsBreakdown(selectedWindow, selectedDimension);
		} catch (caught) {
			error = caught instanceof Error ? caught.message : 'Unable to load this breakdown.';
		}
	}

	async function selectRequest(requestId: string, updateUrl = true): Promise<void> {
		if (reviewSaving && updateUrl) return;
		if (updateUrl && reviewDirty && !canDiscardReview()) return;
		const revision = ++detailRevision;
		selectedRequestId = requestId;
		selectedRequest = null;
		reviewBaseline = '';
		detailDismissed = false;
		detailLoading = true;
		if (updateUrl) syncUrlState();
		try {
			const detail = await fetchAnalyticsRequest(requestId);
			if (selectedRequestId === requestId && revision === detailRevision) {
				selectedRequest = detail;
				hydrateReview(detail);
			}
		} catch (caught) {
			error = caught instanceof Error ? caught.message : 'Unable to load request details.';
		} finally {
			if (selectedRequestId === requestId && revision === detailRevision) detailLoading = false;
		}
	}

	function requestFilters(): AnalyticsRequestFilters {
		return {
			outcome: outcomeFilter,
			flagged: reviewFilter === 'flagged' ? true : undefined,
			reviewStatus: reviewFilter !== 'all' && reviewFilter !== 'flagged' ? reviewFilter : ''
		};
	}

	async function refreshRequestQueue(): Promise<void> {
		requestListLoading = true;
		syncUrlState();
		try {
			recent = await fetchAnalyticsRequests(selectedWindow, requestFilters());
		} catch (caught) {
			error = caught instanceof Error ? caught.message : 'Unable to refresh the review queue.';
		} finally {
			requestListLoading = false;
		}
	}

	function hydrateReview(detail: AnalyticsRequestDetail): void {
		const review = detail.review;
		reviewFlagged = Boolean(review?.flagged);
		reviewReasons = review?.flag_reasons ? [...review.flag_reasons] : [];
		reviewStatus = review?.status || 'unreviewed';
		reviewNotes = review?.notes || '';
		reviewMessage = null;
		reviewError = null;
		reviewBaseline = reviewSignature();
	}

	function reviewSignature(): string {
		return JSON.stringify({
			flagged: reviewFlagged,
			flag_reasons: [...reviewReasons].sort(),
			status: reviewStatus,
			notes: reviewNotes
		});
	}

	function canDiscardReview(): boolean {
		if (reviewSaving) return false;
		return !reviewDirty || window.confirm('Discard your unsaved review changes?');
	}

	function toggleFlagged(): void {
		reviewFlagged = !reviewFlagged;
		if (!reviewFlagged) reviewReasons = [];
		reviewMessage = null;
	}

	function toggleReviewReason(reason: AnalyticsReviewReason): void {
		reviewReasons = reviewReasons.includes(reason)
			? reviewReasons.filter((value) => value !== reason)
			: [...reviewReasons, reason];
		if (reviewReasons.length > 0) reviewFlagged = true;
		reviewMessage = null;
	}

	async function saveReview(): Promise<void> {
		if (!selectedRequestId || reviewSaving) return;
		const requestId = selectedRequestId;
		const submittedReview = {
			version: selectedRequest.review?.version ?? 0,
			flagged: reviewFlagged,
			flag_reasons: [...reviewReasons],
			status: reviewStatus,
			notes: reviewNotes
		};
		reviewSaving = true;
		reviewMessage = null;
		reviewError = null;
		try {
			const detail = await updateAnalyticsReview(requestId, submittedReview);
			if (selectedRequestId === requestId) {
				selectedRequest = detail;
				hydrateReview(detail);
				reviewMessage = 'Review saved.';
			}
			await refreshRequestQueue();
		} catch (caught) {
			reviewError = caught instanceof Error ? caught.message : 'Unable to save this review.';
		} finally {
			reviewSaving = false;
		}
	}

	function closeDetail(): void {
		if (!canDiscardReview()) return;
		detailRevision += 1;
		selectedRequestId = null;
		selectedRequest = null;
		reviewBaseline = '';
		detailDismissed = true;
		syncUrlState();
	}

	function handleRequestKey(event: KeyboardEvent, requestId: string): void {
		if (event.key === 'Enter' || event.key === ' ') {
			event.preventDefault();
			void selectRequest(requestId);
		}
	}

	function filterBreakdown(rows: AnalyticsBreakdownRow[], value: string): AnalyticsBreakdownRow[] {
		const normalized = value.trim().toLowerCase();
		return normalized ? rows.filter((row) => `${row.label} ${row.id}`.toLowerCase().includes(normalized)) : rows;
	}

	function number(value: number | null | undefined, digits = 0): string {
		if (value === null || value === undefined || !Number.isFinite(value)) return 'N/A';
		return value.toLocaleString(undefined, { maximumFractionDigits: digits });
	}

	function percent(value: number | null | undefined): string {
		return value === null || value === undefined ? 'N/A' : `${(value * 100).toFixed(1)}%`;
	}

	function milliseconds(value: number | null | undefined): string {
		if (value === null || value === undefined) return 'N/A';
		return value >= 1_000 ? `${(value / 1_000).toFixed(2)} s` : `${number(value, 1)} ms`;
	}

	function dateTime(value: string | null | undefined): string {
		if (!value) return 'N/A';
		const date = new Date(value);
		return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
	}

	function userLabel(requestRow: AnalyticsRequestSummary | AnalyticsRequestDetail): string {
		return requestRow.actor?.name || requestRow.actor?.email || requestRow.actor?.user_id || 'Unattributed';
	}

	function courseLabel(requestRow: AnalyticsRequestSummary | AnalyticsRequestDetail): string {
		return requestRow.course?.course_code || (requestRow.course?.course_id ? String(requestRow.course.course_id) : '—');
	}

	function contentText(value: unknown): string {
		if (typeof value === 'string') return value.trim() ? value : 'Not recorded.';
		if (value === null || value === undefined) return 'Not recorded.';
		try { return JSON.stringify(value, null, 2); } catch { return 'Content could not be displayed.'; }
	}

	function outcomeLabel(value: string): string {
		return value === 'timed_out' ? 'Timed out' : value.charAt(0).toUpperCase() + value.slice(1);
	}
</script>

<ViewShell title="Analytics">
	<div class="analytics-workspace" aria-busy={isLoading}>
		<div class="analytics-command-bar">
			<div class="analytics-window-control" aria-label="Analytics time window">
				{#each analyticsWindows as windowValue}
					<button type="button" class:active={selectedWindow === windowValue} onclick={() => changeWindow(windowValue)}>{windowValue}</button>
				{/each}
			</div>
			<div class="analytics-live-state" class:stale={Boolean(error && summary)} aria-live="polite">
				<span class="live-dot"></span>
				<span>{error && summary ? 'Stale data' : isRefreshing ? 'Refreshing' : 'Live'}</span>
				<span class="live-divider" aria-hidden="true"></span>
				<span>Updated {lastUpdated && !Number.isNaN(lastUpdated.getTime()) ? lastUpdated.toLocaleTimeString() : '—'}</span>
			</div>
			<button class="analytics-refresh" type="button" disabled={isRefreshing} onclick={() => loadAnalytics()}>
				<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 11a8.1 8.1 0 1 0 2 5.3M20 4v7h-7"></path></svg>
				Refresh
			</button>
		</div>

		{#if error}
			<div class="analytics-alert" role="alert">
				<span>{error}</span>
				<button type="button" onclick={() => loadAnalytics()}>Try again</button>
			</div>
		{/if}

		{#if isLoading && !summary}
			<div class="analytics-loading" aria-live="polite">Loading telemetry for the last {windowLabels[selectedWindow]}…</div>
		{:else if summary && series && hardware && current && breakdown && recent}
			<section class="analytics-kpis" aria-label="Telemetry overview">
				<article><span>Requests</span><strong>{number(summary.requests)}</strong><small>{number(summary.rates.average_requests_per_minute, 2)} avg RPM</small></article>
				<article><span>Tokens</span><strong class="gold-value">{number(summary.usage.total_tokens)}</strong><small>{number(summary.rates.average_tokens_per_minute, 2)} avg TPM</small></article>
				<article><span>Success rate</span><strong class="success-value">{percent(summary.success_rate)}</strong><small>{number(summary.outcomes.completed)} completed</small></article>
				<article><span>P95 latency</span><strong>{milliseconds(summary.latency_ms.p95)}</strong><small>{number(summary.latency_ms.samples)} samples</small></article>
			</section>

			<section class="analytics-primary-grid">
				<div class="analytics-chart-panel">
					<ThroughputChart buckets={series.buckets} windowLabel={`Last ${windowLabels[selectedWindow]}`} />
				</div>
				<aside class="analytics-performance" aria-labelledby="model-performance-heading">
					<h2 id="model-performance-heading">Model performance</h2>
					<dl class="performance-list">
						<div><dt>Generation tokens/sec</dt><dd>{number(summary.model_performance.generation_tokens_per_second, 2)}</dd></div>
						<div><dt>Prompt tokens/sec</dt><dd>{number(summary.model_performance.prompt_tokens_per_second, 2)}</dd></div>
						<div><dt>Average generation time</dt><dd>{milliseconds(summary.model_performance.generation_duration.average_ms)}</dd></div>
						<div><dt>Active requests</dt><dd>{number(current.active_requests)}</dd></div>
					</dl>
					<dl class="outcome-list">
						<div class="completed"><dt>Completed</dt><dd>{number(summary.outcomes.completed)}</dd></div>
						<div class="failed"><dt>Failed</dt><dd>{number(summary.outcomes.failed)}</dd></div>
						<div class="timed-out"><dt>Timed out</dt><dd>{number(summary.outcomes.timed_out)}</dd></div>
						<div class="rejected"><dt>Rejected</dt><dd>{number(summary.outcomes.rejected)}</dd></div>
					</dl>
					<p class="performance-model">Model: <strong>{current.last_model || 'Not reported'}</strong></p>
				</aside>
			</section>

			<section class="analytics-hardware-panel">
				<HardwareCorrelationChart data={hardware} windowLabel={`Last ${windowLabels[selectedWindow]}`} activeRequests={current.active_requests} />
			</section>

			<div class="analytics-mobile-tabs" role="tablist" aria-label="Analytics detail view">
				<button type="button" role="tab" aria-selected={mobilePanel === 'breakdown'} class:active={mobilePanel === 'breakdown'} onclick={() => (mobilePanel = 'breakdown')}>Breakdown</button>
				<button type="button" role="tab" aria-selected={mobilePanel === 'requests'} class:active={mobilePanel === 'requests'} onclick={() => (mobilePanel = 'requests')}>Review queue</button>
			</div>

			<section class="analytics-lower-grid" class:show-breakdown={mobilePanel === 'breakdown'} class:show-requests={mobilePanel === 'requests'}>
				<div class="analytics-breakdown-panel">
					<div class="panel-heading"><h2>Breakdown</h2><span>{number(breakdown.rows.length)} groups</span></div>
					<div class="dimension-tabs" aria-label="Breakdown dimension">
						{#each analyticsDimensions as dimension}
							<button type="button" class:active={selectedDimension === dimension} onclick={() => changeDimension(dimension)}>{dimensionLabels[dimension]}</button>
						{/each}
					</div>
					<label class="breakdown-search">
						<span class="sr-only">Search {dimensionLabels[selectedDimension].toLowerCase()} breakdown</span>
						<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"></circle><path d="m20 20-4-4"></path></svg>
						<input bind:value={search} type="search" placeholder={`Search ${dimensionLabels[selectedDimension].toLowerCase()}…`} />
					</label>
					<div class="analytics-table-scroll breakdown-table-scroll">
						<table><thead><tr><th>{dimensionLabels[selectedDimension]}</th><th>Requests</th><th>Tokens</th><th>Success</th><th>P95</th></tr></thead>
						<tbody>{#if filteredBreakdown.length === 0}<tr><td colspan="5" class="table-empty">No matching telemetry.</td></tr>{:else}{#each filteredBreakdown as row (row.id)}<tr><td title={row.label}><strong>{row.label}</strong></td><td>{number(row.requests)}</td><td>{number(row.usage.total_tokens)}</td><td>{percent(row.success_rate)}</td><td>{milliseconds(row.latency_ms.p95)}</td></tr>{/each}{/if}</tbody></table>
					</div>
				</div>

				<div class="analytics-requests-panel">
					<div class="panel-heading"><h2>Review queue</h2><span>{requestListLoading ? 'Refreshing…' : `${number(recent.matched)} in window`}</span></div>
					<div class="request-filters">
						<label><span>Outcome</span><select bind:value={outcomeFilter} onchange={() => refreshRequestQueue()}><option value="">All outcomes</option><option value="completed">Completed</option><option value="rejected">Rejected</option><option value="failed">Failed</option><option value="timed_out">Timed out</option><option value="active">Active</option></select></label>
						<label><span>Review</span><select bind:value={reviewFilter} onchange={() => refreshRequestQueue()}><option value="all">All requests</option><option value="flagged">Flagged</option><option value="unreviewed">Unreviewed</option><option value="in_review">In review</option><option value="resolved">Resolved</option></select></label>
					</div>
					<div class="analytics-table-scroll requests-table-scroll">
						<table><thead><tr><th>Time</th><th>User</th><th>Course</th><th>Outcome</th><th>Tokens</th><th>Latency</th></tr></thead>
						<tbody>{#if recent.requests.length === 0}<tr><td colspan="6" class="table-empty">No requests match these filters.</td></tr>{:else}{#each recent.requests as requestRow (requestRow.request_id)}<tr class:selected={selectedRequestId === requestRow.request_id} tabindex="0" role="button" aria-label={`Inspect request ${requestRow.request_id}`} onclick={() => selectRequest(requestRow.request_id)} onkeydown={(event) => handleRequestKey(event, requestRow.request_id)}><td data-label="Time">{dateTime(requestRow.received_at)}</td><td data-label="User" title={userLabel(requestRow)}>{#if requestRow.review?.flagged}<span class="review-flag" aria-label="Flagged for review" title="Flagged for review"></span>{/if}{userLabel(requestRow)}</td><td data-label="Course">{courseLabel(requestRow)}</td><td data-label="Outcome"><span class={`outcome-text ${requestRow.outcome}`}>{outcomeLabel(requestRow.outcome)}</span></td><td data-label="Tokens">{number(requestRow.usage?.total_tokens)}</td><td data-label="Latency">{milliseconds(requestRow.performance?.request_latency_ms)}</td></tr>{/each}{/if}</tbody></table>
					</div>
				</div>

				<aside class="analytics-detail-panel" class:open={Boolean(selectedRequestId)} aria-label="Request detail">
					<div class="panel-heading"><h2>Request detail</h2>{#if selectedRequestId}<button class="detail-close" type="button" aria-label="Close request detail" onclick={closeDetail}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"></path></svg></button>{/if}</div>
					{#if detailLoading}<div class="detail-state">Loading request…</div>
					{:else if selectedRequest}
						<dl class="request-meta">
							<div><dt>Time</dt><dd>{dateTime(selectedRequest.received_at)}</dd></div>
							<div><dt>User</dt><dd>{userLabel(selectedRequest)}</dd></div>
							<div><dt>Course</dt><dd>{courseLabel(selectedRequest)}</dd></div>
							<div><dt>Model</dt><dd>{selectedRequest.model?.actual_model || '—'}</dd></div>
							<div><dt>Outcome</dt><dd><span class={`outcome-text ${selectedRequest.outcome}`}>{outcomeLabel(selectedRequest.outcome)}</span></dd></div>
							<div><dt>Tokens</dt><dd>{number(selectedRequest.usage?.total_tokens)}</dd></div>
							<div><dt>Latency</dt><dd>{milliseconds(selectedRequest.performance?.request_latency_ms)}</dd></div>
							<div><dt>Request ID</dt><dd class="request-id">{selectedRequest.request_id}</dd></div>
						</dl>
						<section class="review-editor" aria-labelledby="review-editor-heading">
							<div class="review-editor-heading"><h3 id="review-editor-heading">Administrative review</h3><button type="button" class="flag-toggle" class:active={reviewFlagged} role="switch" aria-checked={reviewFlagged} onclick={toggleFlagged}><span></span>{reviewFlagged ? 'Flagged' : 'Not flagged'}</button></div>
							<label class="review-field"><span>Status</span><select bind:value={reviewStatus}>{#each analyticsReviewStatuses as status}<option value={status}>{status === 'in_review' ? 'In review' : outcomeLabel(status)}</option>{/each}</select></label>
							<fieldset class="review-reasons"><legend>Flag reasons</legend><div>{#each analyticsReviewReasons as reason}<label><input type="checkbox" checked={reviewReasons.includes(reason)} onchange={() => toggleReviewReason(reason)} /><span>{reviewReasonLabels[reason]}</span></label>{/each}</div></fieldset>
							<label class="review-field"><span>Review notes</span><textarea bind:value={reviewNotes} maxlength="4000" rows="4" placeholder="Record the reason for the decision or any follow-up needed."></textarea><small>{reviewNotes.length.toLocaleString()} / 4,000</small></label>
							{#if selectedRequest.review?.reviewed_at}<p class="review-attribution">Last reviewed {dateTime(selectedRequest.review.reviewed_at)} by {selectedRequest.review.reviewed_by?.email || selectedRequest.review.reviewed_by?.user_id || 'an administrator'}.</p>{/if}
							{#if reviewFlagged && reviewReasons.length === 0}<p class="review-validation">Choose at least one reason for a flagged request.</p>{/if}
							{#if reviewError}<p class="review-validation" role="alert">{reviewError}</p>{/if}
							{#if reviewMessage}<p class="review-success" role="status">{reviewMessage}</p>{/if}
							<button type="button" class="review-save" disabled={reviewSaving || (reviewFlagged && reviewReasons.length === 0)} onclick={saveReview}>{reviewSaving ? 'Saving…' : 'Save review'}</button>
						</section>
						<div class="content-inspector"><h3>Prompt (sanitized)</h3><pre>{contentText(selectedRequest.request?.input_text ?? selectedRequest.request?.body)}</pre></div>
						<div class="content-inspector"><h3>Response (sanitized)</h3><pre>{contentText(selectedRequest.response?.output_text ?? selectedRequest.response?.body)}</pre></div>
					{:else}<div class="detail-state">Select a request to inspect its sanitized content.</div>{/if}
				</aside>
			</section>
		{/if}
	</div>
</ViewShell>
