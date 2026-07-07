<script lang="ts">
	import ViewShell from '$lib/components/ViewShell.svelte';
	import { currentFrame } from '$lib/stores/frameStore';
	import type { HelpDocument, HelpResource } from '$lib/types/help';
	import PythonExample from '$lib/components/help/api/PythonExample.svelte';
	import WhatIsApi from '$lib/components/help/api/WhatIsApi.svelte';
	import ApiKeyGuide from '$lib/components/help/api/ApiKeyGuide.svelte';
	import JavaScriptExample from '$lib/components/help/api/JavaScriptExample.svelte';
	import BestPractices from '$lib/components/help/api/BestPractices.svelte';
	import ApiReference from '$lib/components/help/api/ApiReference.svelte';

	import {
		IconHelpCircle,
		IconKey,
		IconBrandPython,
		IconBrandJavascript,
		IconShieldCheck,
		IconBook2,
		IconInfoCircle
	} from '@tabler/icons-svelte';

	const resources: HelpResource[] = [
		{
			label: 'Kent State FlashLine',
			description: 'Quick access to your KSU student portal and tools.',
			action: 'Open FlashLine',
			href: 'https://flashline.kent.edu',
			isInternalRoute: false
		},
		{
			label: 'Report a Problem',
			description: 'If the system misbehaves, tell us about it.',
			action: 'Send an email',
			href: 'mailto:RockySupport@kent.edu',
			isInternalRoute: false
		},
		{
			label: 'Release Notes',
			description: 'Check out the latest updates and system features.',
			action: 'View Notes',
			href: '#release-notes',
			isInternalRoute: false
		},
		{
			label: 'Ready to go?',
			description: 'Done learning? Head back to the dashboard.',
			action: 'Back to Dashboard',
			href: '#',
			isInternalRoute: true
		}
	];

	type ApiDocCard = {
		id: ApiDocumentation;
		title: string;
		description: string;
		action: string;
		icon: typeof IconHelpCircle;
	};

	const apiDocs: ApiDocCard[] = [
		{
			id: 'intro',
			title: 'What is an API?',
			description: 'Learn the fundamentals of APIs, requests, responses, and authentication.',
			action: 'Read Guide',
			icon: IconHelpCircle
		},
		{
			id: 'apikey',
			title: 'Getting Your API Key',
			description: 'Generate and manage your Rocky API key.',
			action: 'View Guide',
			icon: IconKey
		},
		{
			id: 'python',
			title: 'Python Example',
			description: 'Make your first Rocky API request using Python.',
			action: 'View Example',
			icon: IconBrandPython
		},
		{
			id: 'javascript',
			title: 'JavaScript Example',
			description: 'Connect to the Rocky API using JavaScript.',
			action: 'View Example',
			icon: IconBrandJavascript
		},
		{
			id: 'best-practices',
			title: 'Best Practices',
			description: 'Keep your API keys secure and use the API responsibly.',
			action: 'Read Tips',
			icon: IconShieldCheck
		},
		{
			id: 'reference',
			title: 'API Reference',
			description: 'Browse endpoints, parameters, and response formats.',
			action: 'View Reference',
			icon: IconBook2
		}
	];

	type ApiDocumentation =
		| 'home'
		| 'intro'
		| 'apikey'
		| 'python'
		| 'javascript'
		| 'best-practices'
		| 'reference';

	let selectedDocumentation: ApiDocumentation = 'home';

	const helpFiles: HelpDocument[] = [
		{ title: 'User Management Guide', category: 'Administrators', date: '2026-03-21', status: 'Updated', url: '#' },
		{ title: 'Course Creation Workflow', category: 'Instructors', date: '2026-02-15', status: 'Current', url: '#' },
		{ title: 'Analytics Dashboard Overview', category: 'General', date: '2026-01-10', status: 'Current', url: '#' },
		{ title: 'System Roles & Permissions', category: 'Security', date: '2025-11-28', status: 'Current', url: '#' },
		{ title: 'Troubleshooting Common Errors', category: 'Support', date: '2026-03-22', status: 'New', url: '#' }
	];

	function handleResourceClick(event: MouseEvent, isInternal: boolean) {
		if (isInternal) {
			event.preventDefault();
			$currentFrame = 'dashboard';
		}
	}
</script>

