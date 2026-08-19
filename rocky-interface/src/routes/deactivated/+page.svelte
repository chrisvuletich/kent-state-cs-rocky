<svelte:head>
	<title>Account inactive | Rocky</title>
</svelte:head>

<section class="deactivated-page">
	<div class="deactivated-card">
		<p class="deactivated-eyebrow">Rocky AI</p>
		<h1>Your account has been deactivated</h1>
		<p class="deactivated-message">
			You are signed in, but your account is currently inactive. Please contact an administrator if
			you believe this is an error.
		</p>
		<a class="deactivated-action" href="/logout">Sign out and return to sign in</a>
		<p class="deactivated-help">Your current session will be cleared before you sign in again.</p>
	</div>
</section>

<style>
	.deactivated-page {
		display: grid;
		min-height: 100vh;
		place-items: center;
		padding: var(--space-2xl);
		background: linear-gradient(160deg, var(--color-bg-secondary), var(--color-bg-tertiary));
	}

	.deactivated-card {
		width: min(100%, 40rem);
		padding: clamp(1.5rem, 5vw, 2.5rem);
		border: 1px solid var(--color-gray-300);
		border-radius: var(--radius-xl);
		background: var(--color-bg-primary);
		box-shadow: var(--shadow-lg);
		color: var(--color-text-primary);
		text-align: center;
	}

	.deactivated-eyebrow {
		margin-bottom: var(--space-sm);
		color: var(--color-text-accent);
		font-size: var(--font-size-sm);
		font-weight: var(--font-weight-bold);
		letter-spacing: 0.08em;
		text-transform: uppercase;
	}

	.deactivated-card h1 {
		margin: 0 0 var(--space-md);
		font-size: clamp(1.7rem, 5vw, 2.2rem);
		line-height: var(--line-height-tight);
	}

	.deactivated-message {
		color: var(--color-text-secondary);
		line-height: var(--line-height-relaxed);
	}

	.deactivated-action {
		display: inline-flex;
		min-height: 44px;
		align-items: center;
		justify-content: center;
		margin-top: var(--space-xl);
		padding: 0 var(--space-xl);
		border-radius: var(--radius-md);
		background: var(--color-accent);
		color: var(--color-text-inverse);
		font-weight: var(--font-weight-semibold);
		text-decoration: none;
	}

	.deactivated-action:hover {
		filter: brightness(1.08);
	}

	.deactivated-action:focus-visible {
		outline: 3px solid color-mix(in srgb, var(--color-accent) 34%, transparent);
		outline-offset: 3px;
	}

	.deactivated-help {
		margin-top: var(--space-md);
		color: var(--color-text-secondary);
		font-size: var(--font-size-sm);
	}
</style>
