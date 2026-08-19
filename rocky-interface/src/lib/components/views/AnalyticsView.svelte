<script lang="ts">
	import { browser } from '$app/environment';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import {
		analyticsExportUrl,
		fetchAnalyticsBreakdown,
		fetchAnalyticsCurrent,
		fetchAnalyticsHardware,
		fetchAnalyticsRequest,
		fetchAnalyticsRequests,
		fetchAnalyticsSummary,
		fetchAnalyticsTimeseries,
		updateAnalyticsReview
	} from '$lib/api/analytics';
	import {
		analyticsFilterCount,
		analyticsFilterSignature,
		analyticsOperations,
		analyticsOutcomes,
		analyticsUrl,
		defaultAnalyticsFilters,
		parseAnalyticsFilters,
		type AnalyticsFilterState,
		type AnalyticsOperation,
		type AnalyticsReviewFilter
	} from '$lib/analytics/filters';
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
	import { handleTabListKeydown } from '$lib/accessibility/tabs';

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
	let reviewFilter: AnalyticsReviewFilter = 'all';
	let userFilter = '';
	let courseFilter = '';
	let keyFilter = '';
	let modelFilter = '';
	let operationFilter: AnalyticsOperation | '' = '';
	let sourceFilter = '';
	let errorTypeFilter = '';
	let requestListLoading = false;
	let exportLoading: 'json' | 'csv' | null = null;
	let exportMessage: string | null = null;
	let linkMessage: string | null = null;
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
	let breakdownRevision = 0;
	let appliedFilterSignature = '';
	let currentUrlFilterState: AnalyticsFilterState = defaultAnalyticsFilters;
	let currentAnalyticsDataSignature = '';

	$: filteredBreakdown = filterBreakdown(breakdown?.rows ?? [], search);
	$: reviewDirty = Boolean(selectedRequest) && reviewSignature() !== reviewBaseline;
	$: currentUrlFilterState = {
		window: selectedWindow,
		dimension: selectedDimension,
		user: userFilter.trim(),
		course: courseFilter.trim(),
		key: keyFilter.trim(),
		model: modelFilter.trim(),
		operation: operationFilter,
		outcome: outcomeFilter,
		source: sourceFilter.trim(),
		errorType: errorTypeFilter.trim(),
		review: reviewFilter,
		requestId: selectedRequestId || ''
	};
	$: currentAnalyticsDataSignature = JSON.stringify({
		...currentUrlFilterState,
		requestId: ''
	});
	$: activeFilterCount = analyticsFilterCount(currentUrlFilterState);
	$: filtersDirty = appliedFilterSignature !== currentAnalyticsDataSignature;

	onMount(() => {
		const initialState = parseAnalyticsFilters(new URLSearchParams(window.location.search));
		applyUrlState(initialState);
		appliedFilterSignature = analyticsDataSignature(initialState);
		const canonicalUrl = analyticsUrl(new URL(window.location.href), filterState());
		if (canonicalUrl.href !== window.location.href) {
			void goto(canonicalUrl, { replaceState: true, noScroll: true, keepFocus: true });
		}
		void loadAnalytics();
		const handlePopState = () => void restoreAnalyticsLocation();
		window.addEventListener('popstate', handlePopState);
		const interval = window.setInterval(() => {
			if (document.visibilityState === 'visible') void loadAnalytics(true);
		}, 30_000);
		return () => {
			window.clearInterval(interval);
			window.removeEventListener('popstate', handlePopState);
		};
	});

	async function restoreAnalyticsLocation(): Promise<void> {
		const previousState = filterState();
		if (!canDiscardReview()) {
			await goto(analyticsUrl(new URL(window.location.href), previousState), {
				replaceState: true,
				noScroll: true,
				keepFocus: true
			});
			return;
		}

		const previousSignature = analyticsFilterSignature(previousState);
		const nextState = parseAnalyticsFilters(new URLSearchParams(window.location.search));
		detailRevision += 1;
		breakdownRevision += 1;
		applyUrlState(nextState);
		appliedFilterSignature = analyticsDataSignature(nextState);
		detailDismissed = !nextState.requestId;
		if (analyticsFilterSignature(nextState) !== previousSignature) {
			await loadAnalytics();
		} else if (nextState.requestId) {
			await selectRequest(nextState.requestId, false);
		}
	}

	function filterState(): AnalyticsFilterState {
		return {
			window: selectedWindow,
			dimension: selectedDimension,
			user: userFilter.trim(),
			course: courseFilter.trim(),
			key: keyFilter.trim(),
			model: modelFilter.trim(),
			operation: operationFilter,
			outcome: outcomeFilter,
			source: sourceFilter.trim(),
			errorType: errorTypeFilter.trim(),
			review: reviewFilter,
			requestId: selectedRequestId || ''
		};
	}

	function applyUrlState(state: AnalyticsFilterState): void {
		selectedWindow = state.window;
		selectedDimension = state.dimension;
		userFilter = state.user;
		courseFilter = state.course;
		keyFilter = state.key;
		modelFilter = state.model;
		operationFilter = state.operation;
		outcomeFilter = state.outcome;
		sourceFilter = state.source;
		errorTypeFilter = state.errorType;
		reviewFilter = state.review;
		selectedRequestId = state.requestId || null;
		selectedRequest = null;
	}

	function analyticsDataSignature(state: AnalyticsFilterState = filterState()): string {
		return JSON.stringify({ ...state, requestId: '' });
	}

	async function syncUrlState(replaceState = false): Promise<void> {
		if (!browser) return;
		await goto(analyticsUrl(new URL(window.location.href), filterState()), {
			replaceState,
			noScroll: true,
			keepFocus: true
		});
	}

	async function loadAnalytics(background = false): Promise<void> {
		const revision = ++loadRevision;
		breakdownRevision += 1;
		if (background || summary) isRefreshing = true;
		else isLoading = true;
		error = null;
		try {
			const filters = requestFilters();
			const [nextCurrent, nextSummary, nextSeries, nextHardware, nextBreakdown, nextRecent] =
				await Promise.all([
					fetchAnalyticsCurrent(),
					fetchAnalyticsSummary(selectedWindow, filters),
					fetchAnalyticsTimeseries(selectedWindow, filters),
					fetchAnalyticsHardware(selectedWindow, filters),
					fetchAnalyticsBreakdown(selectedWindow, selectedDimension, filters),
					fetchAnalyticsRequests(selectedWindow, filters)
				]);
			if (revision !== loadRevision) return;
			current = nextCurrent;
			summary = nextSummary;
			series = nextSeries;
			hardware = nextHardware;
			breakdown = nextBreakdown;
			recent = nextRecent;
			appliedFilterSignature = analyticsDataSignature();
			lastUpdated = new Date(nextCurrent.generated_at);
			if (selectedRequestId) {
				if (!reviewDirty && !reviewSaving && !detailLoading) {
					void selectRequest(selectedRequestId, false);
				}
			} else if (!detailDismissed && nextRecent.requests[0]) {
				void selectRequest(nextRecent.requests[0].request_id, false);
			}
		} catch (caught) {
			if (revision === loadRevision) {
				error = caught instanceof Error ? caught.message : 'Unable to load analytics right now.';
			}
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
		await syncUrlState();
		await loadAnalytics();
	}

	async function changeDimension(dimension: AnalyticsDimension): Promise<void> {
		if (dimension === selectedDimension) return;
		const revision = ++breakdownRevision;
		selectedDimension = dimension;
		search = '';
		error = null;
		await syncUrlState();
		try {
			const nextBreakdown = await fetchAnalyticsBreakdown(
				selectedWindow,
				selectedDimension,
				requestFilters()
			);
			if (revision === breakdownRevision && selectedDimension === dimension) {
				breakdown = nextBreakdown;
			}
		} catch (caught) {
			if (revision === breakdownRevision && selectedDimension === dimension) {
				error = caught instanceof Error ? caught.message : 'Unable to load this breakdown.';
			}
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
		if (updateUrl) await syncUrlState();
		try {
			const detail = await fetchAnalyticsRequest(requestId);
			if (selectedRequestId === requestId && revision === detailRevision) {
				selectedRequest = detail;
				hydrateReview(detail);
			}
		} catch (caught) {
			if (selectedRequestId === requestId && revision === detailRevision) {
				error = caught instanceof Error ? caught.message : 'Unable to load request details.';
			}
		} finally {
			if (selectedRequestId === requestId && revision === detailRevision) detailLoading = false;
		}
	}

	function requestFilters(): AnalyticsRequestFilters {
		return {
			user: userFilter.trim(),
			course: courseFilter.trim(),
			key: keyFilter.trim(),
			model: modelFilter.trim(),
			operation: operationFilter,
			outcome: outcomeFilter,
			source: sourceFilter.trim(),
			errorType: errorTypeFilter.trim(),
			flagged: reviewFilter === 'flagged' ? true : undefined,
			reviewStatus: reviewFilter !== 'all' && reviewFilter !== 'flagged' ? reviewFilter : ''
		};
	}

	async function refreshRequestQueue(): Promise<void> {
		requestListLoading = true;
		try {
			recent = await fetchAnalyticsRequests(selectedWindow, requestFilters());
		} catch (caught) {
			error = caught instanceof Error ? caught.message : 'Unable to refresh the review queue.';
		} finally {
			requestListLoading = false;
		}
	}

	async function applyFilters(): Promise<void> {
		if (!canDiscardReview()) return;
		detailRevision += 1;
		selectedRequestId = null;
		selectedRequest = null;
		detailDismissed = false;
		exportMessage = null;
		await syncUrlState();
		await loadAnalytics();
	}

	async function clearFilters(): Promise<void> {
		if (!canDiscardReview()) return;
		const preservedWindow = selectedWindow;
		const preservedDimension = selectedDimension;
		applyUrlState({
			...defaultAnalyticsFilters,
			window: preservedWindow,
			dimension: preservedDimension
		});
		detailDismissed = false;
		exportMessage = null;
		await syncUrlState();
		await loadAnalytics();
	}

	async function copyAnalyticsLink(): Promise<void> {
		if (!browser) return;
		if (filtersDirty) {
			linkMessage = 'Apply the changed filters before copying this view.';
			return;
		}
		try {
			await navigator.clipboard.writeText(
				analyticsUrl(new URL(window.location.href), filterState()).href
			);
			linkMessage = 'Analytics link copied.';
		} catch {
			linkMessage = 'Unable to copy the link. Copy it from the address bar instead.';
		}
		window.setTimeout(() => (linkMessage = null), 2500);
	}

	async function downloadExport(format: 'json' | 'csv'): Promise<void> {
		if (!browser || exportLoading) return;
		if (filtersDirty) {
			exportMessage = 'Apply the changed filters before exporting this view.';
			return;
		}
		exportLoading = format;
		exportMessage = null;
		try {
			const response = await fetch(analyticsExportUrl(selectedWindow, format, requestFilters()), {
				cache: 'no-store'
			});
			if (!response.ok) {
				const payload = (await response.json().catch(() => null)) as { error?: unknown } | null;
				throw new Error(
					typeof payload?.error === 'string' ? payload.error : 'Unable to export analytics.'
				);
			}
			const blob = await response.blob();
			const disposition = response.headers.get('content-disposition') || '';
			const filename =
				disposition.match(/filename="?([^";]+)"?/i)?.[1] || `rocky-analytics.${format}`;
			const objectUrl = URL.createObjectURL(blob);
			const anchor = document.createElement('a');
			anchor.href = objectUrl;
			anchor.download = filename;
			anchor.click();
			URL.revokeObjectURL(objectUrl);
			exportMessage = `${format.toUpperCase()} export downloaded.`;
		} catch (caught) {
			exportMessage = caught instanceof Error ? caught.message : 'Unable to export analytics.';
		} finally {
			exportLoading = null;
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
		if (!selectedRequestId || !selectedRequest || reviewSaving) return;
		const requestId = selectedRequestId;
		const requestToReview = selectedRequest;
		const submittedReview = {
			version: requestToReview.review?.version ?? 0,
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
		void syncUrlState();
	}

	function handleRequestKey(event: KeyboardEvent, requestId: string): void {
		if (event.key === 'Enter' || event.key === ' ') {
			event.preventDefault();
			void selectRequest(requestId);
		}
	}

	function filterBreakdown(rows: AnalyticsBreakdownRow[], value: string): AnalyticsBreakdownRow[] {
		const normalized = value.trim().toLowerCase();
		return normalized
			? rows.filter((row) => `${row.label} ${row.id}`.toLowerCase().includes(normalized))
			: rows;
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
		return (
			requestRow.actor?.name ||
			requestRow.actor?.email ||
			requestRow.actor?.user_id ||
			'Unattributed'
		);
	}

	function courseLabel(requestRow: AnalyticsRequestSummary | AnalyticsRequestDetail): string {
		return (
			requestRow.course?.course_code ||
			(requestRow.course?.course_id ? String(requestRow.course.course_id) : '—')
		);
	}

	function contentText(value: unknown): string {
		if (typeof value === 'string') return value.trim() ? value : 'Not recorded.';
		if (value === null || value === undefined) return 'Not recorded.';
		try {
			return JSON.stringify(value, null, 2);
		} catch {
			return 'Content could not be displayed.';
		}
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
					<button
						type="button"
						class:active={selectedWindow === windowValue}
						onclick={() => changeWindow(windowValue)}>{windowValue}</button
					>
				{/each}
			</div>
			<div class="analytics-live-state" class:stale={Boolean(error && summary)} aria-live="polite">
				<span class="live-dot"></span>
				<span>{error && summary ? 'Stale data' : isRefreshing ? 'Refreshing' : 'Live'}</span>
				<span class="live-divider" aria-hidden="true"></span>
				<span
					>Updated {lastUpdated && !Number.isNaN(lastUpdated.getTime())
						? lastUpdated.toLocaleTimeString()
						: '—'}</span
				>
			</div>
			<button
				class="analytics-refresh"
				type="button"
				disabled={isRefreshing}
				onclick={() => loadAnalytics()}
			>
				<svg viewBox="0 0 24 24" aria-hidden="true"
					><path d="M20 11a8.1 8.1 0 1 0 2 5.3M20 4v7h-7"></path></svg
				>
				Refresh
			</button>
			<button
				class="analytics-refresh"
				type="button"
				disabled={filtersDirty}
				title={filtersDirty ? 'Apply the changed filters first' : 'Copy this analytics view'}
				onclick={copyAnalyticsLink}>Copy link</button
			>
			<button
				class="analytics-refresh"
				type="button"
				disabled={Boolean(exportLoading) || filtersDirty}
				onclick={() => downloadExport('json')}
				>{exportLoading === 'json' ? 'Exporting…' : 'Export JSON'}</button
			>
			<button
				class="analytics-refresh"
				type="button"
				disabled={Boolean(exportLoading) || filtersDirty}
				onclick={() => downloadExport('csv')}
				>{exportLoading === 'csv' ? 'Exporting…' : 'Export CSV'}</button
			>
		</div>

		{#if linkMessage || exportMessage}
			<p class="analytics-action-message" role="status">{linkMessage || exportMessage}</p>
		{/if}

		<details class="analytics-filter-panel" open={activeFilterCount > 0}>
			<summary>
				<span>Filters</span>
				<small
					>{filtersDirty
						? 'Changes not applied'
						: activeFilterCount
							? `${activeFilterCount} active`
							: 'All telemetry'}</small
				>
			</summary>
			<form
				class="analytics-filter-grid"
				onsubmit={(event) => {
					event.preventDefault();
					void applyFilters();
				}}
			>
				<label><span>User ID or email</span><input bind:value={userFilter} maxlength="256" /></label
				>
				<label
					><span>Course ID or code</span><input bind:value={courseFilter} maxlength="256" /></label
				>
				<label
					><span>API key ID or name</span><input bind:value={keyFilter} maxlength="256" /></label
				>
				<label><span>Model</span><input bind:value={modelFilter} maxlength="256" /></label>
				<label
					><span>Operation</span><select bind:value={operationFilter}
						><option value="">All operations</option>{#each analyticsOperations as operation}<option
								value={operation}>{operation}</option
							>{/each}</select
					></label
				>
				<label
					><span>Outcome</span><select bind:value={outcomeFilter}
						><option value="">All outcomes</option>{#each analyticsOutcomes as outcome}<option
								value={outcome}>{outcomeLabel(outcome)}</option
							>{/each}</select
					></label
				>
				<label><span>Request source</span><input bind:value={sourceFilter} maxlength="128" /></label
				>
				<label
					><span>Error type</span><input
						bind:value={errorTypeFilter}
						maxlength="128"
						placeholder="rate_limit_exceeded"
					/></label
				>
				<label
					><span>Review</span><select bind:value={reviewFilter}
						><option value="all">All requests</option><option value="flagged">Flagged</option
						><option value="unreviewed">Unreviewed</option><option value="in_review"
							>In review</option
						><option value="resolved">Resolved</option></select
					></label
				>
				<div class="analytics-filter-actions">
					<button type="submit">Apply filters</button>
					<button type="button" disabled={activeFilterCount === 0} onclick={clearFilters}
						>Clear filters</button
					>
				</div>
			</form>
		</details>

		{#if error}
			<div class="analytics-alert" role="alert">
				<span>{error}</span>
				<button type="button" onclick={() => loadAnalytics()}>Try again</button>
			</div>
		{/if}

		{#if isLoading && !summary}
			<div class="analytics-loading" aria-live="polite">
				Loading telemetry for the last {windowLabels[selectedWindow]}…
			</div>
		{:else if summary && series && hardware && current && breakdown && recent}
			<section class="analytics-kpis" aria-label="Telemetry overview">
				<article>
					<span>API requests</span><strong>{number(summary.requests)}</strong><small
						>{number(summary.rates.average_requests_per_minute, 2)} avg RPM</small
					>
				</article>
				<article>
					<span>Tokens</span><strong class="gold-value">{number(summary.usage.total_tokens)}</strong
					><small>{number(summary.rates.average_tokens_per_minute, 2)} avg TPM</small>
				</article>
				<article>
					<span>Generation success</span><strong class="success-value"
						>{percent(summary.success_rate)}</strong
					><small>{number(summary.generation.outcomes.completed)} completed</small>
				</article>
				<article>
					<span>Generation P95</span><strong>{milliseconds(summary.latency_ms.p95)}</strong><small
						>{number(summary.generation.inference_dispatches)} dispatched</small
					>
				</article>
			</section>

			<section class="analytics-primary-grid">
				<div class="analytics-chart-panel">
					<ThroughputChart
						buckets={series.buckets}
						windowLabel={`Last ${windowLabels[selectedWindow]}`}
					/>
				</div>
				<aside class="analytics-performance" aria-labelledby="model-performance-heading">
					<h2 id="model-performance-heading">API &amp; model performance</h2>
					<dl class="performance-list">
						<div>
							<dt>Generation tokens/sec</dt>
							<dd>{number(summary.model_performance.generation_tokens_per_second, 2)}</dd>
						</div>
						<div>
							<dt>Prompt tokens/sec</dt>
							<dd>{number(summary.model_performance.prompt_tokens_per_second, 2)}</dd>
						</div>
						<div>
							<dt>Average generation time</dt>
							<dd>{milliseconds(summary.model_performance.generation_duration.average_ms)}</dd>
						</div>
						<div>
							<dt>Active API requests</dt>
							<dd>{number(current.active_requests)}</dd>
						</div>
						<div>
							<dt>Rate-limit rejections</dt>
							<dd>{number(summary.rate_limits.exceeded)}</dd>
						</div>
						<div>
							<dt>Limiter unavailable</dt>
							<dd>{number(summary.rate_limits.unavailable)}</dd>
						</div>
					</dl>
					<dl class="outcome-list">
						<div class="completed">
							<dt>Completed</dt>
							<dd>{number(summary.generation.outcomes.completed)}</dd>
						</div>
						<div class="failed">
							<dt>Failed</dt>
							<dd>{number(summary.generation.outcomes.failed)}</dd>
						</div>
						<div class="timed-out">
							<dt>Timed out</dt>
							<dd>{number(summary.generation.outcomes.timed_out)}</dd>
						</div>
						<div class="rejected">
							<dt>Rejected</dt>
							<dd>{number(summary.generation.outcomes.rejected)}</dd>
						</div>
					</dl>
					<p class="performance-model">
						Model: <strong>{current.last_model || 'Not reported'}</strong>
					</p>
				</aside>
			</section>

			<section class="analytics-hardware-panel">
				<HardwareCorrelationChart
					data={hardware}
					windowLabel={`Last ${windowLabels[selectedWindow]}`}
					activeRequests={current.active_requests}
				/>
			</section>

			<div class="analytics-mobile-tabs" role="tablist" aria-label="Analytics detail view">
				<button
					id="analytics-breakdown-tab"
					type="button"
					role="tab"
					aria-selected={mobilePanel === 'breakdown'}
					aria-controls="analytics-breakdown-panel"
					tabindex={mobilePanel === 'breakdown' ? 0 : -1}
					class:active={mobilePanel === 'breakdown'}
					onkeydown={handleTabListKeydown}
					onclick={() => (mobilePanel = 'breakdown')}>Breakdown</button
				>
				<button
					id="analytics-requests-tab"
					type="button"
					role="tab"
					aria-selected={mobilePanel === 'requests'}
					aria-controls="analytics-requests-panel"
					tabindex={mobilePanel === 'requests' ? 0 : -1}
					class:active={mobilePanel === 'requests'}
					onkeydown={handleTabListKeydown}
					onclick={() => (mobilePanel = 'requests')}>Review queue</button
				>
			</div>

			<section
				class="analytics-lower-grid"
				class:show-breakdown={mobilePanel === 'breakdown'}
				class:show-requests={mobilePanel === 'requests'}
			>
				<div
					id="analytics-breakdown-panel"
					class="analytics-breakdown-panel"
					role="tabpanel"
					aria-labelledby="analytics-breakdown-tab"
				>
					<div class="panel-heading">
						<h2>Breakdown</h2>
						<span>{number(breakdown.rows.length)} groups</span>
					</div>
					<div class="dimension-tabs" aria-label="Breakdown dimension">
						{#each analyticsDimensions as dimension}
							<button
								type="button"
								class:active={selectedDimension === dimension}
								onclick={() => changeDimension(dimension)}>{dimensionLabels[dimension]}</button
							>
						{/each}
					</div>
					<label class="breakdown-search">
						<span class="sr-only"
							>Search {dimensionLabels[selectedDimension].toLowerCase()} breakdown</span
						>
						<svg viewBox="0 0 24 24" aria-hidden="true"
							><circle cx="11" cy="11" r="7"></circle><path d="m20 20-4-4"></path></svg
						>
						<input
							bind:value={search}
							type="search"
							placeholder={`Search ${dimensionLabels[selectedDimension].toLowerCase()}…`}
						/>
					</label>
					<div class="analytics-table-scroll breakdown-table-scroll">
						<table>
							<thead
								><tr
									><th>{dimensionLabels[selectedDimension]}</th><th>Requests</th><th>Tokens</th><th
										>Success</th
									><th>P95</th></tr
								></thead
							>
							<tbody
								>{#if filteredBreakdown.length === 0}<tr
										><td colspan="5" class="table-empty">No matching telemetry.</td></tr
									>{:else}{#each filteredBreakdown as row (row.id)}<tr
											><td title={row.label}><strong>{row.label}</strong></td><td
												>{number(row.requests)}</td
											><td>{number(row.usage.total_tokens)}</td><td>{percent(row.success_rate)}</td
											><td>{milliseconds(row.latency_ms.p95)}</td></tr
										>{/each}{/if}</tbody
							>
						</table>
					</div>
				</div>

				<div
					id="analytics-requests-panel"
					class="analytics-requests-panel"
					role="tabpanel"
					aria-labelledby="analytics-requests-tab"
				>
					<div class="panel-heading">
						<h2>Review queue</h2>
						<span>{requestListLoading ? 'Refreshing…' : `${number(recent.matched)} in window`}</span
						>
					</div>
					<div class="request-filters">
						<label
							><span>Outcome</span><select
								bind:value={outcomeFilter}
								onchange={() => applyFilters()}
								><option value="">All outcomes</option><option value="completed">Completed</option
								><option value="rejected">Rejected</option><option value="failed">Failed</option
								><option value="timed_out">Timed out</option><option value="active">Active</option
								></select
							></label
						>
						<label
							><span>Review</span><select bind:value={reviewFilter} onchange={() => applyFilters()}
								><option value="all">All requests</option><option value="flagged">Flagged</option
								><option value="unreviewed">Unreviewed</option><option value="in_review"
									>In review</option
								><option value="resolved">Resolved</option></select
							></label
						>
					</div>
					<div class="analytics-table-scroll requests-table-scroll">
						<table>
							<thead
								><tr
									><th>Time</th><th>User</th><th>Course</th><th>Outcome</th><th>Tokens</th><th
										>Latency</th
									></tr
								></thead
							>
							<tbody
								>{#if recent.requests.length === 0}<tr
										><td colspan="6" class="table-empty">No requests match these filters.</td></tr
									>{:else}{#each recent.requests as requestRow (requestRow.request_id)}<tr
											class:selected={selectedRequestId === requestRow.request_id}
											tabindex="0"
											role="button"
											aria-label={`Inspect request ${requestRow.request_id}`}
											onclick={() => selectRequest(requestRow.request_id)}
											onkeydown={(event) => handleRequestKey(event, requestRow.request_id)}
											><td data-label="Time">{dateTime(requestRow.received_at)}</td><td
												data-label="User"
												title={userLabel(requestRow)}
												>{#if requestRow.review?.flagged}<span
														class="review-flag"
														aria-label="Flagged for review"
														title="Flagged for review"
													></span>{/if}{userLabel(requestRow)}</td
											><td data-label="Course">{courseLabel(requestRow)}</td><td
												data-label="Outcome"
												><span class={`outcome-text ${requestRow.outcome}`}
													>{outcomeLabel(requestRow.outcome)}</span
												></td
											><td data-label="Tokens">{number(requestRow.usage?.total_tokens)}</td><td
												data-label="Latency"
												>{milliseconds(requestRow.performance?.request_latency_ms)}</td
											></tr
										>{/each}{/if}</tbody
							>
						</table>
					</div>
				</div>

				<aside
					class="analytics-detail-panel"
					class:open={Boolean(selectedRequestId)}
					aria-label="Request detail"
				>
					<div class="panel-heading">
						<h2>Request detail</h2>
						{#if selectedRequestId}<button
								class="detail-close"
								type="button"
								aria-label="Close request detail"
								onclick={closeDetail}
								><svg viewBox="0 0 24 24" aria-hidden="true"
									><path d="M6 6l12 12M18 6 6 18"></path></svg
								></button
							>{/if}
					</div>
					{#if detailLoading}<div class="detail-state">Loading request…</div>
					{:else if selectedRequest}
						<dl class="request-meta">
							<div>
								<dt>Time</dt>
								<dd>{dateTime(selectedRequest.received_at)}</dd>
							</div>
							<div>
								<dt>User</dt>
								<dd>{userLabel(selectedRequest)}</dd>
							</div>
							<div>
								<dt>Course</dt>
								<dd>{courseLabel(selectedRequest)}</dd>
							</div>
							<div>
								<dt>Model</dt>
								<dd>
									{selectedRequest.model?.actual_model ||
										selectedRequest.model?.public_model ||
										'—'}
								</dd>
							</div>
							<div>
								<dt>Operation</dt>
								<dd>{selectedRequest.operation || 'responses.create'}</dd>
							</div>
							<div>
								<dt>Outcome</dt>
								<dd>
									<span class={`outcome-text ${selectedRequest.outcome}`}
										>{outcomeLabel(selectedRequest.outcome)}</span
									>
								</dd>
							</div>
							{#if selectedRequest.error_stage}<div>
									<dt>Error stage</dt>
									<dd>{selectedRequest.error_stage}</dd>
								</div>{/if}
							{#if selectedRequest.error_type}<div>
									<dt>Error type</dt>
									<dd>{selectedRequest.error_type}</dd>
								</div>{/if}
							<div>
								<dt>Tokens</dt>
								<dd>{number(selectedRequest.usage?.total_tokens)}</dd>
							</div>
							<div>
								<dt>Latency</dt>
								<dd>{milliseconds(selectedRequest.performance?.request_latency_ms)}</dd>
							</div>
							<div>
								<dt>Request ID</dt>
								<dd class="request-id">{selectedRequest.request_id}</dd>
							</div>
						</dl>
						<section class="review-editor" aria-labelledby="review-editor-heading">
							<div class="review-editor-heading">
								<h3 id="review-editor-heading">Administrative review</h3>
								<button
									type="button"
									class="flag-toggle"
									class:active={reviewFlagged}
									role="switch"
									aria-checked={reviewFlagged}
									onclick={toggleFlagged}
									><span></span>{reviewFlagged ? 'Flagged' : 'Not flagged'}</button
								>
							</div>
							<label class="review-field"
								><span>Status</span><select bind:value={reviewStatus}
									>{#each analyticsReviewStatuses as status}<option value={status}
											>{status === 'in_review' ? 'In review' : outcomeLabel(status)}</option
										>{/each}</select
								></label
							>
							<fieldset class="review-reasons">
								<legend>Flag reasons</legend>
								<div>
									{#each analyticsReviewReasons as reason}<label
											><input
												type="checkbox"
												checked={reviewReasons.includes(reason)}
												onchange={() => toggleReviewReason(reason)}
											/><span>{reviewReasonLabels[reason]}</span></label
										>{/each}
								</div>
							</fieldset>
							<label class="review-field"
								><span>Review notes</span><textarea
									bind:value={reviewNotes}
									maxlength="4000"
									rows="4"
									placeholder="Record the reason for the decision or any follow-up needed."
								></textarea><small>{reviewNotes.length.toLocaleString()} / 4,000</small></label
							>
							{#if selectedRequest.review?.reviewed_at}<p class="review-attribution">
									Last reviewed {dateTime(selectedRequest.review.reviewed_at)} by {selectedRequest
										.review.reviewed_by?.email ||
										selectedRequest.review.reviewed_by?.user_id ||
										'an administrator'}.
								</p>{/if}
							{#if reviewFlagged && reviewReasons.length === 0}<p class="review-validation">
									Choose at least one reason for a flagged request.
								</p>{/if}
							{#if reviewError}<p class="review-validation" role="alert">{reviewError}</p>{/if}
							{#if reviewMessage}<p class="review-success" role="status">{reviewMessage}</p>{/if}
							<button
								type="button"
								class="review-save"
								disabled={reviewSaving || (reviewFlagged && reviewReasons.length === 0)}
								onclick={saveReview}>{reviewSaving ? 'Saving…' : 'Save review'}</button
							>
						</section>
						<div class="content-inspector">
							<h3>Prompt</h3>
							<pre>{contentText(
									selectedRequest.request?.input_text ?? selectedRequest.request?.body
								)}</pre>
						</div>
						<div class="content-inspector">
							<h3>Response</h3>
							<pre>{contentText(
									selectedRequest.response?.output_text ?? selectedRequest.response?.body
								)}</pre>
						</div>
					{:else}<div class="detail-state">
							Select a request to inspect its recorded content.
						</div>{/if}
				</aside>
			</section>
		{/if}
	</div>
</ViewShell>
