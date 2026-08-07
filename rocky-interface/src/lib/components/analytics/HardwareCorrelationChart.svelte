<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import type { AnalyticsHardware, AnalyticsHardwareBucket } from '$lib/types/analytics';

	export let data: AnalyticsHardware;
	export let windowLabel = 'Last 24 hours';
	export let activeRequests = 0;

	let container: HTMLDivElement;
	let width = 760;
	let observer: ResizeObserver | null = null;
	const height = 360;
	const margin = { top: 20, right: 20, bottom: 38, left: 54 };
	const panelHeight = 78;
	const panelGap = 24;

	$: innerWidth = Math.max(1, width - margin.left - margin.right);
	$: speedMax = Math.max(1, ...data.buckets.map((row) => row.workload.generation_tokens_per_second || 0));
	$: latencyMax = Math.max(1, ...data.buckets.map((row) => row.workload.p95_latency_ms || 0));
	$: ticks = tickIndexes(data.buckets.length, width < 520 ? 3 : 5);
	$: latestBucket = [...data.buckets].reverse().find((row) => row.sample_count > 0);

	onMount(() => {
		observer = new ResizeObserver(([entry]) => {
			width = Math.max(300, Math.round(entry.contentRect.width));
		});
		observer.observe(container);
	});

	onDestroy(() => observer?.disconnect());

	function x(index: number): number {
		return margin.left + (data.buckets.length <= 1 ? 0 : (index / (data.buckets.length - 1)) * innerWidth);
	}

	function y(value: number, maximum: number, panel: number): number {
		const top = margin.top + panel * (panelHeight + panelGap);
		return top + panelHeight - (value / maximum) * panelHeight;
	}

	function path(accessor: (row: AnalyticsHardwareBucket) => number | null, maximum: number, panel: number): string {
		let drawing = false;
		return data.buckets.map((row, index) => {
			const value = accessor(row);
			if (value === null || !Number.isFinite(value)) {
				drawing = false;
				return '';
			}
			const command = drawing ? 'L' : 'M';
			drawing = true;
			return `${command} ${x(index).toFixed(2)} ${y(value, maximum, panel).toFixed(2)}`;
		}).join(' ');
	}

	function tickIndexes(count: number, target: number): number[] {
		if (count <= 0) return [];
		if (count === 1) return [0];
		return Array.from(new Set(Array.from({ length: target }, (_, index) => Math.round((index / (target - 1)) * (count - 1)))));
	}

	function timeLabel(value: string): string {
		const date = new Date(value);
		if (Number.isNaN(date.getTime())) return '';
		return data.bucket === 'day'
			? date.toLocaleDateString([], { month: 'short', day: 'numeric' })
			: date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
	}

	function metric(value: number | null | undefined, unit = '%'): string {
		return value === null || value === undefined ? 'N/A' : `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })}${unit}`;
	}

	function bytes(value: number | null | undefined): string {
		if (value === null || value === undefined) return 'N/A';
		const gib = value / 1024 ** 3;
		return `${gib.toLocaleString(undefined, { maximumFractionDigits: 1 })} GiB`;
	}
</script>

