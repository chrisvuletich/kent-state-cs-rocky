<script lang="ts">
</script>

<div class="api-doc">
	<h1>JavaScript Example</h1>

	<p class="api-doc-lead">
		Learn how to make your first request to the Rocky API using modern JavaScript.
	</p>

	<section class="api-doc-section">
		<h2>Requirements</h2>

		<ul>
			<li>A modern browser or Node.js</li>
			<li>Your Rocky API Key</li>
			<li>Basic knowledge of JavaScript</li>
		</ul>
	</section>

	<section class="api-doc-section">
		<h2>Authentication</h2>

		<p>
			Every request to the Rocky API requires an API key. Include your API key
			in the <code>Authorization</code> header using the Bearer format.
		</p>

		<p>
			Keep your API key private. Anyone with access to your key can make
			requests on your behalf.
		</p>
	</section>

	<section class="api-doc-section">
		<h2>Example Request</h2>

		<p>
			The example below sends a simple chat request to the Rocky API using the
			built-in <code>fetch()</code> function.
		</p>

		<pre><code>{`const response = await fetch(
    "https://api.rocky.edu/v1/chat",
    {
        method: "POST",
        headers: {
            "Authorization": "Bearer YOUR_API_KEY",
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            message: "Hello Rocky!"
        })
    }
);

const data = await response.json();

console.log(data);
`}</code></pre>
	</section>

	<section class="api-doc-section">
		<h2>Example Response</h2>

		<p>
			If the request succeeds, Rocky returns a JSON response similar to the
			example below.
		</p>

		<pre><code>{`{
    "reply": "Hello! How can I help you today?"
}`}</code></pre>
	</section>

	<section class="api-doc-section">
		<h2>Next Steps</h2>

		<p>
			Now that you've sent your first JavaScript request, continue exploring
			the Rocky API.
		</p>

		<ul>
			<li>Review the API Reference.</li>
			<li>Read the Best Practices guide.</li>
			<li>Build your first Rocky application.</li>
		</ul>
	</section>
</div>