<ViewShell title="Help Center">
	{#if selectedDocumentation === 'home'}
	<section class="section">
		<div class="section-header">
			<h2>Other Resources</h2>
		</div>

		<div class="section-content">
			<p class="section-text">Quick links to our most commonly used support channels and training materials.</p>

			<div class="help-resource-grid">
				{#each resources as resource}
					<a href={resource.href} on:click={(e) => handleResourceClick(e, resource.isInternalRoute)} class="help-resource-card">
						<p class="help-resource-label">{resource.label}</p>
						<strong class="help-resource-description">{resource.description}</strong>
						<span class="help-resource-action">{resource.action} -></span>
					</a>
				{/each}
			</div>
		</div>
	</section>

	<section class="section help-section">

			<div class="api-docs">
				<h3>Developer Resources</h3>
				<p>
					Learn how to integrate Rocky into your applications and use the API.
				</p>
				<div class="api-card-grid">
					{#each apiDocs as doc}
						<button type="button"
								class="api-card"
								on:click={() => (selectedDocumentation = doc.id)}
						>
							<div class="api-card-icon">
								<svelte:component this={doc.icon} size={40} stroke={1.75} />
							</div>
							<h4>{doc.title}</h4>
							<p>{doc.description}</p>
							<span class="api-card-link">
								{doc.action} →
							</span>
						</button>
					{/each}
				</div>

				<div class="api-callout">
					<div class="api-callout-icon">
						<IconInfoCircle size={30} stroke={2} />
					</div>
					<div class="api-callout-content">
						<h3>New to APIs?</h3>
						<p>
							Start with <strong>What is an API?</strong> to learn the basics,
							then continue to <strong>Getting Your API Key</strong> before
							trying the <strong>Python Example</strong>.
						</p>
					</div>
					<a href="#" class="support-btn support-btn-primary">
						Start Here
					</a>
				</div>

			</div>
	</section>

	<section class="section help-section">
		<div class="section-header">
			<h2>Documentation</h2>
		</div>

		<div class="section-content">
			<div class="table-container">
				<table class="data-table">
					<thead>
						<tr>
							<th>Document Title</th>
							<th>Category</th>
							<th>Last Updated</th>
							<th>Status</th>
						</tr>
					</thead>
					<tbody>
						{#each helpFiles as file}
							<tr>
								<td>
									<a href={file.url} class="help-doc-link">{file.title}</a>
								</td>
								<td>{file.category}</td>
								<td>{file.date}</td>
								<td>
									<span
										class="help-status-pill"
										class:help-status-new={file.status === 'New'}
										class:help-status-updated={file.status === 'Updated'}
										class:help-status-current={file.status === 'Current'}
									>
										{file.status}
									</span>
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		</div>
	</section>

	{:else if selectedDocumentation === 'intro'}

		<section class="section">

			<button
				class="support-btn support-btn-secondary"
				on:click={() => (selectedDocumentation = 'home')}
			>
				← Back to Developer Resources
			</button>

			<div class="section-content">
				<WhatIsApi />
			</div>

		</section>
	
	{:else if selectedDocumentation === 'apikey'}

		<section class="section">

			<button
				class="support-btn support-btn-secondary"
				on:click={() => (selectedDocumentation = 'home')}
			>
				← Back to Developer Resources
			</button>

			<div class="section-content">
				<ApiKeyGuide />
			</div>

		</section>

	{:else if selectedDocumentation === 'python'}

		<section class="section">

			<button
				class="support-btn support-btn-secondary"
				on:click={() => (selectedDocumentation = 'home')}
			>
				← Back to Developer Resources
			</button>
			<div class="section-content">
				<PythonExample />
			</div>
		</section>

	{:else if selectedDocumentation === 'javascript'}

		<section class="section">

			<button
				class="support-btn support-btn-secondary"
				on:click={() => (selectedDocumentation = 'home')}
			>
				← Back to Developer Resources
			</button>

			<div class="section-content">
				<JavaScriptExample />
			</div>

		</section>
	
	{:else if selectedDocumentation === 'best-practices'}

		<section class="section">

			<button
				class="support-btn support-btn-secondary"
				on:click={() => (selectedDocumentation = 'home')}
			>
				← Back to Developer Resources
			</button>

			<div class="section-content">
				<BestPractices />
			</div>

		</section>

	{:else if selectedDocumentation === 'reference'}

		<section class="section">

			<button
				class="support-btn support-btn-secondary"
				on:click={() => (selectedDocumentation = 'home')}
			>
				← Back to Developer Resources
			</button>

			<div class="section-content">
				<ApiReference />
			</div>

		</section>
	{/if}

</ViewShell>
