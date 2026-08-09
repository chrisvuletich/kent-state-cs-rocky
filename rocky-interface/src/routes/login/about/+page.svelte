<script lang="ts">
	import '$lib/styles/routes/modules/about-view.css';
</script>

<svelte:head>
	<title>About Rocky</title>
	<meta name="description" content="Learn more about the Rocky platform and its features." />
</svelte:head>
<div class="about-background">
	<div class="about-card">
		<div class="about-header">
			<img class="about-logo" src="/ksu_horizontal_blue.png" alt="Kent State University" />

			<h1>About Rocky</h1>

			<p>
				Rocky is a web-based platform that provides students and instructors with secure access to
				AI-powered tools for coursework and software development projects.
			</p>
		</div>

		<div class="about-content">
			<p>
				Instructors add students to course rosters. Enrolled students can generate API keys for
				coursework and interact with the available AI model through Rocky's built-in chat interface.
				Requests are logged so administrators can understand usage and review appropriate use.
			</p>

			<h2>Key Features</h2>

			<ul>
				<li>Secure account authentication</li>
				<li>Course and project management</li>
				<li>Course-scoped API key generation</li>
				<li>Administrative request and usage review</li>
				<li>Integrated AI chat interface</li>
				<li>Modern web-based dashboard</li>
			</ul>
		</div>

		<div class="about-footer">
			<a class="back-button" href="/login"> ← Back to Login </a>
		</div>
	</div>
</div>
