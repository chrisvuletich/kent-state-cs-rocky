<script lang="ts">
	import { onDestroy } from 'svelte';

	export let title = 'Key Slot';
	export let keyName = '';
	export let hasExistingKey = false;
	export let maskedPreview = '';
	export let placeholderText = 'No key exists for this slot yet.';
	export let generateDisabled = false;
	export let hideDisabled = false;
	export let removeDisabled = false;
	export let toggleActiveDisabled = false;
	export let showToggleActive = false;
	export let isKeyActive = true;
	export let readOnly = false;
	export let readOnlyMessage = 'Course is closed. Key actions are unavailable.';
	export let slotIdentity = title;
	export let disabledMessage = 'Key: This key is currently disabled for this slot.';
	export let onKeyNameChange: (value: string) => void = () => {};
	export let onGenerate: () => Promise<string | null> | string | null = () => null;
	export let onHide: () => void = () => {};
	export let onRemove: () => Promise<boolean> | boolean = () => true;
	export let onToggleActive: () => void = () => {};

	let visibleKey: string | null = null;
	let lastSlotIdentity = slotIdentity;
	let generatedExists = false;
	let isGenerating = false;
	let isRemoving = false;
	let copyStatus = '';
	let copyStatusTimeout: ReturnType<typeof setTimeout> | null = null;

	$: if (slotIdentity !== lastSlotIdentity) {
		visibleKey = null;
		generatedExists = false;
		lastSlotIdentity = slotIdentity;
	}

	async function handleGenerate() {
		if (
			(hasExistingKey || generatedExists || maskedPreview) &&
			!window.confirm(
				'Regenerating this key will immediately invalidate its current value. Applications using the old key will stop working. Continue?'
			)
		) {
			return;
		}

		isGenerating = true;
		copyStatus = '';
		try {
			const nextKey = await onGenerate();
			visibleKey = typeof nextKey === 'string' && nextKey.trim() ? nextKey.trim() : null;
			if (visibleKey) {
				generatedExists = true;
			}
		} finally {
			isGenerating = false;
		}
	}

	function handleHide() {
		visibleKey = null;
		onHide();
	}

	async function handleRemove() {
		if (
			!window.confirm('Remove this API key? Applications using it will immediately stop working.')
		) {
			return;
		}
		isRemoving = true;
		try {
			const removed = await onRemove();
			if (removed) {
				visibleKey = null;
				generatedExists = false;
				copyStatus = '';
			}
		} finally {
			isRemoving = false;
		}
	}

	async function copyVisibleKey() {
		if (!visibleKey) return;
		try {
			await navigator.clipboard.writeText(visibleKey);
			copyStatus = 'Copied to clipboard.';
		} catch {
			copyStatus = 'Unable to copy automatically. Select and copy the key manually.';
		}
		if (copyStatusTimeout) clearTimeout(copyStatusTimeout);
		copyStatusTimeout = setTimeout(() => (copyStatus = ''), 4000);
	}

	function handleToggleActive() {
		onToggleActive();
	}

	onDestroy(() => {
		if (copyStatusTimeout) clearTimeout(copyStatusTimeout);
		visibleKey = null;
		generatedExists = false;
	});
</script>

<div class="course-panel">
	<h3>{title}</h3>
	{#if readOnly}
		<p><strong>Key Name:</strong> {keyName}</p>
	{:else}
		<div class="course-group-create-row">
			<input
				class="text-input"
				type="text"
				value={keyName}
				placeholder="Key name"
				aria-label={`${title} key name`}
				oninput={(event) => onKeyNameChange((event.currentTarget as HTMLInputElement).value)}
			/>
		</div>
	{/if}
	<p>
		<strong>Key:</strong>
		{#if hasExistingKey || generatedExists || maskedPreview}
			{#if isKeyActive}
				{maskedPreview}
			{:else}
				{disabledMessage}
			{/if}
		{:else}
			{placeholderText}
		{/if}
	</p>
	{#if visibleKey}
		<div class="course-key-reveal">
			<strong
				>Copy this key now. It will not be shown again after you dismiss it or leave this page.</strong
			>
			<code>{visibleKey}</code>
			<div class="course-inline-actions">
				<button type="button" class="list-go-btn" onclick={copyVisibleKey}>Copy API Key</button>
				<button type="button" class="list-go-btn" onclick={handleHide} disabled={hideDisabled}
					>Dismiss</button
				>
			</div>
			{#if copyStatus}<p class="course-key-copy-status" role="status">{copyStatus}</p>{/if}
		</div>
	{/if}
	{#if readOnly}
		<p class="section-text">{readOnlyMessage}</p>
	{:else}
		<div class="course-inline-actions">
			<button
				type="button"
				class="list-go-btn"
				onclick={handleGenerate}
				disabled={generateDisabled || isGenerating || isRemoving}
			>
				{isGenerating
					? 'Working…'
					: hasExistingKey || generatedExists || maskedPreview
						? 'Regenerate Key'
						: 'Generate Key'}
			</button>
			{#if hasExistingKey || visibleKey || maskedPreview}
				<button
					type="button"
					class="list-go-btn"
					onclick={handleRemove}
					disabled={removeDisabled || isGenerating || isRemoving}
					>{isRemoving ? 'Removing…' : 'Remove Key'}</button
				>
			{/if}
			{#if (hasExistingKey || visibleKey || maskedPreview) && showToggleActive}
				<button
					type="button"
					class="list-go-btn"
					onclick={handleToggleActive}
					disabled={toggleActiveDisabled}
				>
					{isKeyActive ? 'Deactivate Key' : 'Activate Key'}
				</button>
			{/if}
		</div>
	{/if}
</div>
