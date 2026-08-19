const tabNavigationKeys = new Set([
	'ArrowLeft',
	'ArrowRight',
	'ArrowUp',
	'ArrowDown',
	'Home',
	'End'
]);

/**
 * Gives native buttons in a tablist the expected roving-focus keyboard behavior.
 * Clicking the destination tab keeps selection logic in the owning component.
 */
export function handleTabListKeydown(event: KeyboardEvent): void {
	if (!tabNavigationKeys.has(event.key) || !(event.target instanceof HTMLElement)) {
		return;
	}

	const tabList = event.target.closest<HTMLElement>('[role="tablist"]');
	if (!tabList) return;

	const tabs = Array.from(
		tabList.querySelectorAll<HTMLButtonElement>('[role="tab"]:not(:disabled)')
	);
	const currentIndex = tabs.indexOf(event.target.closest<HTMLButtonElement>('[role="tab"]')!);
	if (currentIndex < 0 || tabs.length === 0) return;

	event.preventDefault();
	let nextIndex = currentIndex;
	if (event.key === 'Home') nextIndex = 0;
	else if (event.key === 'End') nextIndex = tabs.length - 1;
	else if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
		nextIndex = (currentIndex + 1) % tabs.length;
	} else {
		nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
	}

	tabs[nextIndex].focus();
	tabs[nextIndex].click();
}
