<script lang="ts">
	import '$lib/styles/routes/views/chat.css';
	import { onDestroy, onMount, tick } from 'svelte';
	import ChatComposer from '$lib/components/chat/ChatComposer.svelte';
	import ChatHeader from '$lib/components/chat/ChatHeader.svelte';
	import ChatHistoryPanel from '$lib/components/chat/ChatHistoryPanel.svelte';
	import ChatMessageList from '$lib/components/chat/ChatMessageList.svelte';
	import ChatStatusNotice from '$lib/components/chat/ChatStatusNotice.svelte';
	import ChatWelcome from '$lib/components/chat/ChatWelcome.svelte';
	import { conversationLabel } from '$lib/chat/conversations';
	import {
		chatExceptionFailure,
		chatHttpFailure,
		isAbortError,
		type ChatFailure
	} from '$lib/chat/errors';
	import { pendingChatConversationId } from '$lib/stores/chatNavigationStore';
	import type { ChatAvailability, ChatConversation, ChatMessage } from '$lib/types/chat';

	let input = '';
	let messages: ChatMessage[] = [];
	let conversationId = '';
	let conversations: ChatConversation[] = [];
	let loadingConversations = false;
	let loadingConversationId = '';
	let conversationListError = '';
	let sending = false;
	let exporting = false;
	let historyCollapsed = false;
	let errorMessage = '';
	let noticeTone: 'error' | 'info' = 'error';
	let failedMessage: ChatMessage | null = null;
	let availability: ChatAvailability = 'checking';
	let messageList: ChatMessageList;
	let composer: ChatComposer;
	let historyPanel: ChatHistoryPanel;
	let chatHeader: ChatHeader;
	let isMobile = false;
	let conversationRequest: AbortController | null = null;
	let generationRequest: AbortController | null = null;
	let unsubscribePendingConversation: (() => void) | null = null;
	let availabilityTimer: ReturnType<typeof setInterval> | null = null;
	let mobileMediaQuery: MediaQueryList | null = null;

	$: activeConversation = conversations.find(
		(conversation) => conversation.conversation_id === conversationId
	);
	$: conversationTitle = activeConversation ? conversationLabel(activeConversation) : '';

	function messageId(): string {
		return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
	}

	function userFacingError(payload: unknown, fallback: string): string {
		if (payload && typeof payload === 'object' && 'error' in payload) {
			const error = (payload as { error?: unknown }).error;
			if (typeof error === 'string' && error.trim()) return error.trim();
			if (error && typeof error === 'object' && 'message' in error) {
				const message = (error as { message?: unknown }).message;
				if (typeof message === 'string' && message.trim()) return message.trim();
			}
		}
		return fallback;
	}

	async function checkAvailability(showChecking = false) {
		if (showChecking) availability = 'checking';
		try {
			const response = await fetch('/api/server-health', { cache: 'no-store' });
			const payload = await response.json().catch(() => null);
			const services = Array.isArray(payload?.services) ? payload.services : [];
			const requiredServices = ['granite', 'chat-api', 'ollama'];
			availability = requiredServices.every((name) =>
				services.some(
					(service: { name?: string; ok?: boolean }) => service.name === name && service.ok
				)
			)
				? 'available'
				: 'unavailable';
		} catch {
			availability = 'unavailable';
		}
	}

	async function sendMessage() {
		const userMessage = input;
		if (!userMessage.trim() || sending) return;
		let requestPersisted = false;
		let requestFailure: ChatFailure | null = null;
		let stoppedRequest = false;
		let stoppedNotice = '';
		const request = new AbortController();
		generationRequest = request;

		const optimisticMessage: ChatMessage = {
			id: messageId(),
			role: 'user',
			content: userMessage,
			createdAt: new Date().toISOString(),
			state: 'sending'
		};

		messages = [...messages, optimisticMessage];
		input = '';
		errorMessage = '';
		noticeTone = 'error';
		failedMessage = null;
		sending = true;
		await composer?.resetHeight();
		await tick();
		messageList?.scrollToBottom('smooth');

		try {
			const response = await fetch('/api/chat', {
				method: 'POST',
				signal: request.signal,
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					message: userMessage,
					...(conversationId ? { conversation_id: conversationId } : {})
				})
			});

			const data = await response.json().catch(() => null);
			if (request.signal.aborted) {
				const abortError = new Error('The response was stopped.');
				abortError.name = 'AbortError';
				throw abortError;
			}
			if (typeof data?.conversation_id === 'string') conversationId = data.conversation_id;
			requestPersisted = data?.message_stored === true;
			if (!response.ok || typeof data?.output_text !== 'string' || !data.output_text.trim()) {
				if (conversationId) await loadConversations(false);
				requestFailure = chatHttpFailure(response.status, data);
				throw new Error(requestFailure.message);
			}

			messages = messages.map((message) =>
				message.id === optimisticMessage.id
					? { ...message, state: 'sent', persisted: true }
					: message
			);
			messages = [
				...messages,
				{
					id: messageId(),
					role: 'assistant',
					content: data.output_text,
					createdAt: new Date().toISOString(),
					state: 'sent'
				}
			];

			availability = 'available';
			await loadConversations(false);
		} catch (error) {
			const failure = isAbortError(error)
				? chatExceptionFailure(error)
				: requestFailure || chatExceptionFailure(error);
			if (failure.kind === 'stopped') {
				stoppedRequest = true;
				stoppedNotice = failure.message;
				messages = messages.filter((message) => message.id !== optimisticMessage.id);
				failedMessage = null;
				errorMessage = failure.message;
				noticeTone = 'info';
				return;
			}
			const failed = {
				...optimisticMessage,
				state: 'failed' as const,
				persisted: requestPersisted
			};
			messages = messages.map((message) =>
				message.id === optimisticMessage.id ? failed : message
			);
			failedMessage = failed;
			errorMessage = failure.message;
			noticeTone = 'error';
			if (failure.markUnavailable) availability = 'unavailable';
		} finally {
			if (generationRequest === request) {
				generationRequest = null;
				sending = false;
			}
			if (stoppedRequest) {
				await loadConversations(false);
				if (conversationId) await loadConversation(conversationId);
				if (!errorMessage) errorMessage = stoppedNotice;
			}
			await tick();
			messageList?.scrollToBottom('smooth');
		}
	}

	function stopGeneration() {
		generationRequest?.abort();
	}

	async function restoreFailedMessage() {
		if (!failedMessage || sending) return;
		const retryText = failedMessage.content;
		if (!failedMessage.persisted) {
			messages = messages.filter((message) => message.id !== failedMessage?.id);
		}
		failedMessage = null;
		errorMessage = '';
		noticeTone = 'error';
		input = retryText;
		await composer?.focus();
	}

	async function loadConversations(showLoading = true) {
		if (showLoading) loadingConversations = true;
		conversationListError = '';
		try {
			const response = await fetch('/api/chat/conversations', { method: 'POST' });
			const data = await response.json().catch(() => null);
			if (!response.ok || !Array.isArray(data?.conversations)) {
				throw new Error(userFacingError(data, 'Unable to load conversations.'));
			}
			conversations = data.conversations;
		} catch (error) {
			conversationListError =
				error instanceof Error ? error.message : 'Unable to load conversations.';
		} finally {
			loadingConversations = false;
		}
	}

	async function loadConversation(selectedConversationId: string) {
		if (!selectedConversationId || sending) return;
		conversationRequest?.abort();
		const request = new AbortController();
		conversationRequest = request;
		errorMessage = '';
		noticeTone = 'error';
		loadingConversationId = selectedConversationId;

		try {
			const response = await fetch(`/api/chat/conversations/${selectedConversationId}`, {
				method: 'POST',
				signal: request.signal
			});
			const data = await response.json().catch(() => null);
			if (!response.ok) throw new Error(userFacingError(data, 'Unable to load conversation.'));

			conversationId = selectedConversationId;
			messages = Array.isArray(data?.messages)
				? data.messages
						.filter(
							(message: { role?: unknown; content?: unknown }) =>
								(message.role === 'user' || message.role === 'assistant') &&
								typeof message.content === 'string'
						)
						.map(
							(message: {
								message_id?: string;
								role: 'user' | 'assistant';
								content: string;
								created_at?: string;
								status?: 'sent' | 'failed' | 'pending';
							}) => ({
								id: message.message_id || messageId(),
								role: message.role,
								content: message.content,
								createdAt: message.created_at,
								state:
									message.status && message.status !== 'sent'
										? ('failed' as const)
										: ('sent' as const),
								persisted: true
							})
						)
				: [];
			failedMessage =
				[...messages]
					.reverse()
					.find((message) => message.role === 'user' && message.state === 'failed') || null;
			if (isMobile) historyCollapsed = true;
			await tick();
			if (isMobile) chatHeader?.focusHistoryButton();
			messageList?.scrollToTop();
		} catch (error) {
			if (error instanceof DOMException && error.name === 'AbortError') return;
			errorMessage = error instanceof Error ? error.message : 'Unable to load conversation.';
		} finally {
			if (conversationRequest === request) loadingConversationId = '';
		}
	}

	async function newConversation() {
		conversationRequest?.abort();
		conversationId = '';
		messages = [];
		input = '';
		errorMessage = '';
		noticeTone = 'error';
		failedMessage = null;
		if (isMobile) historyCollapsed = true;
		await composer?.resetHeight();
		await composer?.focus();
	}

	async function selectStarterPrompt(prompt: string) {
		input = prompt;
		await composer?.focus();
	}

	async function exportConversation() {
		if (!conversationId || exporting) return;
		exporting = true;
		errorMessage = '';
		noticeTone = 'error';
		try {
			const response = await fetch('/api/chat/export', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ conversation_id: conversationId, format: 'markdown' })
			});
			if (!response.ok) {
				const data = await response.json().catch(() => null);
				throw new Error(userFacingError(data, 'Export failed.'));
			}

			const blob = await response.blob();
			const url = URL.createObjectURL(blob);
			const link = document.createElement('a');
			link.href = url;
			link.download = `rocky-conversation-${conversationId}.md`;
			document.body.appendChild(link);
			link.click();
			link.remove();
			URL.revokeObjectURL(url);
		} catch (error) {
			errorMessage = error instanceof Error ? error.message : 'Unable to export conversation.';
		} finally {
			exporting = false;
		}
	}

	async function openHistory() {
		historyCollapsed = false;
		if (isMobile) {
			await tick();
			historyPanel?.focusCloseButton();
		}
	}

	async function toggleHistory() {
		const wasOpen = !historyCollapsed;
		historyCollapsed = !historyCollapsed;
		if (isMobile && wasOpen) {
			await tick();
			chatHeader?.focusHistoryButton();
		}
	}

	function handleWindowKeydown(event: KeyboardEvent) {
		if (event.key === 'Escape' && isMobile && !historyCollapsed) {
			event.preventDefault();
			void toggleHistory();
		}
	}

	function handleVisibilityChange() {
		if (document.visibilityState === 'visible') void checkAvailability();
	}

	onMount(() => {
		mobileMediaQuery = window.matchMedia('(max-width: 900px)');
		const handleViewportChange = (event: MediaQueryListEvent) => {
			isMobile = event.matches;
			historyCollapsed = event.matches;
		};
		isMobile = mobileMediaQuery.matches;
		historyCollapsed = isMobile;
		mobileMediaQuery.addEventListener('change', handleViewportChange);
		void loadConversations();
		void checkAvailability(true);
		availabilityTimer = setInterval(() => void checkAvailability(), 30_000);
		document.addEventListener('visibilitychange', handleVisibilityChange);
		unsubscribePendingConversation = pendingChatConversationId.subscribe(
			(selectedConversationId) => {
				if (!selectedConversationId) return;
				pendingChatConversationId.set(null);
				void loadConversation(selectedConversationId);
			}
		);

		return () => {
			mobileMediaQuery?.removeEventListener('change', handleViewportChange);
			document.removeEventListener('visibilitychange', handleVisibilityChange);
		};
	});

	onDestroy(() => {
		conversationRequest?.abort();
		generationRequest?.abort();
		unsubscribePendingConversation?.();
		if (availabilityTimer) clearInterval(availabilityTimer);
	});