<figure class="hardware-figure" aria-labelledby="hardware-title">
	<div class="hardware-heading">
		<div><h2 id="hardware-title">Hardware &amp; model correlation</h2><p>{windowLabel} · {data.sample_count.toLocaleString()} samples · {data.latest?.source.host || 'source unavailable'}{data.latest?.missing.length ? ` · Missing ${data.latest.missing.join(', ')}` : ''}</p></div>
		<span class={`hardware-status ${data.status}`}>{data.status}</span>
	</div>

	<div class="hardware-current" aria-label="Latest hardware snapshot">
		<div><span>GPU utilization</span><strong>{metric(data.latest?.gpu?.utilization_percent)}</strong></div>
		<div><span>VRAM</span><strong>{metric(data.latest?.gpu?.memory_percent)}</strong><small>{bytes(data.latest?.gpu?.memory_used_bytes)} used</small></div>
		<div><span>GPU temperature</span><strong>{metric(data.latest?.gpu?.temperature_c, ' °C')}</strong></div>
		<div><span>CPU / RAM</span><strong>{metric(data.latest?.system?.cpu_percent)} / {metric(data.latest?.system?.memory_percent)}</strong></div>
		<div><span>Current active requests</span><strong>{activeRequests.toLocaleString()}</strong></div>
	</div>

	<div class="hardware-chart" bind:this={container}>
		{#if data.buckets.length === 0 || data.sample_count === 0}
			<div class="hardware-empty">Hardware history is unavailable for this window. Enable the Granite sampler to begin collecting bounded snapshots.</div>
		{:else}
			<svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`GPU utilization, generation speed, and request latency over ${windowLabel.toLowerCase()}`}>
				{#each [0, 1, 2] as panel}
					<line class="hardware-grid" x1={margin.left} x2={width - margin.right} y1={margin.top + panel * (panelHeight + panelGap)} y2={margin.top + panel * (panelHeight + panelGap)}></line>
					<line class="hardware-grid" x1={margin.left} x2={width - margin.right} y1={margin.top + panel * (panelHeight + panelGap) + panelHeight} y2={margin.top + panel * (panelHeight + panelGap) + panelHeight}></line>
				{/each}
				<text class="panel-label gpu" x={margin.left} y={12}>GPU / VRAM %</text>
				<text class="panel-label speed" x={margin.left} y={margin.top + panelHeight + panelGap - 7}>Generation tokens/sec</text>
				<text class="panel-label latency" x={margin.left} y={margin.top + 2 * (panelHeight + panelGap) - 7}>P95 request latency</text>
				<text class="axis-value" x={margin.left - 9} y={margin.top + 4} text-anchor="end">100</text>
				<text class="axis-value" x={margin.left - 9} y={margin.top + panelHeight + 4} text-anchor="end">0</text>
				<text class="axis-value" x={margin.left - 9} y={margin.top + panelHeight + panelGap + 4} text-anchor="end">{speedMax.toFixed(0)}</text>
				<text class="axis-value" x={margin.left - 9} y={margin.top + 2 * (panelHeight + panelGap) + 4} text-anchor="end">{latencyMax >= 1000 ? `${(latencyMax / 1000).toFixed(1)}s` : `${latencyMax.toFixed(0)}ms`}</text>
				<path class="hardware-line gpu-line" d={path((row) => row.hardware.gpu_utilization_percent.average, 100, 0)}></path>
				<path class="hardware-line vram-line" d={path((row) => row.hardware.gpu_memory_percent.average, 100, 0)}></path>
				<path class="hardware-line speed-line" d={path((row) => row.workload.generation_tokens_per_second, speedMax, 1)}></path>
				<path class="hardware-line latency-line" d={path((row) => row.workload.p95_latency_ms, latencyMax, 2)}></path>
				{#each ticks as index}
					<text class="axis-value x" x={x(index)} y={height - 12} text-anchor={index === 0 ? 'start' : index === data.buckets.length - 1 ? 'end' : 'middle'}>{timeLabel(data.buckets[index].start)}</text>
				{/each}
			</svg>
		{/if}
	</div>
	<div class="hardware-key" aria-label="Chart series"><span class="gpu-key">GPU utilization</span><span class="vram-key">VRAM use</span><span class="speed-key">Generation speed</span><span class="latency-key">P95 latency</span></div>
	{#if latestBucket}<figcaption>Latest sampled bucket: {latestBucket.workload.requests.toLocaleString()} requests, {latestBucket.workload.input_tokens.toLocaleString()} prompt tokens, {latestBucket.workload.output_tokens.toLocaleString()} output tokens, {metric(latestBucket.hardware.gpu_temperature_c.maximum, ' °C')} peak GPU temperature, and {metric(latestBucket.workload.load_duration_ms, ' ms')} average model load time.</figcaption>{/if}
</figure>

<style>
	.hardware-figure { margin: 0; min-width: 0; }
	.hardware-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--space-md); }
	.hardware-heading h2 { margin: 0 0 2px; color: var(--color-text-primary); font-size: var(--font-size-base); }
	.hardware-heading p, figcaption { margin: 0; color: var(--color-text-secondary); font-size: var(--font-size-xs); }
	.hardware-status { padding: 3px 8px; border: 1px solid var(--color-gray-300); border-radius: 999px; color: var(--color-text-secondary); font-size: 0.66rem; font-weight: var(--font-weight-semibold); text-transform: capitalize; }
	.hardware-status.live { border-color: #86c99e; color: #15803d; }
	.hardware-status.partial, .hardware-status.stale { border-color: #e1b760; color: #9a5b00; }
	.hardware-status.unavailable { border-color: #e0a090; color: #c2410c; }
	.hardware-current { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); margin-top: var(--space-md); border-block: 1px solid var(--color-gray-200); }
	.hardware-current div { min-width: 0; padding: var(--space-sm) var(--space-md); border-right: 1px solid var(--color-gray-200); }
	.hardware-current div:last-child { border-right: 0; }
	.hardware-current span, .hardware-current small { display: block; color: var(--color-text-secondary); font-size: 0.65rem; }
	.hardware-current strong { display: block; margin-top: 2px; color: var(--color-text-primary); font-size: var(--font-size-sm); }
	.hardware-chart { min-height: 360px; margin-top: var(--space-md); }
	.hardware-chart svg { display: block; width: 100%; height: 360px; overflow: visible; }
	.hardware-empty { min-height: 260px; display: grid; place-items: center; padding: var(--space-xl); color: var(--color-text-secondary); font-size: var(--font-size-sm); text-align: center; }
	.hardware-grid { stroke: var(--color-gray-200); stroke-width: 1; }
	.panel-label { font: var(--font-weight-semibold) 11px var(--font-family-base); }
	.panel-label.gpu { fill: #b86d00; }
	.panel-label.speed { fill: #15803d; }
	.panel-label.latency { fill: var(--color-accent); }
	.axis-value { fill: var(--color-text-secondary); font: 10px var(--font-family-base); }
	.hardware-line { fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; vector-effect: non-scaling-stroke; }
	.gpu-line { stroke: #b86d00; }
	.vram-line { stroke: var(--color-accent); stroke-dasharray: 5 3; }
	.speed-line { stroke: #15803d; }
	.latency-line { stroke: #7c3aed; }
	.hardware-key { display: flex; flex-wrap: wrap; gap: var(--space-md); margin-top: -8px; color: var(--color-text-secondary); font-size: 0.66rem; }
	.hardware-key span::before { content: ''; display: inline-block; width: 16px; height: 2px; margin-right: 5px; vertical-align: middle; background: currentColor; }
	.gpu-key { color: #b86d00; } .vram-key { color: var(--color-accent); } .speed-key { color: #15803d; } .latency-key { color: #7c3aed; }
	figcaption { margin-top: var(--space-sm); line-height: 1.45; }
	@media (max-width: 720px) {
		.hardware-current { grid-template-columns: repeat(2, minmax(0, 1fr)); }
		.hardware-current div { border-bottom: 1px solid var(--color-gray-200); }
		.hardware-current div:nth-child(2n) { border-right: 0; }
		.hardware-current div:last-child { border-bottom: 0; }
	}
</style>
