<script lang="ts">
</script>

<div class="api-doc">
	<h1>What is an API?</h1>

	<p class="api-doc-lead">
		An API (Application Programming Interface) allows different software
		applications to communicate with one another. The Rocky API lets your
		application securely send requests and receive data from Rocky.
	</p>

	<section class="api-doc-section">
		<h2>How APIs Work</h2>

		<p>
			When your application needs information, it sends a request to the Rocky
			API. Rocky processes the request and returns a response containing the
			requested data.
		</p>
	</section>

	<section class="api-doc-section">
		<h2>Request and Response</h2>

		<p>
			Every API interaction consists of a request sent by your application and
			a response returned by the server.
		</p>

		<pre><code>{`Request
    ↓
Rocky API
    ↓
Response`}</code></pre>
	</section>

	<section class="api-doc-section">
		<h2>JSON Data</h2>

		<p>
			The Rocky API sends and receives information using JSON
			(JavaScript Object Notation), a lightweight format that is easy for both
			people and computers to read.
		</p>

		<pre><code>{`{
    "message": "Hello Rocky!"
}`}</code></pre>
	</section>

	<section class="api-doc-section">
		<h2>HTTP Methods</h2>

		<p>
			APIs use different HTTP methods depending on the action being performed.
		</p>

		<ul>
			<li><strong>GET</strong> — Retrieve data.</li>
			<li><strong>POST</strong> — Send new data.</li>
			<li><strong>PUT</strong> — Update existing data.</li>
			<li><strong>DELETE</strong> — Remove data.</li>
		</ul>
	</section>

	<section class="api-doc-section">
		<h2>Next Steps</h2>

		<p>
			Now that you understand the basics of APIs, you're ready to begin using
			the Rocky API.
		</p>

		<ul>
			<li>Generate your API key.</li>
			<li>Read the Python example.</li>
			<li>Explore the API Reference.</li>
		</ul>
	</section>
</div>