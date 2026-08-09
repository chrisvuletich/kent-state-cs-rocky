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
			localStorage.removeItem('rocky_current_frame');
			localStorage.removeItem('rocky_selected_course');
			document.cookie = 'rocky_current_frame=; Path=/; Max-Age=0; SameSite=Lax';
			await goto('/login', { replaceState: true });
		}
	}
</script>

<svelte:head><title>Signing out | Rocky</title></svelte:head>

<section class="logout-page" aria-live="polite" aria-label="Signing out">
	<p>Signing out of Rocky…</p>
	<noscript><a href="/login">Continue to sign in</a></noscript>
</section>

<style>
	.logout-page {
		display: grid;
		min-height: 100vh;
		place-items: center;
		font:
			1rem/1.5 system-ui,
			sans-serif;
	}
</style>
