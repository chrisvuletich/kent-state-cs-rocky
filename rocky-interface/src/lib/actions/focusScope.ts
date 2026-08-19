export type FocusScopeOptions = {
	active?: boolean;
	initialFocus?: string;
	inertOutside?: boolean;
	onEscape?: () => void;
	returnFocusTo?: HTMLElement | null;
};

const focusableSelector = [
	'a[href]',
	'button:not(:disabled)',
	'input:not(:disabled)',
	'select:not(:disabled)',
	'textarea:not(:disabled)',
	'details > summary:first-of-type',
	'[tabindex]:not([tabindex="-1"])'
].join(',');

function focusableElements(node: HTMLElement): HTMLElement[] {
	return Array.from(node.querySelectorAll<HTMLElement>(focusableSelector)).filter(
		(element) =>
			!element.closest('[inert]') &&
			element.getAttribute('aria-hidden') !== 'true' &&
			(element.offsetWidth > 0 || element.offsetHeight > 0 || element.getClientRects().length > 0)
	);
}

function outsideBranches(node: HTMLElement): HTMLElement[] {
	const branches: HTMLElement[] = [];
	let current: HTMLElement = node;
	let parent = current.parentElement;

	while (parent) {
		for (const child of Array.from(parent.children)) {
			if (child === current || child.hasAttribute('data-focus-scope-allow')) continue;
			if (child instanceof HTMLElement && !branches.includes(child)) branches.push(child);
		}

		if (parent === document.body) break;
		current = parent;
		parent = parent.parentElement;
	}

	return branches;
}

export function focusScope(node: HTMLElement, initialOptions: FocusScopeOptions = {}) {
	let options = initialOptions;
	let active = false;
	let activationId = 0;
	let previousFocus: HTMLElement | null = null;
	let inertStates: Array<{ element: HTMLElement; hadAttribute: boolean }> = [];

	function firstFocusTarget(): HTMLElement {
		if (options.initialFocus) {
			const requested = node.querySelector<HTMLElement>(options.initialFocus);
			if (requested) return requested;
		}

		return (
			node.querySelector<HTMLElement>('[data-autofocus]') || focusableElements(node)[0] || node
		);
	}

	function focusInside(): void {
		const target = firstFocusTarget();
		if (!target.hasAttribute('tabindex') && target === node) target.setAttribute('tabindex', '-1');
		target.focus({ preventScroll: true });
	}

	function activate(): void {
		if (active) return;
		active = true;
		activationId += 1;
		const currentActivation = activationId;
		previousFocus =
			options.returnFocusTo ||
			(document.activeElement instanceof HTMLElement ? document.activeElement : null);

		if (options.inertOutside !== false) {
			inertStates = outsideBranches(node).map((element) => ({
				element,
				hadAttribute: element.hasAttribute('inert')
			}));
			for (const { element } of inertStates) element.setAttribute('inert', '');
		}

		queueMicrotask(() => {
			if (active && currentActivation === activationId) focusInside();
		});
	}

	function deactivate(): void {
		if (!active) return;
		active = false;
		activationId += 1;

		for (const { element, hadAttribute } of inertStates.reverse()) {
			if (!hadAttribute) element.removeAttribute('inert');
		}
		inertStates = [];

		const returnTarget = options.returnFocusTo || previousFocus;
		previousFocus = null;
		queueMicrotask(() => {
			if (returnTarget?.isConnected && !returnTarget.closest('[inert]')) {
				returnTarget.focus({ preventScroll: true });
			}
		});
	}

	function handleKeydown(event: KeyboardEvent): void {
		if (!active) return;

		if (event.key === 'Escape' && options.onEscape) {
			event.preventDefault();
			event.stopPropagation();
			options.onEscape();
			return;
		}

		if (event.key !== 'Tab') return;
		const focusable = focusableElements(node);
		if (focusable.length === 0) {
			event.preventDefault();
			focusInside();
			return;
		}

		const first = focusable[0];
		const last = focusable[focusable.length - 1];
		const current = document.activeElement;
		if (event.shiftKey && (current === first || !node.contains(current))) {
			event.preventDefault();
			last.focus();
		} else if (!event.shiftKey && (current === last || !node.contains(current))) {
			event.preventDefault();
			first.focus();
		}
	}

	function handleFocusIn(event: FocusEvent): void {
		if (active && event.target instanceof Node && !node.contains(event.target)) focusInside();
	}

	document.addEventListener('keydown', handleKeydown, true);
	document.addEventListener('focusin', handleFocusIn, true);

	if (options.active !== false) activate();

	return {
		update(nextOptions: FocusScopeOptions = {}) {
			const wasActive = active;
			options = nextOptions;
			const shouldBeActive = options.active !== false;
			if (!wasActive && shouldBeActive) activate();
			else if (wasActive && !shouldBeActive) deactivate();
		},
		destroy() {
			deactivate();
			document.removeEventListener('keydown', handleKeydown, true);
			document.removeEventListener('focusin', handleFocusIn, true);
		}
	};
}
