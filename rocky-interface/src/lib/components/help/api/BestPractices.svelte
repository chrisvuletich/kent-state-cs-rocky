<script lang="ts">
</script>

<div class="api-doc">
	<h1>API Best Practices</h1>

	<p class="api-doc-lead">
		Following these best practices will help keep your Rocky applications secure,
		reliable, and easy to maintain.
	</p>

	<section class="api-doc-section">
		<h2>Keep Your API Key Secure</h2>

		<p>
			Your API key identifies your application when communicating with Rocky.
			Never share your API key publicly or include it in source control.
		</p>

		<pre><code>{`// ❌ Don't do this
const apiKey = "abc123xyz";

// ✅ Better
const apiKey = process.env.ROCKY_API_KEY;
`}</code></pre>
	</section>

	<section class="api-doc-section">
		<h2>Validate API Responses</h2>

		<p>
			Always check that a request completed successfully before using the data
			returned by the API.
		</p>

		<pre><code>{`if (response.ok) {
    const data = await response.json();
    console.log(data);
} else {
    console.error("Request failed.");
}`}</code></pre>
	</section>

	<section class="api-doc-section">
		<h2>Handle Errors Gracefully</h2>

		<p>
			Network issues and server errors can happen. Make sure your application
			handles these situations without crashing.
		</p>

		<ul>
			<li>Check HTTP status codes.</li>
			<li>Display helpful error messages.</li>
			<li>Retry requests only when appropriate.</li>
		</ul>
	</section>

	<section class="api-doc-section">
		<h2>Protect Sensitive Information</h2>

		<p>
			Only request the information your application needs, and avoid storing
			sensitive data unless absolutely necessary.
		</p>

		<ul>
			<li>Never expose API keys in client-side code.</li>
			<li>Use HTTPS for all API requests.</li>
			<li>Rotate API keys if they become compromised.</li>
		</ul>
	</section>

	<section class="api-doc-section">
		<h2>Next Steps</h2>

		<p>
			You're now ready to explore the Rocky API in more detail.
		</p>

		<ul>
			<li>Browse the API Reference.</li>
			<li>Experiment with the Python and JavaScript examples.</li>
			<li>Start building your own Rocky integrations.</li>
		</ul>
	</section>
</div>
