<script lang="ts">
	import '$lib/styles/routes/views/chat.css';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
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
	import { consumeRockyResponseStream, RockyResponseStreamError } from '$lib/chat/responseStream';
	import {
		ImageAttachmentError,
		prepareImageAttachments,
		storedChatImages
	} from '$lib/chat/imageAttachments';
	import { buildAppUrl, parseConversationId } from '$lib/navigation/appRoute';
	import type {
		ChatAvailability,
		ChatConversation,
		ChatImage,
		ChatImageLimits,
		ChatMessage
	} from '$lib/types/chat';

	let input = '';
	let images: ChatImage[] = [];
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
	let checkingAvailability = false;
	let messageList: ChatMessageList;
	let composer: ChatComposer;
	let isMobile = false;
	let conversationRequest: AbortController | null = null;
	let generationRequest: AbortController | null = null;
	let availabilityTimer: ReturnType<typeof setInterval> | null = null;
	let rateLimitTimer: ReturnType<typeof setTimeout> | null = null;
	let retryBlocked = false;
	let mobileMediaQuery: MediaQueryList | null = null;
	let streamScrollFrame: number | null = null;
	let imageInputEnabled = false;
	let imageLimits: ChatImageLimits | null = null;
	let addingImages = false;
	let conversationUrlSyncInFlight = '';
	let conversationListRevision = 0;
	let pendingConversationLocation: string | null | undefined;
	let chatCapabilitiesLoaded = false;
	let checkingChatCapabilities = false;

	$: activeConversation = conversations.find(
		(conversation) => conversation.conversation_id === conversationId
	);
	$: conversationTitle = activeConversation ? conversationLabel(activeConversation) : '';
	$: composerDisabled = retryBlocked || availability === 'unavailable';
	$: composerDisabledReason = retryBlocked
		? 'Please wait before trying again.'
		: availability === 'unavailable'
			? 'Rocky AI is temporarily unavailable. Check the service again before sending.'
			: '';

	async function syncConversationUrl(selectedConversationId: string): Promise<void> {
		const normalizedId = parseConversationId(selectedConversationId);
		if (
			!normalizedId ||
			parseConversationId($page.url.searchParams.get('conversation')) === normalizedId ||
			conversationUrlSyncInFlight === normalizedId
		) {
			return;
		}

		conversationUrlSyncInFlight = normalizedId;
		try {
			await goto(buildAppUrl($page.url, { frame: 'chat', conversationId: normalizedId }), {
				replaceState: true,
				noScroll: true,
				keepFocus: true
			});
		} finally {
			if (conversationUrlSyncInFlight === normalizedId) conversationUrlSyncInFlight = '';
		}
	}

	function setConversationId(nextConversationId: string, syncUrl = true): void {
		conversationId = parseConversationId(nextConversationId) || '';
		if (syncUrl && conversationId && pendingConversationLocation === undefined) {
			void syncConversationUrl(conversationId);
		}
	}

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

	function applyRetryCooldown(seconds: number | undefined) {
		if (!seconds) return;
		if (rateLimitTimer) clearTimeout(rateLimitTimer);
		retryBlocked = true;
		rateLimitTimer = setTimeout(() => {
			retryBlocked = false;
			rateLimitTimer = null;
		}, seconds * 1000);
	}

	function cancelStreamScroll() {
		if (streamScrollFrame !== null) cancelAnimationFrame(streamScrollFrame);
		streamScrollFrame = null;
	}

	async function checkAvailability(showChecking = false, forceRefresh = false) {
		if (checkingAvailability) return;
		const previousAvailability = availability;
		checkingAvailability = true;
		if (showChecking && availability !== 'unavailable') availability = 'checking';
		try {
			const healthUrl = forceRefresh ? '/api/server-health?refresh=1' : '/api/server-health';
			const response = await fetch(healthUrl, { cache: 'no-store' });
			const payload = await response.json().catch(() => null);
			const services = Array.isArray(payload?.services) ? payload.services : [];
			const requiredServices = ['granite', 'chat-api', 'ollama'];
			const nextAvailability =
				response.ok &&
				requiredServices.every((name) =>
					services.some(
						(service: { name?: string; ok?: boolean }) => service.name === name && service.ok
					)
				)
					? 'available'
					: 'unavailable';
			availability = nextAvailability;
			if (
				nextAvailability === 'available' &&
				(previousAvailability !== 'available' || !chatCapabilitiesLoaded)
			) {
				await loadChatCapabilities();
			}
		} catch {
			availability = 'unavailable';
		} finally {
			checkingAvailability = false;
		}
	}

	async function loadChatCapabilities() {
		if (checkingChatCapabilities) return;
		checkingChatCapabilities = true;
		try {
			const response = await fetch('/api/chat/capabilities', { cache: 'no-store' });
			const payload = await response.json().catch(() => null);
			const candidate = payload?.imageInput;
			if (!response.ok) {
				chatCapabilitiesLoaded = false;
				imageInputEnabled = false;
				imageLimits = null;
				return;
			}
			chatCapabilitiesLoaded = true;
			if (candidate?.enabled !== true || !candidate?.limits) {
				imageInputEnabled = false;
				imageLimits = null;
				return;
			}
			imageLimits = candidate.limits as ChatImageLimits;
			imageInputEnabled = true;
		} catch {
			chatCapabilitiesLoaded = false;
			imageInputEnabled = false;
			imageLimits = null;
		} finally {
			checkingChatCapabilities = false;
		}
	}

	async function addImages(files: File[]) {
		if (!imageInputEnabled || !imageLimits || sending || addingImages || files.length === 0) return;
		addingImages = true;
		errorMessage = '';
		noticeTone = 'error';
		try {
			const prepared = await prepareImageAttachments(files, images, imageLimits);
			images = [...images, ...prepared];
		} catch (error) {
			errorMessage =
				error instanceof ImageAttachmentError
					? error.message
					: 'Unable to prepare the selected image.';
		} finally {
			addingImages = false;
			await flushPendingConversationLocation();
		}
	}

	function removeImage(imageId: string) {
		if (sending || addingImages) return;
		images = images.filter((image) => image.id !== imageId);
	}

	async function sendMessage() {
		const userMessage = input;
		const userImages = images;
		if (
			(!userMessage.trim() && userImages.length === 0) ||
			sending ||
			addingImages ||
			composerDisabled
		)
			return;
		let requestPersisted = false;
		let requestFailure: ChatFailure | null = null;
		let stoppedRequest = false;
		let stoppedNotice = '';
		let assistantMessageId = '';
		let requestId = '';
		const request = new AbortController();
		generationRequest = request;

		const optimisticMessage: ChatMessage = {
			id: messageId(),
			role: 'user',
			content: userMessage,
			createdAt: new Date().toISOString(),
			state: 'sending',
			images: userImages
		};

		messages = [...messages, optimisticMessage];
		input = '';
		images = [];
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
					...(userImages.length
						? {
								images: userImages.map((image) => ({
									image_url: image.imageUrl,
									detail: 'auto'
								}))
							}
						: {}),
					...(conversationId ? { conversation_id: conversationId } : {})
				})
			});
			requestId =
				response.headers.get('x-request-id') || response.headers.get('x-rocky-request-id') || '';
			const responseConversationId = response.headers.get('x-rocky-conversation-id')?.trim();
			if (responseConversationId) setConversationId(responseConversationId);
			requestPersisted = response.headers.get('x-rocky-message-stored') === 'true';
			if (request.signal.aborted) {
				const abortError = new Error('The response was stopped.');
				abortError.name = 'AbortError';
				throw abortError;
			}
			if (!response.ok) {
				const data = await response.json().catch(() => null);
				if (typeof data?.conversation_id === 'string') setConversationId(data.conversation_id);
				requestPersisted = requestPersisted || data?.message_stored === true;
				if (conversationId) await loadConversations(false);
				requestFailure = chatHttpFailure(response.status, data, {
					retryAfter: response.headers.get('retry-after'),
					requestId
				});
				throw new Error(requestFailure.message);
			}
			const contentType = response.headers.get('content-type')?.toLowerCase() || '';
			if (!contentType.startsWith('text/event-stream')) {
				const data = await response.json().catch(() => null);
				if (typeof data?.output_text !== 'string' || !data.output_text.trim()) {
					requestFailure = chatHttpFailure(
						502,
						{
							error: {
								code: 'invalid_model_response',
								message: 'Rocky AI did not return a valid reply.'
							}
						},
						{ requestId }
					);
					throw new Error(requestFailure.message);
				}
				if (typeof data.conversation_id === 'string') setConversationId(data.conversation_id);
				requestPersisted = requestPersisted || data.message_stored === true;
				messages = messages.map((message) =>
					message.id === optimisticMessage.id
						? { ...message, state: 'sent', persisted: requestPersisted }
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
				return;
			}

			const completed = await consumeRockyResponseStream(response, (outputText) => {
				const shouldFollow = messageList?.isNearBottom() ?? true;
				if (!assistantMessageId) {
					assistantMessageId = messageId();
					messages = [
						...messages,
						{
							id: assistantMessageId,
							role: 'assistant',
							content: outputText,
							createdAt: new Date().toISOString(),
							state: 'streaming'
						}
					];
				} else {
					messages = messages.map((message) =>
						message.id === assistantMessageId ? { ...message, content: outputText } : message
					);
				}
				if (shouldFollow && streamScrollFrame === null) {
					streamScrollFrame = requestAnimationFrame(async () => {
						streamScrollFrame = null;
						await tick();
						messageList?.scrollToBottom('auto');
					});
				}
			});
			if (request.signal.aborted) {
				const abortError = new Error('The response was stopped.');
				abortError.name = 'AbortError';
				throw abortError;
			}

			const completedConversationId = completed.response.conversation_id;
			if (typeof completedConversationId === 'string' && completedConversationId.trim()) {
				setConversationId(completedConversationId);
			}
			requestPersisted = requestPersisted || completed.response.message_stored === true;

			messages = messages.map((message) =>
				message.id === optimisticMessage.id
					? { ...message, state: 'sent', persisted: requestPersisted }
					: message.id === assistantMessageId
						? { ...message, content: completed.outputText, state: 'sent' }
						: message
			);

			availability = 'available';
			await loadConversations(false);
		} catch (error) {
			const caughtError =
				request.signal.aborted && !isAbortError(error)
					? Object.assign(new Error('The response was stopped.'), { name: 'AbortError' })
					: error;
			if (caughtError instanceof RockyResponseStreamError) {
				const status =
					caughtError.code === 'model_timeout'
						? 504
						: caughtError.code === 'model_busy' ||
							  caughtError.code === 'request_logging_unavailable'
							? 503
							: 502;
				requestFailure = chatHttpFailure(
					status,
					{ error: { code: caughtError.code, message: caughtError.message } },
					{ requestId }
				);
			}
			const failure = isAbortError(caughtError)
				? chatExceptionFailure(caughtError)
				: requestFailure || chatExceptionFailure(caughtError);
			if (failure.kind === 'stopped') {
				stoppedRequest = true;
				stoppedNotice = failure.message;
				messages = messages.filter(
					(message) => message.id !== optimisticMessage.id && message.id !== assistantMessageId
				);
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
				message.id === optimisticMessage.id
					? failed
					: message.id === assistantMessageId
						? { ...message, state: 'failed' as const }
						: message
			);
			failedMessage = failed;
			errorMessage = failure.message;
			noticeTone = 'error';
			applyRetryCooldown(failure.retryAfterSeconds);
			if (failure.markUnavailable) availability = 'unavailable';
		} finally {
			if (generationRequest === request) {
				generationRequest = null;
				sending = false;
			}
			const shouldReconcileLocation = pendingConversationLocation !== undefined;
			if (stoppedRequest && !shouldReconcileLocation) {
				await loadConversations(false);
				if (conversationId) await loadConversation(conversationId, false);
				if (!errorMessage) errorMessage = stoppedNotice;
			}
			if (shouldReconcileLocation) await flushPendingConversationLocation();
			await tick();
			messageList?.scrollToBottom('smooth');
		}
	}

	function stopGeneration() {
		generationRequest?.abort();
		cancelStreamScroll();
	}

	async function restoreFailedMessage() {
		if (!failedMessage || sending) return;
		const retryText = failedMessage.content;
		const retryImages = failedMessage.images || [];
		if (!failedMessage.persisted) {
			messages = messages.filter((message) => message.id !== failedMessage?.id);
		}
		failedMessage = null;
		errorMessage = '';
		noticeTone = 'error';
		input = retryText;
		images = [...retryImages];
		await composer?.focus();
	}

	async function loadConversations(showLoading = true) {
		const revision = ++conversationListRevision;
		if (showLoading) loadingConversations = true;
		conversationListError = '';
		try {
			const response = await fetch('/api/chat/conversations', { method: 'POST' });
			const data = await response.json().catch(() => null);
			if (!response.ok || !Array.isArray(data?.conversations)) {
				throw new Error(userFacingError(data, 'Unable to load conversations.'));
			}
			if (revision !== conversationListRevision) return;
			conversations = data.conversations;
		} catch (error) {
			if (revision !== conversationListRevision) return;
			conversationListError =
				error instanceof Error ? error.message : 'Unable to load conversations.';
		} finally {
			if (revision === conversationListRevision) loadingConversations = false;
		}
	}

	function retryConversations() {
		void loadConversations();
	}

	async function loadConversation(selectedConversationId: string, offerFailedRetry = true) {
		if (!selectedConversationId || sending || addingImages) return;
		conversationRequest?.abort();
		const request = new AbortController();
		conversationRequest = request;
		errorMessage = '';
		noticeTone = 'error';
		loadingConversationId = selectedConversationId;

		try {
			const response = await fetch(
				`/api/chat/conversations/${encodeURIComponent(selectedConversationId)}`,
				{
					method: 'POST',
					signal: request.signal
				}
			);
			const data = await response.json().catch(() => null);
			if (!response.ok) throw new Error(userFacingError(data, 'Unable to load conversation.'));

			images = [];
			setConversationId(selectedConversationId, false);
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
								input_images?: unknown;
								created_at?: string;
								status?: 'sent' | 'failed' | 'pending';
							}) => {
								const id = message.message_id || messageId();
								return {
									id,
									role: message.role,
									content: message.content,
									createdAt: message.created_at,
									state:
										message.status && message.status !== 'sent'
											? ('failed' as const)
											: ('sent' as const),
									persisted: true,
									images: storedChatImages(message.input_images, id)
								};
							}
						)
				: [];
			failedMessage = offerFailedRetry
				? [...messages]
						.reverse()
						.find((message) => message.role === 'user' && message.state === 'failed') || null
				: null;
			if (isMobile) historyCollapsed = true;
			await tick();
			messageList?.scrollToTop();
		} catch (error) {
			if (error instanceof DOMException && error.name === 'AbortError') return;
			errorMessage = error instanceof Error ? error.message : 'Unable to load conversation.';
		} finally {
			if (conversationRequest === request) loadingConversationId = '';
		}
	}

	async function resetConversation(focusComposer = true) {
		if (addingImages) return;
		conversationRequest?.abort();
		setConversationId('', false);
		messages = [];
		input = '';
		images = [];
		errorMessage = '';
		noticeTone = 'error';
		failedMessage = null;
		if (isMobile) historyCollapsed = true;
		await composer?.resetHeight();
		if (focusComposer) await composer?.focus();
	}

	async function newConversation() {
		await goto(buildAppUrl($page.url, { frame: 'chat' }), { noScroll: true });
		await syncConversationFromLocation();
		if (!sending && !addingImages) await composer?.focus();
	}

	async function selectConversation(selectedConversationId: string) {
		const normalizedId = parseConversationId(selectedConversationId);
		if (!normalizedId) return;
		if (parseConversationId($page.url.searchParams.get('conversation')) !== normalizedId) {
			await goto(buildAppUrl($page.url, { frame: 'chat', conversationId: normalizedId }), {
				noScroll: true,
				keepFocus: true
			});
		}
		await syncConversationFromLocation();
	}

	async function reconcileConversationLocation(
		requestedConversationId: string | null
	): Promise<void> {
		if (sending || addingImages) {
			pendingConversationLocation = requestedConversationId;
			return;
		}
		pendingConversationLocation = undefined;
		const currentUrlConversationId = parseConversationId(
			new URLSearchParams(window.location.search).get('conversation')
		);
		if (currentUrlConversationId !== requestedConversationId) {
			await goto(
				buildAppUrl($page.url, {
					frame: 'chat',
					...(requestedConversationId ? { conversationId: requestedConversationId } : {})
				}),
				{ replaceState: true, noScroll: true, keepFocus: true }
			);
		}
		if (requestedConversationId) {
			if (requestedConversationId !== conversationId) {
				await loadConversation(requestedConversationId);
			}
			return;
		}

		if (conversationId) await resetConversation(false);
	}

	async function syncConversationFromLocation(): Promise<void> {
		await reconcileConversationLocation(
			parseConversationId(new URLSearchParams(window.location.search).get('conversation'))
		);
	}

	async function flushPendingConversationLocation(): Promise<void> {
		if (pendingConversationLocation === undefined || sending || addingImages) return;
		const requestedConversationId = pendingConversationLocation;
		pendingConversationLocation = undefined;
		await reconcileConversationLocation(requestedConversationId);
	}

	function handleConversationPopState(): void {
		void syncConversationFromLocation();
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
	}

	function toggleHistory() {
		historyCollapsed = !historyCollapsed;
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
		void syncConversationFromLocation();
		void checkAvailability(true);
		availabilityTimer = setInterval(() => void checkAvailability(), 30_000);
		document.addEventListener('visibilitychange', handleVisibilityChange);
		window.addEventListener('popstate', handleConversationPopState);

		return () => {
			mobileMediaQuery?.removeEventListener('change', handleViewportChange);
			document.removeEventListener('visibilitychange', handleVisibilityChange);
			window.removeEventListener('popstate', handleConversationPopState);
		};
	});

	onDestroy(() => {
		conversationRequest?.abort();
		generationRequest?.abort();
		cancelStreamScroll();
		if (availabilityTimer) clearInterval(availabilityTimer);
		if (rateLimitTimer) clearTimeout(rateLimitTimer);
	});
