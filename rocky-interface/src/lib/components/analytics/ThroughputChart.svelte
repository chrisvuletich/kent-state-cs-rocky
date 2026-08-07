<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import type { AnalyticsTimeBucket } from '$lib/types/analytics';

	export let buckets: AnalyticsTimeBucket[] = [];
	export let windowLabel = 'Last 24 hours';

	let container: HTMLDivElement;
	let chartWidth = 760;
	let observer: ResizeObserver | null = null;
	const chartHeight = 270;
	const margin = { top: 20, right: 68, bottom: 42, left: 54 };

	$: innerWidth = Math.max(1, chartWidth - margin.left - margin.right);
	$: innerHeight = chartHeight - margin.top - margin.bottom;
	$: maxRequests = Math.max(1, ...buckets.map((bucket) => bucket.requests));
	$: maxTokens = Math.max(1, ...buckets.map((bucket) => bucket.usage.total_tokens));
	$: requestPath = linePath(buckets.map((bucket) => bucket.requests), maxRequests);
	$: tokenPath = linePath(buckets.map((bucket) => bucket.usage.total_tokens), maxTokens);
	$: xTicks = tickIndexes(buckets.length, chartWidth < 520 ? 3 : 5);
	$: latest = buckets.at(-1);

	onMount(() => {
		observer = new ResizeObserver(([entry]) => {
			chartWidth = Math.max(300, Math.round(entry.contentRect.width));
		});
		observer.observe(container);
	});

	onDestroy(() => observer?.disconnect());

	function x(index: number, count = buckets.length): number {
		return margin.left + (count <= 1 ? 0 : (index / (count - 1)) * innerWidth);
	}

	function y(value: number, maximum: number): number {
		return margin.top + innerHeight - (value / maximum) * innerHeight;
	}

	function linePath(values: number[], maximum: number): string {
		return values
			.map((value, index) => `${index === 0 ? 'M' : 'L'} ${x(index, values.length).toFixed(2)} ${y(value, maximum).toFixed(2)}`)
			.join(' ');
	}

	function tickIndexes(count: number, target: number): number[] {
		if (count <= 0) return [];
		if (count === 1) return [0];
		return Array.from(new Set(Array.from({ length: target }, (_, index) => Math.round((index / (target - 1)) * (count - 1)))));
	}

	function compact(value: number): string {
		return new Intl.NumberFormat('en-US', {
			notation: value >= 1_000 ? 'compact' : 'standard',
			maximumFractionDigits: value >= 1_000 ? 1 : 0
		}).format(value);
	}

	function timeLabel(value: string): string {
		const date = new Date(value);
		if (Number.isNaN(date.getTime())) return '';
		const first = buckets[0] ? new Date(buckets[0].start).getTime() : 0;
		const second = buckets[1] ? new Date(buckets[1].start).getTime() : first;
		if (second - first >= 20 * 60 * 60 * 1_000) {
			return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
		}
		return date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
	}
</script>

