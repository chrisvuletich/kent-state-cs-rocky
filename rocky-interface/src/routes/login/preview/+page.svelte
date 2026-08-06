<script lang="ts">
	import { onMount } from 'svelte';
	import { normalizeUsers, type ApiUser, type User } from '$lib/types/user';
	import '$lib/styles/routes/modules/login-view.css';

	let users: User[] = [];
	let isLoading = true;
	let error: string | null = null;

	onMount(async () => {
		try {
			const response = await fetch('/api/backend/auth/preview-users', {
				method: 'GET',
				headers: {
					Accept: 'application/json'
				}
			});
			if (!response.ok) {
				throw new Error(`Failed to load preview users (${response.status}).`);
			}
			const payload = (await response.json()) as ApiUser[];
			users = normalizeUsers(payload);
		} catch (err) {
			error = err instanceof Error ? err.message : 'Unable to load users.';
		} finally {
			isLoading = false;
		}
	});

	async function enterAsUser(user: User) {
		const response = await fetch('/auth/login', {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json'
			},
			body: JSON.stringify({ email: user.email })
		});

		if (!response.ok) {
			error = 'Unable to create preview session.';
			return;
		}

		window.location.href = '/';
	}
</script>

<div class="login-background">
	<div class="login-overlay login-preview-overlay">
		<section class="preview-shell">
			<header class="preview-header">
				<h1>Login Preview</h1>
				<p>Select a seeded user to test the app without OAuth.</p>
			</header>

			{#if isLoading}
				<div class="preview-state">Loading users...</div>
			{:else if error}
				<div class="preview-state preview-error">{error}</div>
			{:else if users.length === 0}
				<div class="preview-state">No preview users are currently available.</div>
			{:else}
				<div class="preview-user-grid">
					{#each users as user}
						<article class="preview-user-card">
							<h2>{user.displayName}</h2>
							<p>{user.email}</p>
							<span class="preview-role">{user.role}</span>
							<button class="login-signin-btn" type="button" on:click={() => enterAsUser(user)}>Continue as {user.displayName}</button>
						</article>
					{/each}
				</div>
			{/if}

			<a class="preview-back" href="/login">Back to Login</a>
		</section>
	</div>
</div>