</script>

<svelte:window onkeydown={handleWindowKeydown} />

<div class:chat-layout-history-collapsed={historyCollapsed} class="chat-layout">
	<ChatHistoryPanel
		bind:this={historyPanel}
		{conversations}
		activeConversationId={conversationId}
		loading={loadingConversations}
		{loadingConversationId}
		busy={sending}
		error={conversationListError}
		collapsed={historyCollapsed}
		onNewChat={newConversation}
		onSelectConversation={loadConversation}
		mobile={isMobile}
		onToggle={toggleHistory}
	/>

	<section
		class="chat-workspace"
		aria-label="Chat workspace"
		inert={isMobile && !historyCollapsed}
		aria-hidden={isMobile && !historyCollapsed ? 'true' : undefined}
	>
		<ChatHeader
			bind:this={chatHeader}
			{conversationTitle}
			{availability}
			canExport={Boolean(conversationId)}
			{exporting}
			onOpenHistory={openHistory}
			onExport={exportConversation}
		/>

		<div class="chat-content">
			{#if messages.length === 0 && !sending}
				<ChatWelcome onSelectPrompt={selectStarterPrompt} />
			{:else}
				<ChatMessageList bind:this={messageList} {messages} {sending} />
			{/if}

			<div class="chat-bottom-region">
				<ChatStatusNotice
					message={errorMessage}
					tone={noticeTone}
					canRetry={Boolean(failedMessage)}
					onRetry={restoreFailedMessage}
					onDismiss={() => (errorMessage = '')}
				/>
				<ChatComposer
					bind:this={composer}
					bind:value={input}
					{sending}
					onSend={sendMessage}
					onStop={stopGeneration}
				/>
			</div>
		</div>
	</section>
</div>
