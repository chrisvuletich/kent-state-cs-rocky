<script lang="ts">
</script>

<div class="api-doc">
	<h1>Python Example</h1>

	<p class="api-doc-lead">
		Learn how to make your first request to the Rocky API using Python.
	</p>

	<section class="api-doc-section">
		<h2>Requirements</h2>

		<ul>
			<li>Python 3.10 or newer</li>
			<li>The <code>requests</code> library</li>
			<li>Your Rocky API Key</li>
		</ul>
	</section>

	<section class="api-doc-section">
		<h2>Install Dependencies</h2>

		<p>
			Rocky's Python examples use the
			<code>requests</code> library to communicate with the API.
			If you don't already have it installed, run:
    	</p>

		<pre><code>pip install requests</code></pre>
	</section>

	<section class="api-doc-section">
		<h2>Authentication</h2>

		<p>
			Every request to the Rocky API requires an API key. Include it as the
			<code>api-key</code> field in the JSON request body, not as an
			<code>Authorization</code> header.
		</p>

		<p>
			Keep your API key private. Anyone with access to your key can make
			requests on your behalf.
		</p>
	</section>

	<section class="api-doc-section">
		<h2>Example Request</h2>

		<p>
			The example below sends a simple chat request to the Rocky API. Store
			your key in the <code>ROCKY_API_KEY</code> environment variable before
			running the script.
		</p>

	<pre><code>{`import os
import requests

url = "https://rocky.cs.kent.edu/rocky-api"

payload = {
    "api-key": os.environ["ROCKY_API_KEY"],
    "message": "Hello Rocky!",
    "store": False
}

response = requests.post(url, json=payload, timeout=30)
response.raise_for_status()

print(response.json()["reply"])
`}</code></pre>
	</section>

	<section class="api-doc-section">
		<h2>Example Response</h2>

		<p>
			If the request succeeds, Rocky returns a JSON response similar to the
			example below.
		</p>

		<pre><code>{`{
    "reply": "Hello! How can I help you today?",
    "model": "configured-model-name",
    "metadata": { "source": "ollama" }
}`}</code></pre>
	</section>

	<section class="api-doc-section">
		<h2>Next Steps</h2>

		<p>
			Now that you've made your first request, continue exploring the Rocky
			API by reviewing the available documentation.
		</p>

		<ul>
			<li>Generate your API key.</li>
			<li>Read the API Reference.</li>
			<li>Learn authentication best practices.</li>
		    <li>Try the JavaScript example.</li>
		</ul>
	</section>
</div>
