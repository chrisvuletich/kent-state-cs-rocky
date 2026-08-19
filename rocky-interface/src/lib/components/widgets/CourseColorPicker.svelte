<script lang="ts">
	import '$lib/styles/components/modules/course-color-picker.css';

	export let value = '#2b5aa6';
	export let labelledBy: string | undefined;

	const presetColors = [
		'#c2410c',
		'#dc2626',
		'#db2777',
		'#9333ea',
		'#6d28d9',
		'#4f46e5',
		'#1d4ed8',
		'#0ea5e9',
		'#0891b2',
		'#0d9488',
		'#16a34a',
		'#84cc16',
		'#d97706',
		'#ea580c',
		'#e11d48'
	];

	let draftColor = value;
	let lastValue = value;
	let applyMessage = '';

	$: if (value !== lastValue) {
		draftColor = value;
		lastValue = value;
	}

	function selectColor(color: string) {
		draftColor = color;
	}

	function applyColor() {
		if (!isValidHex(draftColor)) {
			return;
		}

		value = draftColor;
		lastValue = value;
		applyMessage = 'Color applied. Click Save Course to save changes.';

		setTimeout(() => {
			applyMessage = '';
		}, 2500);
	}

	function cancelColor() {
		draftColor = value;
	}

	function isValidHex(color: string) {
		return /^#[0-9A-Fa-f]{6}$/.test(color);
	}
</script>

<div class="course-color-picker">
	<div class="color-grid" role="group" aria-label="Course color presets">
		{#each presetColors as color}
			<button
				type="button"
				class="color-swatch"
				class:is-selected={draftColor.toLowerCase() === color.toLowerCase()}
				style={`background-color: ${color};`}
				onclick={() => selectColor(color)}
				aria-label={`Select color ${color}`}
			></button>
		{/each}
	</div>

	<div class="color-code-row">
		<div
			class="color-preview"
			style={`background-color: ${isValidHex(draftColor) ? draftColor : value};`}
		></div>

		<input
			class="text-input color-code-input"
			type="text"
			bind:value={draftColor}
			placeholder="#2b5aa6"
			aria-labelledby={labelledBy}
			aria-label={labelledBy ? undefined : 'Course color hex value'}
			aria-invalid={!isValidHex(draftColor) ? 'true' : undefined}
			aria-describedby={!isValidHex(draftColor) ? `${labelledBy}-error` : undefined}
		/>
	</div>
	{#if !isValidHex(draftColor)}
		<p id={`${labelledBy}-error`} class="field-error" role="alert">
			Enter a six-digit hex color such as #2b5aa6.
		</p>
	{/if}

	<div class="color-picker-actions">
		<button
			type="button"
			class="view-btn"
			disabled={!isValidHex(draftColor) || draftColor === value}
			onclick={applyColor}>Apply Color</button
		>
	</div>
	{#if applyMessage}
		<p class="color-apply-message">{applyMessage}</p>
	{/if}
</div>
