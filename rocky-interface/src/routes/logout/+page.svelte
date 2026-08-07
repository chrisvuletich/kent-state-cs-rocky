<script lang="ts">
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { ENABLE_MICROSOFT_OAUTH } from '$lib/config/env';
	import { clearMicrosoftAuthCache } from '$lib/auth/microsoftClient';

	onMount(() => {
		void finishLogout();
	});

	async function finishLogout(): Promise<void> {
		try {
			if (ENABLE_MICROSOFT_OAUTH) await clearMicrosoftAuthCache();
		} finally {
			localStorage.removeItem('rocky.currentUser');
			await goto('/login', { replaceState: true });
		}
	}
</script>

<svelte:head><title>Signing out | Rocky</title></svelte:head>

<main class="logout-page" aria-live="polite">
	<p>Signing out of Rocky…</p>
	<noscript><a href="/login">Continue to sign in</a></noscript>
</main>

<style>
	.logout-page {
		display: grid;
		min-height: 100vh;
		place-items: center;
		font: 1rem/1.5 system-ui, sans-serif;
	}
</style>
