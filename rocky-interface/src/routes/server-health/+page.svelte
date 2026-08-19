<script lang="ts">
	type ServiceHealth = {
		name: string;
		ok: boolean;
		latencyMs: number;
	};

	type HealthReport = {
		ok: boolean;
		services: ServiceHealth[];
	};

	let { data }: { data: { health: HealthReport } } = $props();

	const serviceLabels: Record<string, string> = {
		web: 'Rocky Web',
		backend: 'Backend API',
		granite: 'Granite Bridge',
		'chat-api': 'Chat API',
		ollama: 'Ollama / Gemma'
	};

	function getServiceLabel(name: string): string {
		return serviceLabels[name] ?? name;
	}
</script>

<svelte:head>
	<title>Rocky Server Health</title>
	<meta name="description" content="Current availability of Rocky application services." />
</svelte:head>

<section class="health-page" aria-label="Server health">
	<header class="page-header">
		<div>
			<p class="eyebrow">SYSTEM STATUS</p>
			<h1>Rocky Server Health</h1>
			<p class="description">
				Live availability checks for Rocky's application and model-serving services.
			</p>
		</div>

		<div class:healthy={data.health.ok} class:unhealthy={!data.health.ok} class="overall-status">
			<span class="status-dot"></span>
			<span>{data.health.ok ? 'All systems operational' : 'Service disruption detected'}</span>
		</div>
	</header>

	<section class="summary" aria-label="System health summary">
		<div>
			<span class="summary-label">Overall status</span>
			<strong>{data.health.ok ? 'Operational' : 'Degraded'}</strong>
		</div>

		<div>
			<span class="summary-label">Services checked</span>
			<strong>{data.health.services.length}</strong>
		</div>

		<div>
			<span class="summary-label">Unavailable</span>
			<strong>{data.health.services.filter((service) => !service.ok).length}</strong>
		</div>
	</section>

	<section class="service-list" aria-label="Service status">
		<div class="table-header">
			<span>Service</span>
			<span>Status</span>
			<span>Latency</span>
		</div>

		{#each data.health.services as service}
			<article class="service-row">
				<div class="service-name">
					<span class:healthy-dot={service.ok} class:unhealthy-dot={!service.ok} class="service-dot"
					></span>

					<div>
						<h2>{getServiceLabel(service.name)}</h2>
						<p>{service.name}</p>
					</div>
				</div>

				<div
					class:healthy-text={service.ok}
					class:unhealthy-text={!service.ok}
					class="service-status"
				>
					{service.ok ? 'Operational' : 'Unavailable'}
				</div>

				<div class="latency">{service.latencyMs} ms</div>
			</article>
		{/each}
	</section>

	<footer>
		<p>
			This page checks service reachability. It does not perform a full authenticated chat or
			model-generation test.
		</p>
		<a href="/api/server-health">View raw health response</a>
	</footer>
</section>

<style>
	.health-page {
		width: min(960px, calc(100% - 2rem));
		margin: 0 auto;
		padding: 3rem 0 4rem;
		color: #172033;
	}

	.page-header {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 2rem;
		padding-bottom: 2rem;
		border-bottom: 1px solid #d8dee9;
	}

	.eyebrow {
		margin: 0 0 0.5rem;
		font-size: 0.75rem;
		font-weight: 700;
		letter-spacing: 0.14em;
		color: #5f6b7a;
	}

	h1 {
		margin: 0;
		font-size: clamp(2rem, 5vw, 3.5rem);
		line-height: 1;
		letter-spacing: -0.04em;
	}

	.description {
		max-width: 620px;
		margin: 1rem 0 0;
		color: #5f6b7a;
		line-height: 1.6;
	}

	.overall-status {
		display: inline-flex;
		align-items: center;
		gap: 0.6rem;
		flex-shrink: 0;
		padding: 0.7rem 0.9rem;
		border: 1px solid;
		border-radius: 6px;
		font-size: 0.875rem;
		font-weight: 700;
	}

	.overall-status.healthy {
		color: #17653a;
		background: #edf9f1;
		border-color: #acdcbc;
	}

	.overall-status.unhealthy {
		color: #9d2727;
		background: #fff1f1;
		border-color: #e8b1b1;
	}

	.status-dot {
		width: 0.55rem;
		height: 0.55rem;
		border-radius: 50%;
		background: currentColor;
	}

	.summary {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		margin: 2rem 0;
		border: 1px solid #d8dee9;
		border-radius: 8px;
		overflow: hidden;
	}

	.summary > div {
		padding: 1.25rem;
	}

	.summary > div + div {
		border-left: 1px solid #d8dee9;
	}

	.summary-label {
		display: block;
		margin-bottom: 0.4rem;
		font-size: 0.75rem;
		font-weight: 700;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: #667085;
	}

	.summary strong {
		font-size: 1.25rem;
	}

	.service-list {
		border: 1px solid #d8dee9;
		border-radius: 8px;
		overflow: hidden;
	}

	.table-header,
	.service-row {
		display: grid;
		grid-template-columns: minmax(0, 1fr) 180px 100px;
		align-items: center;
		gap: 1rem;
	}

	.table-header {
		padding: 0.8rem 1rem;
		background: #f5f7fa;
		font-size: 0.75rem;
		font-weight: 700;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: #667085;
	}

	.service-row {
		padding: 1rem;
	}

	.service-row + .service-row {
		border-top: 1px solid #e2e7ef;
	}

	.service-name {
		display: flex;
		align-items: center;
		gap: 0.8rem;
		min-width: 0;
	}

	.service-name h2 {
		margin: 0;
		font-size: 1rem;
	}

	.service-name p {
		margin: 0.2rem 0 0;
		font-family: var(--font-family-monospace);
		font-size: 0.75rem;
		color: #7a8493;
	}

	.service-dot {
		width: 0.65rem;
		height: 0.65rem;
		flex-shrink: 0;
		border-radius: 50%;
	}

	.healthy-dot {
		background: #2d9b57;
		box-shadow: 0 0 0 4px #e4f5e9;
	}

	.unhealthy-dot {
		background: #c93d3d;
		box-shadow: 0 0 0 4px #fbe5e5;
	}

	.service-status {
		font-weight: 700;
		font-size: 0.9rem;
	}

	.healthy-text {
		color: #237645;
	}

	.unhealthy-text {
		color: #b12d2d;
	}

	.latency {
		font-family: var(--font-family-monospace);
		font-size: 0.85rem;
		color: #5f6b7a;
		text-align: right;
	}

	footer {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		margin-top: 1.5rem;
		font-size: 0.8rem;
		color: #667085;
	}

	footer p {
		margin: 0;
	}

	footer a {
		flex-shrink: 0;
		color: inherit;
		font-weight: 700;
	}

	@media (max-width: 700px) {
		.health-page {
			padding-top: 2rem;
		}

		.page-header {
			flex-direction: column;
		}

		.summary {
			grid-template-columns: 1fr;
		}

		.summary > div + div {
			border-top: 1px solid #d8dee9;
			border-left: 0;
		}

		.table-header {
			display: none;
		}

		.service-row {
			grid-template-columns: 1fr auto;
		}

		.latency {
			grid-column: 2;
		}

		footer {
			align-items: flex-start;
			flex-direction: column;
		}
	}
</style>
