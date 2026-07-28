<script lang="ts">
	import ViewShell from '$lib/components/ViewShell.svelte';
	import { currentFrame } from '$lib/stores/frameStore';
	import { page } from '$app/state';
	import type { HelpResource } from '$lib/types/help';
	import PythonExample from '$lib/components/help/api/PythonExample.svelte';
	import WhatIsApi from '$lib/components/help/api/WhatIsApi.svelte';
	import ApiKeyGuide from '$lib/components/help/api/ApiKeyGuide.svelte';
	import JavaScriptExample from '$lib/components/help/api/JavaScriptExample.svelte';
	import BestPractices from '$lib/components/help/api/BestPractices.svelte';
	import ApiReference from '$lib/components/help/api/ApiReference.svelte';
	import CurlExample from '$lib/components/help/api/CurlExample.svelte';
	import CourseRosterGuide from '$lib/components/help/documentation/CourseRosterGuide.svelte';
	import UserManagementGuide from '$lib/components/help/documentation/UserManagementGuide.svelte';
	import ApiKeyManagementGuide from '$lib/components/help/documentation/ApiKeyManagementGuide.svelte';
	import AdminDashboardGuide from '$lib/components/help/documentation/AdminDashboardGuide.svelte';

	import {
		IconHelpCircle,
		IconKey,
		IconBrandPython,
		IconBrandJavascript,
		IconShieldCheck,
		IconBook2,
		IconInfoCircle,
		IconUsers,
		IconLayoutDashboard
	} from '@tabler/icons-svelte';

	const documentationComponents = {
		intro: WhatIsApi,
		apikey: ApiKeyGuide,
		python: PythonExample,
		javascript: JavaScriptExample,
		curl: CurlExample,
		'best-practices': BestPractices,
		reference: ApiReference
	} as const;

	const documentationOrder: ApiDocumentation[] = [
		'intro',
		'apikey',
		'python',
		'curl',
		'javascript',
		'best-practices',
		'reference'
	];

	$: currentIndex = documentationOrder.indexOf(selectedDocumentation);

	type DocumentationPage = Exclude<ApiDocumentation, 'home'>;

	$: previousDocumentation =
		(currentIndex > 0
			? documentationOrder[currentIndex - 1]
			: null) as DocumentationPage | null;

	$: nextDocumentation =
		(currentIndex < documentationOrder.length - 1
			? documentationOrder[currentIndex + 1]
			: null) as DocumentationPage | null;

	const documentationTitles: Record<DocumentationPage, string> = {
		intro: 'Getting Started',
		apikey: 'API Keys',
		python: 'Python Example',
		curl: 'curl Example',
		javascript: 'JavaScript Example',
		'best-practices': 'Best Practices',
		reference: 'API Reference'
	};

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
			title: 'Getting Started',
			description: 'Learn the fundamentals of APIs, requests, responses, and authentication.',
			action: 'Read Guide',
			icon: IconHelpCircle
		},
		{
			id: 'apikey',
			title: 'API Keys',
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
			id: 'curl',
			title: 'curl Example',
			description: 'Send a copyable Rocky API request from a terminal.',
			action: 'View Example',
			icon: IconBrandJavascript
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

	type AdministrationGuide = 'user-management' | 'api-key-management' | 'admin-dashboard';
	type AdministrationGuideCard = {
		id: 'course-roster' | AdministrationGuide;
		title: string;
		description: string;
		icon: typeof IconHelpCircle;
	};

	const administrationGuides: AdministrationGuideCard[] = [
		{ id: 'course-roster', title: 'Course Roster Workflow', description: 'Learn how to edit a course roster, add students manually, import a Canvas CSV, and confirm enrollment.', icon: IconBook2 },
		{ id: 'user-management', title: 'User Management', description: 'Manage users, search accounts, update roles, activate or deactivate accounts, and perform bulk user management.', icon: IconUsers },
		{ id: 'api-key-management', title: 'Managing API Keys', description: 'View, search, filter, activate, deactivate, and manage API keys for users and courses.', icon: IconKey },
		{ id: 'admin-dashboard', title: 'Admin Dashboard', description: 'Learn how to use the dashboard, analytics, audit logs, system metrics, and other administrative tools.', icon: IconLayoutDashboard }
	];

	const administrationGuideTitles: Record<AdministrationGuide, string> = {
		'user-management': 'User Management',
		'api-key-management': 'Managing API Keys',
		'admin-dashboard': 'Admin Dashboard'
	};

	const administrationGuideComponents = {
		'user-management': UserManagementGuide,
		'api-key-management': ApiKeyManagementGuide,
		'admin-dashboard': AdminDashboardGuide
	} as const;

	const administrationGuideOrder: AdministrationGuide[] = ['user-management', 'api-key-management', 'admin-dashboard'];

	$: administrationCurrentIndex = selectedAdministrationGuide ? administrationGuideOrder.indexOf(selectedAdministrationGuide) : -1;
	$: previousAdministrationGuide = administrationCurrentIndex > 0 ? administrationGuideOrder[administrationCurrentIndex - 1] : null;
	$: nextAdministrationGuide = administrationCurrentIndex >= 0 && administrationCurrentIndex < administrationGuideOrder.length - 1 ? administrationGuideOrder[administrationCurrentIndex + 1] : null;

	type ApiDocumentation =
		| 'home'
		| 'intro'
		| 'apikey'
		| 'python'
		| 'curl'
		| 'javascript'
		| 'best-practices'
		| 'reference';

	let selectedDocumentation: ApiDocumentation = 'home';
	let isCourseWorkflowOpen = false;
	let selectedAdministrationGuide: AdministrationGuide | null = null;
	$: canViewAdministrationGuides = page.data.currentUser?.isAdmin || page.data.currentUser?.role === 'instructor';

	$: currentDocumentation =
		selectedDocumentation !== 'home'
			? documentationComponents[selectedDocumentation]
			: null;
	$: currentAdministrationGuide = selectedAdministrationGuide ? administrationGuideComponents[selectedAdministrationGuide] : null;

	function handleResourceClick(event: MouseEvent, isInternal: boolean) {
		if (isInternal) {
			event.preventDefault();
			$currentFrame = 'dashboard';
		}
	}

	function openDocumentation(page: ApiDocumentation) {
		isCourseWorkflowOpen = false;
		selectedAdministrationGuide = null;
		selectedDocumentation = page;

		document.querySelector('.app-content')?.scrollTo({
			top: 0,
			behavior: 'smooth'
		});
	}

	function openCourseWorkflow() {
		selectedAdministrationGuide = null;
		isCourseWorkflowOpen = true;
		document.querySelector('.app-content')?.scrollTo({ top: 0, behavior: 'smooth' });
	}

	function openAdministrationGuide(guide: AdministrationGuide) {
		isCourseWorkflowOpen = false;
		selectedDocumentation = 'home';
		selectedAdministrationGuide = guide;
		document.querySelector('.app-content')?.scrollTo({ top: 0, behavior: 'smooth' });
	}
</script>

<ViewShell title="Help Center">
	{#if selectedDocumentation === 'home' && !isCourseWorkflowOpen && !selectedAdministrationGuide}
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
								on:click={() => openDocumentation(doc.id)}
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
					<button
						class="support-btn support-btn-primary"
						on:click={() => openDocumentation('intro')}
					>
						Start Here
					</button>
				</div>

			</div>
	</section>

	{#if canViewAdministrationGuides}
		<section class="section help-section">
			<div class="section-header">
				<h2>Administration Guides</h2>
			</div>

			<div class="section-content">
				<div class="api-card-grid">
					{#each administrationGuides as guide}
						<button type="button" class="api-card" on:click={() => guide.id === 'course-roster' ? openCourseWorkflow() : openAdministrationGuide(guide.id)}>
							<div class="api-card-icon">
								<svelte:component this={guide.icon} size={40} stroke={1.75} />
							</div>
							<h4>{guide.title}</h4>
							<p>{guide.description}</p>
							<span class="api-card-link">View Guide →</span>
						</button>
					{/each}
				</div>
			</div>
		</section>
	{/if}

	{:else if isCourseWorkflowOpen}
		<section class="section">
			<div class="documentation-header">
				<button class="support-btn support-btn-secondary" on:click={() => (isCourseWorkflowOpen = false)}>
					← Back to Help Center
				</button>
			</div>
			<div class="section-content">
				<CourseRosterGuide />
			</div>
		</section>
	{:else if selectedAdministrationGuide}
		<section class="section">
			<div class="documentation-header">
				<button class="support-btn support-btn-secondary" on:click={() => (selectedAdministrationGuide = null)}>
					← Back to Administration Guides
				</button>
			</div>
			<div class="section-content">
				<svelte:component this={currentAdministrationGuide} />
			</div>
			<div class="documentation-navigation">
				{#if previousAdministrationGuide}
					<button class="documentation-nav-card" on:click={() => openAdministrationGuide(previousAdministrationGuide)}><span class="documentation-nav-label">← Previous</span><strong>{administrationGuideTitles[previousAdministrationGuide]}</strong></button>
				{:else}<div></div>{/if}
				{#if nextAdministrationGuide}
					<button class="documentation-nav-card documentation-nav-next" on:click={() => openAdministrationGuide(nextAdministrationGuide)}><span class="documentation-nav-label">Continue →</span><strong>{administrationGuideTitles[nextAdministrationGuide]}</strong></button>
				{/if}
			</div>
		</section>
	{:else}
		<section class="section">
		<div class="documentation-header">
			<button
				class="support-btn support-btn-secondary"
				on:click={() => (selectedDocumentation = 'home')}
			>
				← Back to Developer Resources
			</button>
		</div>
			<div class="section-content">
				<svelte:component this={currentDocumentation} />
			</div>
			<div class="documentation-navigation">
				{#if previousDocumentation}
					<button
						class="documentation-nav-card"
						on:click={() => openDocumentation(previousDocumentation)}
					>
						<span class="documentation-nav-label">← Previous</span>
						<strong>{documentationTitles[previousDocumentation]}</strong>
					</button>
				{:else}
					<div></div>
				{/if}

				{#if nextDocumentation}
					<button
						class="documentation-nav-card documentation-nav-next"
						on:click={() => openDocumentation(nextDocumentation)}
					>
						<span class="documentation-nav-label">Continue →</span>
						<strong>{documentationTitles[nextDocumentation]}</strong>
					</button>
				{/if}

			</div>
		</section>
	{/if}

</ViewShell>
