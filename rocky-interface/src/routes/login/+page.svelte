<script lang="ts">
	import { browser } from '$app/environment';
	import { replaceState } from '$app/navigation';
	import { onMount } from 'svelte';
	import { ENABLE_MICROSOFT_OAUTH, ENABLE_PREVIEW_AUTH } from '$lib/config/env';
	import { getMicrosoftAuthClient } from '$lib/auth/microsoftClient';
	import '$lib/styles/routes/modules/login-view.css';

	let error: string | null = null;
	let isSigningInWithMicrosoft = false;
	let isProcessingMicrosoftRedirect = false;

	type MicrosoftAuthResponse = {
		idToken?: string;
	};

	async function establishSessionFromMicrosoftLogin(
		loginResponse: MicrosoftAuthResponse
	): Promise<void> {
		if (!loginResponse.idToken) {
			throw new Error('Microsoft login returned no identity token.');
		}

		const sessionResponse = await fetch('/auth/microsoft/login', {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json'
			},
			body: JSON.stringify({ idToken: loginResponse.idToken })
		});

		if (!sessionResponse.ok) {
			const payload = (await sessionResponse
				.json()
				.catch(() => ({ error: 'Unable to sign in with Microsoft.' }))) as {
				error?: string;
			};
			throw new Error(payload.error || 'Unable to sign in with Microsoft.');
		}

		window.location.href = '/';
	}

	async function processMicrosoftRedirectResult(): Promise<void> {
		if (!browser || !ENABLE_MICROSOFT_OAUTH || isProcessingMicrosoftRedirect) {
			return;
		}

		isProcessingMicrosoftRedirect = true;

		try {
			const app = await getMicrosoftAuthClient();
			const redirectResponse = await app.handleRedirectPromise();

			if (!redirectResponse) {
				return;
			}

			await establishSessionFromMicrosoftLogin(redirectResponse);
		} catch (err) {
			console.log('[oauth] frontend redirect handling failed', err);

			const maybeCode =
				typeof err === 'object' && err !== null && 'errorCode' in err
					? String((err as { errorCode?: unknown }).errorCode ?? '')
					: '';

			if (maybeCode === 'no_token_request_cache_error') {
				// A stale callback hash or lost request cache can trigger this; clear hash and allow retry.
				const cleanUrl = `${window.location.pathname}${window.location.search}`;
				replaceState(cleanUrl, {});
				error =
					'Microsoft sign-in session expired before callback completed. Please click Sign In again.';
			} else {
				error = err instanceof Error ? err.message : 'Unable to sign in with Microsoft.';
			}
		} finally {
			isProcessingMicrosoftRedirect = false;
		}
	}

	onMount(() => {
		void processMicrosoftRedirectResult();
	});

	async function signInWithMicrosoft(): Promise<void> {
		if (
			!browser ||
			!ENABLE_MICROSOFT_OAUTH ||
			isSigningInWithMicrosoft ||
			isProcessingMicrosoftRedirect
		) {
			return;
		}

		error = null;
		isSigningInWithMicrosoft = true;

		try {
			const app = await getMicrosoftAuthClient();
			await app.loginRedirect({
				scopes: ['openid', 'profile', 'email', 'User.Read'],
				prompt: 'select_account'
			});
		} catch (err) {
			console.log('[oauth] frontend sign-in failed', err);
			error = err instanceof Error ? err.message : 'Unable to sign in with Microsoft.';
			isSigningInWithMicrosoft = false;
		}
	}
</script>

<svelte:head><title>Sign in | Rocky</title></svelte:head>

<div class="login-background">
	<div class="login-overlay">
		<div class="login-shell">
			<section class="login-column">
				<div class="login-top">
					<img src="/ksu_horizontal_blue.png" alt="Kent State University" class="login-ksu-logo" />
					<h1 class="login-title">Sign in to Rocky</h1>
					{#if ENABLE_MICROSOFT_OAUTH}
						<button
							class="login-signin-btn"
							type="button"
							onclick={signInWithMicrosoft}
							disabled={isSigningInWithMicrosoft || isProcessingMicrosoftRedirect}
						>
							{isSigningInWithMicrosoft ? 'Signing In...' : 'Sign In'}
						</button>
					{:else if ENABLE_PREVIEW_AUTH}
						<a class="login-signin-btn" href="/login/preview">Sign In</a>
					{/if}
					{#if error}
						<p class="login-error">{error}</p>
					{/if}
					<p class="login-help-links">
						Forgot your <a href="/login/preview">Username</a> or
						<a href="/login/preview">Password</a>?
					</p>
					<p class="login-help-links">
						<a href="/login/about">About Rocky</a>
					</p>
				</div>

				<div class="login-bottom">
					<p>
						If this is your first time logging in, please visit <a href="https://welcome.kent.edu/"
							>welcome.kent.edu</a
						>.
					</p>
					<p>
						If you need assistance, please visit <a href="https://support.kent.edu/"
							>support.kent.edu</a
						> to chat with the Helpdesk.
					</p>
				</div>
			</section>
		</div>

		<footer class="login-footer">
			<a href="/credits">Credits</a>
			<a href="https://www.kent.edu/privacy-statement#cookies">Privacy and cookies</a>
		</footer>
	</div>
</div>
