<script lang="ts">
	import { IconBook2, IconCalendarEvent, IconCode } from '@tabler/icons-svelte';

	export let onSelectPrompt: (prompt: string) => void;

	const prompts = [
		{
			title: 'Explain a concept',
			description: 'Get a clear explanation and examples',
			prompt: 'Explain recursion with a simple Python example.',
			icon: IconBook2
		},
		{
			title: 'Debug my code',
			description: 'Work through an error step by step',
			prompt: 'Help me debug this code. I expected it to do the following:',
			icon: IconCode
		},
		{
			title: 'Plan a study session',
			description: 'Create a focused plan for your next topic',
			prompt: 'Help me plan a study session for my upcoming computer science exam.',
			icon: IconCalendarEvent
		}
	];
</script>

<section class="chat-welcome" aria-labelledby="chat-welcome-title">
	<div class="chat-welcome-copy">
		<h2 id="chat-welcome-title">How can I help you learn today?</h2>
		<p>Ask about programming, coursework, debugging, or study planning.</p>
	</div>

	<div class="chat-starters" aria-label="Suggested prompts">
		{#each prompts as prompt}
			<button type="button" class="chat-starter" onclick={() => onSelectPrompt(prompt.prompt)}>
				<span class="chat-starter-icon" aria-hidden="true">
					<svelte:component this={prompt.icon} size={22} stroke={1.8} />
				</span>
				<span class="chat-starter-copy">
					<strong>{prompt.title}</strong>
					<span>{prompt.description}</span>
				</span>
			</button>
		{/each}
	</div>
</section>