<figure class="throughput-figure" aria-labelledby="throughput-title">
	<div class="throughput-heading">
		<div>
			<h2 id="throughput-title">Request &amp; token throughput</h2>
			<p>{windowLabel}</p>
		</div>
		<div class="throughput-key" aria-label="Chart series">
			<span><i class="series-line requests"></i>Requests</span>
			<span><i class="series-line tokens"></i>Tokens</span>
		</div>
	</div>

	<div class="throughput-chart" bind:this={container}>
		{#if buckets.length === 0}
			<div class="chart-empty">No requests were recorded in this window.</div>
		{:else}
			<svg viewBox={`0 0 ${chartWidth} ${chartHeight}`} role="img" aria-label={`Requests and tokens over ${windowLabel.toLowerCase()}`}>
				{#each [0, 0.25, 0.5, 0.75, 1] as ratio}
					<line class="chart-gridline" x1={margin.left} x2={chartWidth - margin.right} y1={margin.top + innerHeight * ratio} y2={margin.top + innerHeight * ratio}></line>
					<text class="axis-label request-axis" x={margin.left - 10} y={margin.top + innerHeight * ratio + 4} text-anchor="end">{compact(maxRequests * (1 - ratio))}</text>
					<text class="axis-label token-axis" x={chartWidth - margin.right + 10} y={margin.top + innerHeight * ratio + 4}>{compact(maxTokens * (1 - ratio))}</text>
				{/each}
				<text class="axis-title request-axis" x={margin.left} y={12}>Requests</text>
				<text class="axis-title token-axis" x={chartWidth - margin.right} y={12} text-anchor="end">Tokens</text>
				<line class="chart-baseline" x1={margin.left} x2={chartWidth - margin.right} y1={margin.top + innerHeight} y2={margin.top + innerHeight}></line>
				{#each xTicks as index}
					<text class="axis-label x-axis" x={x(index)} y={chartHeight - 14} text-anchor={index === 0 ? 'start' : index === buckets.length - 1 ? 'end' : 'middle'}>{timeLabel(buckets[index].start)}</text>
				{/each}
				<path class="series-path token-path" d={tokenPath}></path>
				<path class="series-path request-path" d={requestPath}></path>
			</svg>
		{/if}
	</div>

	{#if latest}
		<figcaption>
			Latest bucket: <strong>{latest.requests.toLocaleString()} requests</strong> and
			<strong>{latest.usage.total_tokens.toLocaleString()} tokens</strong>.
		</figcaption>
	{/if}
</figure>

<style>
	.throughput-figure { margin: 0; min-width: 0; }
	.throughput-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--space-lg); margin-bottom: var(--space-md); }
	.throughput-heading h2 { margin: 0 0 2px; font-size: var(--font-size-base); color: var(--color-text-primary); }
	.throughput-heading p, figcaption { margin: 0; color: var(--color-text-secondary); font-size: var(--font-size-xs); }
	.throughput-key { display: flex; align-items: center; gap: var(--space-lg); font-size: var(--font-size-xs); color: var(--color-text-secondary); }
	.throughput-key span { display: inline-flex; align-items: center; gap: 6px; }
	.series-line { display: inline-block; width: 22px; height: 3px; border-radius: 2px; }
	.series-line.requests { background: var(--color-accent); }
	.series-line.tokens { background: var(--color-highlight-gold); }
	.throughput-chart { min-height: 270px; width: 100%; position: relative; }
	.throughput-chart svg { display: block; width: 100%; height: 270px; overflow: visible; }
	.chart-empty { height: 230px; display: grid; place-items: center; color: var(--color-text-secondary); font-size: var(--font-size-sm); border-top: 1px solid var(--color-gray-200); }
	.chart-gridline { stroke: var(--color-gray-200); stroke-width: 1; }
	.chart-baseline { stroke: var(--color-gray-300); stroke-width: 1; }
	.axis-label { fill: var(--color-text-secondary); font-size: 11px; font-family: var(--font-family-base); }
	.axis-title { font-size: 11px; font-weight: var(--font-weight-semibold); font-family: var(--font-family-base); }
	.request-axis { fill: var(--color-accent); }
	.token-axis { fill: #b86d00; }
	.series-path { fill: none; stroke-width: 2.25; stroke-linecap: round; stroke-linejoin: round; vector-effect: non-scaling-stroke; }
	.request-path { stroke: var(--color-accent); }
	.token-path { stroke: var(--color-highlight-gold); }
	figcaption { margin-top: var(--space-xs); }
	figcaption strong { color: var(--color-text-primary); font-weight: var(--font-weight-semibold); }
	@media (max-width: 560px) {
		.throughput-heading { align-items: stretch; flex-direction: column; gap: var(--space-sm); }
		.throughput-key { justify-content: flex-start; }
		.throughput-chart, .throughput-chart svg { min-height: 245px; height: 245px; }
	}
</style>
