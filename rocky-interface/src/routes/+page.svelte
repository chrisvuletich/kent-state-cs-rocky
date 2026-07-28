<script lang="ts">
	import { browser } from '$app/environment';
	import { page } from '$app/state';
	import { currentFrame, frameMap } from '$lib/stores/frameStore';
	import { canAccessFrame, type FrameName } from '$lib/types/frame';
	import CourseComposerPopover from '$lib/components/CourseComposerPopover.svelte';
	import '$lib/styles/foundation/global.css';

	let currentUser = $derived(page.data.currentUser);
	let resolvedFrame = $derived((browser ? $currentFrame : page.data.initialFrame) as FrameName);
	let ActiveView = $derived(frameMap[resolvedFrame]);

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
</script>

{#if currentUser}
	<div class="page-layout">
		<CourseComposerPopover />
		<div class="main-content">
			<div class="view-wrapper">
				<ActiveView />
			</div>
		</div>
	</div>
{/if}
