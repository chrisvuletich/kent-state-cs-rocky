<script lang="ts">
</script>

<div class="api-doc">
	<h1>API Reference</h1>

	<p class="api-doc-lead">
		The API Reference provides a general overview of the Rocky API, including
		common endpoints, authentication requirements, and example request formats.
	</p>

	<section class="api-doc-section">
		<h2>Base URL</h2>

		<p>
			All requests should be sent to the Rocky API using the appropriate base
			URL.
		</p>

		<pre><code>https://api.rocky.edu/v1/</code></pre>
	</section>

	<section class="api-doc-section">
		<h2>Authentication</h2>

		<p>
			Every request must include a valid API key in the
			<code>Authorization</code> header.
		</p>

		<pre><code>{`Authorization: Bearer YOUR_API_KEY`}</code></pre>
	</section>

	<section class="api-doc-section">
		<h2>Example Endpoint</h2>

		<p>
			The example below demonstrates a request to Rocky's chat endpoint.
		</p>

		<table class="data-table">
			<thead>
				<tr>
					<th>Method</th>
					<th>Endpoint</th>
					<th>Description</th>
				</tr>
			</thead>

			<tbody>
				<tr>
					<td>POST</td>
					<td>/chat</td>
					<td>Send a message to the Rocky assistant.</td>
				</tr>
			</tbody>
		</table>
	</section>

	<section class="api-doc-section">
		<h2>Example Request Body</h2>

		<pre><code>{`{
    "message": "Hello Rocky!"
}`}</code></pre>
	</section>

	<section class="api-doc-section">
		<h2>Example Response</h2>

		<pre><code>{`{
    "reply": "Hello! How can I help you today?"
}`}</code></pre>
	</section>

	<section class="api-doc-section">
		<h2>Next Steps</h2>

		<p>
			Continue exploring the Rocky API using the documentation available in
			the Help Center.
		</p>

		<ul>
			<li>Read the Python Example.</li>
			<li>Read the JavaScript Example.</li>
			<li>Review API Best Practices.</li>
		</ul>
	</section>
</div>