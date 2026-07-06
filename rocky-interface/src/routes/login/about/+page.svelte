<svelte:head>
	<title>About Rocky</title>
	<meta
		name="description"
		content="Learn more about the Rocky platform and its features."
	/>
</svelte:head>

<script lang="ts">
	import '$lib/styles/routes/modules/about-view.css';
    import { goto } from '$app/navigation';

	function goBack() {
		goto('/login');
	}
</script>
<div class="about-background">
    <div class="about-card">

        <div class="about-header">
            <img
                class="about-logo"
                src="/ksu_horizontal_blue.png"
                alt="Kent State University"
            />

            <h1>About Rocky</h1>

            <p>
                Rocky is a web-based platform that provides students and instructors
                with secure access to AI-powered tools for coursework and software
                development projects.
            </p>
        </div>

        <div class="about-content">

            <p>
                Students can join courses, generate API keys for approved projects,
                and interact with AI models through Rocky's built-in chat interface.
                API keys are managed by instructors and can be configured with usage
                limits for individual users or projects.
            </p>

            <h2>Key Features</h2>

            <ul>
                <li>Secure account authentication</li>
                <li>Course and project management</li>
                <li>Instructor-managed API key generation</li>
                <li>Configurable API key usage limits</li>
                <li>Integrated AI chat interface</li>
                <li>Modern web-based dashboard</li>
            </ul>

        </div>

        <div class="about-footer">
            <a class="back-button" href="/login">
                ← Back to Login
            </a>
        </div>

    </div>
</div>