</script>

<div class:chat-layout-history-collapsed={historyCollapsed} class="chat-layout">
	<ChatHistoryPanel
		{conversations}
		activeConversationId={conversationId}
		loading={loadingConversations}
		{loadingConversationId}
		busy={sending || addingImages}
		error={conversationListError}
		collapsed={historyCollapsed}
		onNewChat={newConversation}
		onSelectConversation={selectConversation}
		mobile={isMobile}
		onToggle={toggleHistory}
		onRetry={retryConversations}
	/>

	<section
		class="chat-workspace"
		aria-label="Chat workspace"
		data-focus-scope-allow
		inert={isMobile && !historyCollapsed}
		aria-hidden={isMobile && !historyCollapsed ? 'true' : undefined}
	>
		<ChatHeader
			{conversationTitle}
			{availability}
			canExport={Boolean(conversationId)}
			{exporting}
			onOpenHistory={openHistory}
			onExport={exportConversation}
			historyOpen={isMobile && !historyCollapsed}
		/>

		<div class="chat-content">
			{#if messages.length === 0 && !sending}
				<ChatWelcome onSelectPrompt={selectStarterPrompt} />
			{:else}
				<ChatMessageList bind:this={messageList} {messages} {sending} />
			{/if}

			<div class="chat-bottom-region">
				{#if availability === 'unavailable'}
					<div class="chat-availability-notice" role="status" aria-live="polite">
						<p>
							<strong>Rocky AI is temporarily unavailable.</strong>
							Your draft stays here and can still be edited while the service recovers.
						</p>
						<button
							type="button"
							onclick={() => checkAvailability(false, true)}
							disabled={checkingAvailability}
						>
							{checkingAvailability ? 'Checking…' : 'Check again'}
						</button>
					</div>
				{/if}
				<ChatStatusNotice
					message={errorMessage}
					tone={noticeTone}
					canRetry={Boolean(failedMessage) && !retryBlocked}
					onRetry={restoreFailedMessage}
					onDismiss={() => (errorMessage = '')}
				/>
				<ChatComposer
					bind:this={composer}
					bind:value={input}
					{images}
					{imageInputEnabled}
					{addingImages}
					maxImages={imageLimits?.maxImages || 0}
					{sending}
					disabled={composerDisabled}
					disabledReason={composerDisabledReason}
					onSend={sendMessage}
					onStop={stopGeneration}
					onAddImages={addImages}
					onRemoveImage={removeImage}
				/>
			</div>
		</div>
	</section>
</div>
