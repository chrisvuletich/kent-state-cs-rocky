<script lang="ts">
</script>

<div class="api-doc">
	<h1>API Reference</h1>
	<p class="api-doc-lead">Reference for Rocky’s current Chat API request and response contract.</p>

	<section class="api-doc-section">
		<h2>Endpoint and authentication</h2>
		<table class="data-table">
			<thead><tr><th>Method</th><th>Default local endpoint</th><th>Authentication</th></tr></thead>
			<tbody><tr><td>POST</td><td><code>http://127.0.0.1:5003/rocky-api</code></td><td>JSON <code>api-key</code> field</td></tr></tbody>
		</table>
		<p>The deployed Chat API host is environment-specific. Rocky does not define a fixed public API domain in code.</p>
	</section>

	<section class="api-doc-section">
		<h2>Simple request parameters</h2>
		<p>Use this form for a single message. History is stored unless <code>store</code> is set to <code>false</code>.</p>
		<table class="data-table">
			<thead><tr><th>Parameter</th><th>Data type</th><th>Required</th><th>Description</th><th>Default</th></tr></thead>
			<tbody>
				<tr><td><code>api-key</code></td><td>string</td><td>Yes</td><td>Active course API key.</td><td>None</td></tr>
				<tr><td><code>message</code></td><td>string</td><td>Yes*</td><td>The user message sent to Rocky.</td><td>None</td></tr>
				<tr><td><code>store</code></td><td>boolean</td><td>No</td><td>Store the exchange and use conversation history.</td><td><code>true</code></td></tr>
				<tr><td><code>conversation_id</code></td><td>string</td><td>No</td><td>Continue a stored conversation owned by the key’s user.</td><td>New conversation</td></tr>
				<tr><td><code>model</code></td><td>string</td><td>No</td><td>Model name forwarded to the generation service.</td><td>Configured server model</td></tr>
				<tr><td><code>temperature</code></td><td>number</td><td>No</td><td>Sampling temperature; accepted range is 0–2.</td><td>Generation-service default</td></tr>
				<tr><td><code>top_p</code></td><td>number</td><td>No</td><td>Nucleus sampling value; accepted range is 0–1.</td><td>Generation-service default</td></tr>
				<tr><td><code>max_output_tokens</code></td><td>integer</td><td>No</td><td>Maximum generated tokens; accepted range is 1–3500.</td><td>Generation-service default</td></tr>
			</tbody>
		</table>
		<p><strong>*</strong> Required when history is stored. A request with <code>store: false</code> may use the advanced <code>input</code> form below instead.</p>
	</section>

	<section class="api-doc-section">
		<h2>Advanced input parameters</h2>
		<p>For a prebuilt message list, set <code>store</code> to <code>false</code> and send <code>input</code> instead of <code>message</code>.</p>
		<table class="data-table">
			<thead><tr><th>Parameter</th><th>Data type</th><th>Required</th><th>Description</th><th>Default</th></tr></thead>
			<tbody>
				<tr><td><code>input</code></td><td>array</td><td>Yes</td><td>Array of message objects passed to the generation service.</td><td>None</td></tr>
				<tr><td><code>input[].role</code></td><td>string</td><td>No</td><td>Message role.</td><td><code>user</code></td></tr>
				<tr><td><code>input[].content</code></td><td>array</td><td>No</td><td>Content blocks for the message.</td><td>Empty array</td></tr>
				<tr><td><code>input[].content[].type</code></td><td>string</td><td>Yes for usable text</td><td>Use <code>input_text</code> for text content.</td><td>None</td></tr>
				<tr><td><code>input[].content[].text</code></td><td>string</td><td>Yes for usable text</td><td>Text sent in an <code>input_text</code> block.</td><td>None</td></tr>
			</tbody>
		</table>
	</section>

	<section class="api-doc-section">
		<h2>Successful response fields</h2>
		<table class="data-table">
			<thead><tr><th>Field</th><th>Data type</th><th>Description</th></tr></thead>
			<tbody>
				<tr><td><code>reply</code></td><td>string</td><td>Rocky’s generated response text.</td></tr>
				<tr><td><code>model</code></td><td>string</td><td>Model reported by the generation service.</td></tr>
				<tr><td><code>metadata</code></td><td>object</td><td>Generation-service metadata.</td></tr>
				<tr><td><code>conversation_id</code></td><td>string</td><td>Stored conversation ID; returned only when history is stored.</td></tr>
			</tbody>
		</table>
	</section>

	<section class="api-doc-section">
		<h2>Error responses and status codes</h2>
		<table class="data-table">
			<thead><tr><th>Status</th><th>Returned fields</th><th>When it occurs</th></tr></thead>
			<tbody>
				<tr><td>200</td><td><code>reply</code>, <code>model</code>, <code>metadata</code>, optional <code>conversation_id</code></td><td>Request completed.</td></tr>
				<tr><td>400</td><td><code>error</code> (string)</td><td>Invalid JSON, missing message, missing chat context, or an invalid request handled as a bad request.</td></tr>
				<tr><td>401</td><td><code>error</code> (string)</td><td>Missing, invalid, inactive, revoked, or expired API key.</td></tr>
				<tr><td>502</td><td><code>error</code> (string)</td><td>Rocky could not contact the generation service or the service returned an unusable response.</td></tr>
			</tbody>
		</table>
	</section>
</div>
