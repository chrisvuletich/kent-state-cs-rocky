<script lang="ts">
</script>

<div class="api-doc">
	<h1>Getting Your API Key</h1>

	<p class="api-doc-lead">
		Your API key allows your application to securely authenticate with the
		Rocky API. Treat your API key like a password and never share it publicly.
	</p>

	<section class="api-doc-section">
		<h2>What is an API Key?</h2>

		<p>
			An API key is a unique token that identifies your application when it
			communicates with Rocky. Every request to the Rocky API must include a
			valid API key.
		</p>
	</section>

	<section class="api-doc-section">
		<h2>Generate an API Key</h2>

		<p>
			Generate your API key from your Rocky account settings.
		</p>

		<ol>
			<li>Open the <strong>Course</strong> page.</li>
			<li>Select <strong>Home</strong>.</li>
			<li>Click <strong>Generate API Key</strong>.</li>
			<li>Copy and securely store your new API key.</li>
		</ol>
	</section>

	<section class="api-doc-section">
		<h2>Using Your API Key</h2>

		<p>
			Include your API key in the <code>Authorization</code> header using the
			Bearer format.
		</p>

		<pre><code>{`Authorization: Bearer YOUR_API_KEY`}</code></pre>
	</section>

	<section class="api-doc-section">
		<h2>Security Best Practices</h2>

		<ul>
			<li>Never share your API key.</li>
			<li>Do not commit API keys to Git repositories.</li>
			<li>Regenerate your API key if you believe it has been compromised.</li>
			<li>Store API keys in environment variables whenever possible.</li>
		</ul>
	</section>

	<section class="api-doc-section">
		<h2>Next Steps</h2>

		<p>
			Once you have generated your API key, you're ready to make your first
			request to the Rocky API.
		</p>

		<ul>
			<li>Read the Python Example.</li>
			<li>Read the JavaScript Example.</li>
			<li>Explore the API Reference.</li>
		</ul>
	</section>
</div>