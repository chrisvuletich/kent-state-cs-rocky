<script lang="ts">
	import ViewShell from '$lib/components/ViewShell.svelte';
	import MarkdownDocumentation from '$lib/components/help/MarkdownDocumentation.svelte';
	import { goto } from '$app/navigation';
	import { appHref, buildAppUrl } from '$lib/navigation/appRoute';
	import {
		canViewDocumentation,
		documentation,
		documentsForCategory,
		type DocumentationCategory,
		type DocumentationDocument
	} from '$lib/documentation/registry';
	import { page } from '$app/stores';
	import type { HelpResource } from '$lib/types/help';
	import {
		IconHelpCircle,
		IconKey,
		IconBrandPython,
		IconBrandJavascript,
		IconShieldCheck,
		IconBook2,
		IconInfoCircle,
		IconUsers,
		IconLayoutDashboard,
		IconTerminal2,
		IconMail,
		IconAlertCircle,
		IconBolt,
		IconPhoto
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

	const icons: Record<string, typeof IconHelpCircle> = {
		intro: IconHelpCircle,
		apikey: IconKey,
		'best-practices': IconShieldCheck,
		reference: IconBook2,
		errors: IconAlertCircle,
		python: IconBrandPython,
		javascript: IconBrandJavascript,
		curl: IconTerminal2,
		streaming: IconBolt,
		'image-input': IconPhoto,
		'email-scam-detector': IconMail,
		'course-roster': IconBook2,
		'user-management': IconUsers,
		'api-key-management': IconKey,
		'admin-dashboard': IconLayoutDashboard
	};
	const documentationIcon = (documentId: string) => icons[documentId] || IconHelpCircle;

	const developerResources = documentsForCategory('developer');
	const exampleCode = documentsForCategory('examples');
	let administrationGuides: DocumentationDocument[] = [];

	$: administrationGuides = documentsForCategory('administration').filter((document) =>
		canViewDocumentation(document, $page.data.currentUser)
	);
	$: canViewAdministrationGuides = administrationGuides.length > 0;
	$: selectedDocumentation = $page.url.searchParams.get('doc')?.trim() || null;
	$: requestedDocumentation =
		documentation.find((document) => document.id === selectedDocumentation) ?? null;
	$: currentDocumentation =
		requestedDocumentation && canViewDocumentation(requestedDocumentation, $page.data.currentUser)
			? requestedDocumentation
			: null;
	$: documentationSequence = currentDocumentation
		? documentsForCategory(currentDocumentation.category).filter((document) =>
				canViewDocumentation(document, $page.data.currentUser)
			)
		: [];
	$: currentIndex = currentDocumentation
		? documentationSequence.findIndex((document) => document.id === currentDocumentation.id)
		: -1;
	$: previousDocumentation = currentIndex > 0 ? documentationSequence[currentIndex - 1] : null;
	$: nextDocumentation =
		currentIndex >= 0 && currentIndex < documentationSequence.length - 1
			? documentationSequence[currentIndex + 1]
			: null;

	async function openDocumentation(id: string) {
		await goto(buildAppUrl($page.url, { frame: 'help', documentId: id }), {
			noScroll: true,
			keepFocus: true
		});
		document.querySelector('.app-content')?.scrollTo({ top: 0, behavior: 'smooth' });
	}

	async function backToDocumentation() {
		await goto(buildAppUrl($page.url, { frame: 'help' }), {
			noScroll: true,
			keepFocus: true
		});
		document.querySelector('.app-content')?.scrollTo({ top: 0, behavior: 'smooth' });
	}

	function backLabel(category: DocumentationCategory) {
		if (category === 'administration') return 'Administration Guides';
		if (category === 'examples') return 'Example Code';
		return 'Developer Resources';
	}
</script>

<svelte:head>
	<title
		>{currentDocumentation
			? `${currentDocumentation.title} | Rocky Help`
			: 'Help Center | Rocky'}</title
	>
</svelte:head>

<ViewShell title={currentDocumentation?.title ?? 'Help Center'}>
	{#if !currentDocumentation}
		<section class="section section-flat help-section-first">
			<div class="section-header"><h2>Other Resources</h2></div>
			<div class="section-content">
				<p class="section-text">
					Quick links to our most commonly used support channels and training materials.
				</p>
				<div class="help-resource-grid">
					{#each resources as resource}
						<a
							href={resource.isInternalRoute
								? appHref($page.url, { frame: 'dashboard' })
								: resource.href}
							class="help-resource-card"
						>
							<p class="help-resource-label">{resource.label}</p>
							<strong class="help-resource-description">{resource.description}</strong>
							<span class="help-resource-action">{resource.action} →</span>
						</a>
					{/each}
				</div>
			</div>
		</section>

		<section class="section section-flat help-section">
			<div class="api-docs">
				<h2>Developer Resources</h2>
				<p>Learn how to integrate Rocky into your applications and use the API.</p>
				<div class="api-card-grid">
					{#each developerResources as document}
						<button type="button" class="api-card" on:click={() => openDocumentation(document.id)}>
							<div class="api-card-icon">
								<svelte:component this={documentationIcon(document.id)} size={40} stroke={1.75} />
							</div>
							<h3>{document.title}</h3>
							<p>{document.description}</p>
							<span class="api-card-link"
								>{document.id === 'reference'
									? 'View Reference'
									: document.id === 'best-practices'
										? 'Read Tips'
										: document.id === 'intro'
											? 'Read Guide'
											: 'View Guide'} →</span
							>
						</button>
					{/each}
				</div>
				<div class="api-callout">
					<div class="api-callout-icon"><IconInfoCircle size={30} stroke={2} /></div>
					<div class="api-callout-content">
						<h3>New to APIs?</h3>
						<p>
							Start with <strong>Getting Started</strong> to learn the basics, then continue to
							<strong>API Keys</strong> before trying an example.
						</p>
					</div>
					<button
						class="support-btn support-btn-primary"
						on:click={() => openDocumentation('intro')}>Start Here</button
					>
				</div>
			</div>
		</section>

		<section class="section section-flat help-section">
			<div class="section-header"><h2>Example Code</h2></div>
			<div class="section-content">
				<div class="api-card-grid">
					{#each exampleCode as document}
						<button type="button" class="api-card" on:click={() => openDocumentation(document.id)}>
							<div class="api-card-icon">
								<svelte:component this={documentationIcon(document.id)} size={40} stroke={1.75} />
							</div>
							<h3>{document.title}</h3>
							<p>{document.description}</p>
							<span class="api-card-link">View Example →</span>
						</button>
					{/each}
				</div>
			</div>
		</section>

		{#if canViewAdministrationGuides}
			<section class="section section-flat help-section">
				<div class="section-header"><h2>Administration Guides</h2></div>
				<div class="section-content">
					<div class="api-card-grid">
						{#each administrationGuides as document}
							<button
								type="button"
								class="api-card"
								on:click={() => openDocumentation(document.id)}
							>
								<div class="api-card-icon">
									<svelte:component this={documentationIcon(document.id)} size={40} stroke={1.75} />
								</div>
								<h3>{document.title}</h3>
								<p>{document.description}</p>
								<span class="api-card-link">View Guide →</span>
							</button>
						{/each}
					</div>
				</div>
			</section>
		{/if}

		<section class="section section-flat help-section" id="release-notes">
			<div class="section-header"><h2>Release Notes</h2></div>
			<div class="section-content">
				<article class="release-note-card">
					<h3>Current release</h3>
					<ul>
						<li>Responses and model-list endpoints for student projects.</li>
						<li>Incremental streaming for the API and built-in chat.</li>
						<li>Bounded JPEG, PNG, and WebP input for supported vision models.</li>
						<li>Course-scoped API key creation and management.</li>
						<li>Built-in chat, administrative analytics, and audit history.</li>
					</ul>
				</article>
			</div>
		</section>
	{:else}
		<section class="section section-flat">
			<div class="documentation-header">
				<button class="support-btn support-btn-secondary" on:click={backToDocumentation}
					>← Back to {backLabel(currentDocumentation.category)}</button
				>
			</div>
			<div class="section-content">
				{#key currentDocumentation.id}<MarkdownDocumentation
						sourcePath={currentDocumentation.path}
						documentTitle={currentDocumentation.title}
					/>{/key}
			</div>
			<div class="documentation-navigation">
				{#if previousDocumentation}<button
						class="documentation-nav-card"
						on:click={() => openDocumentation(previousDocumentation.id)}
						><span class="documentation-nav-label">← Previous</span><strong
							>{previousDocumentation.title}</strong
						></button
					>{:else}<div></div>{/if}
				{#if nextDocumentation}<button
						class="documentation-nav-card documentation-nav-next"
						on:click={() => openDocumentation(nextDocumentation.id)}
						><span class="documentation-nav-label">Continue →</span><strong
							>{nextDocumentation.title}</strong
						></button
					>{/if}
			</div>
		</section>
	{/if}
</ViewShell>
