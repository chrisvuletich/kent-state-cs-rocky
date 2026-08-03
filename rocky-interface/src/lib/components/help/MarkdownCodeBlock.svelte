<script lang="ts">
	export let lang: string;
	export let text: string;

	let copied = false;
	let copyError = false;
	let resetTimer: ReturnType<typeof setTimeout>;

	async function copyCode() {
		try {
			await navigator.clipboard.writeText(text);
			copied = true;
			copyError = false;
		} catch {
			copied = false;
			copyError = true;
		}

		clearTimeout(resetTimer);
		resetTimer = setTimeout(() => {
			copied = false;
			copyError = false;
		}, 1500);
	}
</script>

<div class="markdown-code-block">
	<button class="markdown-code-copy" type="button" onclick={copyCode} aria-label="Copy code block">
		{copied ? 'Copied' : copyError ? 'Copy failed' : 'Copy'}
	</button>
	<pre class={lang}><code>{text}</code></pre>
</div>
