<script lang="ts">
</script>

<div class="api-doc">
	<h1>curl Example</h1>
	<p class="api-doc-lead">Use curl to send a Rocky API request from a terminal.</p>

	<section class="api-doc-section">
		<h2>Before you begin</h2>
		<p>Replace the environment-variable value with your own course API key. Keep the key out of shared shell history, code, and screenshots.</p>
	</section>

	<section class="api-doc-section">
		<h2>Send a request</h2>
		<pre><code>{`export ROCKY_API_KEY='replace-with-your-course-api-key'

curl --request POST https://rocky.cs.kent.edu/v1/responses \\
  --header 'Content-Type: application/json' \\
  --data "{
    \\"api-key\\": \\"$ROCKY_API_KEY\\",
    \\"message\\": \\"Explain recursion in one paragraph.\\",
    \\"store\\": false
  }"`}</code></pre>
		<p><code>https://rocky.cs.kent.edu/v1/responses</code> is Rocky’s public Chat API endpoint.</p>
	</section>

	<section class="api-doc-section">
		<h2>Example response</h2>
		<pre><code>{`{
  "reply": "Recursion is a technique where a function solves a problem by calling itself with a smaller version of that problem.",
  "model": "configured-model-name",
  "metadata": {
    "source": "ollama"
  }
}`}</code></pre>
	</section>
</div>
