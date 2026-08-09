<script lang="ts">
	import { browser } from '$app/environment';
	import { page } from '$app/state';
	import { onMount } from 'svelte';
	import { currentFrame, frameMap, frameTitles } from '$lib/stores/frameStore';
	import { canAccessFrame, type FrameName } from '$lib/types/frame';
	import CourseComposerPopover from '$lib/components/CourseComposerPopover.svelte';
	import '$lib/styles/foundation/global.css';

	let currentUser = $derived(page.data.currentUser);
	let hasMounted = $state(false);
	let resolvedFrame = $derived((hasMounted ? $currentFrame : page.data.initialFrame) as FrameName);
	let ActiveView = $derived(frameMap[resolvedFrame]);

	onMount(() => {
		hasMounted = true;
	});

	$effect(() => {
		if (browser && !currentUser) {
			window.location.href = '/login';
		}
	});

	$effect(() => {
		if (!browser || !currentUser) {
			return;
		}

		const isAdmin = currentUser.isAdmin ?? false;
		if (!canAccessFrame($currentFrame, isAdmin)) {
			currentFrame.set(page.data.initialFrame);
		}
	});

	$effect(() => {
		const requestedDocumentation = page.url.searchParams.get('doc')?.trim();
		if (browser && hasMounted && requestedDocumentation && $currentFrame !== 'help') {
			currentFrame.set('help');
		}
	});

	$effect(() => {
		const requestedFrame = page.url.searchParams.get('frame')?.trim() as FrameName | undefined;
		if (
			browser &&
			hasMounted &&
			requestedFrame &&
			canAccessFrame(requestedFrame, currentUser?.isAdmin ?? false) &&
			$currentFrame !== requestedFrame
		) {
			currentFrame.set(requestedFrame);
		}
	});
</script>

<svelte:head>
	<title>{frameTitles[resolvedFrame]} | Rocky</title>
</svelte:head>

{#if currentUser}
	<div class:chat-page-layout={resolvedFrame === 'chat'} class="page-layout">
		<CourseComposerPopover />
		<div class:chat-page-main={resolvedFrame === 'chat'} class="main-content">
			<div class="view-wrapper">
				<ActiveView />
			</div>
		</div>
	</div>
{/if}
