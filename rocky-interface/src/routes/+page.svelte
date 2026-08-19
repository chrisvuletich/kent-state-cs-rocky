<script lang="ts">
	import { page } from '$app/state';
	import { onMount } from 'svelte';
	import { frameMap, frameTitles } from '$lib/navigation/frameRegistry';
	import type { FrameName } from '$lib/types/frame';
	import CourseComposerPopover from '$lib/components/CourseComposerPopover.svelte';

	let currentUser = $derived(page.data.currentUser);
	let resolvedFrame = $derived(page.data.initialFrame as FrameName);
	let ActiveView = $derived(frameMap[resolvedFrame]);
	let hydrated = $state(false);

	onMount(() => {
		hydrated = true;
	});
</script>

<svelte:head>
	<title>{frameTitles[resolvedFrame]} | Rocky</title>
</svelte:head>

{#if currentUser}
	<div
		class:chat-page-layout={resolvedFrame === 'chat'}
		class="page-layout"
		data-rocky-app-ready={hydrated ? 'true' : undefined}
	>
		<CourseComposerPopover />
		<div class:chat-page-main={resolvedFrame === 'chat'} class="main-content">
			<div class="view-wrapper">
				<ActiveView />
			</div>
		</div>
	</div>
{/if}
