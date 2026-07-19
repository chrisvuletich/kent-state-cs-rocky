import { browser } from '$app/environment';
import { writable } from 'svelte/store';
import type { User } from '$lib/types/user';

const AUTH_STORAGE_KEY = 'rocky.currentUser';

export const currentUser = writable<User | null>(null);

export function initAuthFromStorage(): void {
	if (!browser) {
		return;
	}

	const raw = localStorage.getItem(AUTH_STORAGE_KEY);
	if (!raw) {
		return;
	}

	try {
		const parsed = JSON.parse(raw) as Partial<User>;
		if (parsed.id && parsed.displayName && parsed.email) {
			const firstName = parsed.firstName || parsed.displayName.split(' ')[0] || '';
			const lastName = parsed.lastName || parsed.displayName.split(' ').slice(1).join(' ');
			currentUser.set({
				id: parsed.id,
				firstName,
				lastName,
				displayName: parsed.displayName,
				email: parsed.email,
				apiKeyOwnerId: parsed.apiKeyOwnerId || parsed.id,
				isAdmin: Boolean(parsed.isAdmin),
				isActive: true
			});
		}
	} catch {
		localStorage.removeItem(AUTH_STORAGE_KEY);
	}
}

export function loginAsUser(user: User): void {
	currentUser.set(user);
	if (browser) {
		localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(user));
	}
}

export function logoutUser(): void {
	currentUser.set(null);
	if (browser) {
		localStorage.removeItem(AUTH_STORAGE_KEY);
	}
}
