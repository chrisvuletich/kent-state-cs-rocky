import { writable } from 'svelte/store';
import type { Component } from 'svelte';
import { browser } from '$app/environment';
import DashboardView from '$lib/components/views/DashboardView.svelte';
import AnalyticsView from '$lib/components/views/AnalyticsView.svelte';
import UsersView from '$lib/components/views/UsersView.svelte';
import CoursesView from '$lib/components/views/CoursesView.svelte';
import AdminPanel from '$lib/components/views/AdminPanel.svelte';
import AuditLogsView from '$lib/components/views/AuditLogsView.svelte';
import ApiKeysView from '$lib/components/views/ApiKeysView.svelte';
import AccountView from '$lib/components/views/AccountView.svelte';
// ChatView is a legacy JavaScript component; Svelte supplies it at runtime.
// @ts-expect-error no declaration is available for this legacy component
import ChatView from '$lib/components/views/ChatView.svelte';
import HelpView from '$lib/components/views/HelpView.svelte';
import type { FrameName } from '$lib/types/frame';

export type FrameComponent = Component;
export type { FrameName };
const FRAME_CACHE_KEY = 'rocky_current_frame';
const FRAME_CACHE_TTL_MS = 60 * 60 * 1000;
const FRAME_COOKIE_NAME = 'rocky_current_frame';
const FRAME_COOKIE_MAX_AGE_SECONDS = 60 * 60;

export const frameMap: Record<FrameName, FrameComponent> = {
    dashboard: DashboardView,
    analytics: AnalyticsView,
    users: UsersView,
    courses: CoursesView,
    admin: AdminPanel,
    audit: AuditLogsView,
    'api-keys': ApiKeysView,
    account: AccountView,
    chat: ChatView,
    help: HelpView
};

function isFrameName(value: unknown): value is FrameName {
    return typeof value === 'string' && value in frameMap;
}

function loadInitialFrame(): FrameName {
    if (!browser) {
        return 'dashboard';
    }

    try {
        const cookieMatch = document.cookie
            .split('; ')
            .find((entry) => entry.startsWith(`${FRAME_COOKIE_NAME}=`));

        if (cookieMatch) {
            const [, rawFrame] = cookieMatch.split('=');
            const frameFromCookie = decodeURIComponent(rawFrame || '').trim();
            if (isFrameName(frameFromCookie)) {
                return frameFromCookie;
            }
        }

        const rawValue = localStorage.getItem(FRAME_CACHE_KEY);
        if (!rawValue) {
            return 'dashboard';
        }

        const cached = JSON.parse(rawValue) as { frame?: unknown; expiresAt?: unknown };
        if (typeof cached.expiresAt !== 'number' || Date.now() > cached.expiresAt) {
            localStorage.removeItem(FRAME_CACHE_KEY);
            return 'dashboard';
        }

        if (isFrameName(cached.frame)) {
            return cached.frame;
        }
    } catch {
        localStorage.removeItem(FRAME_CACHE_KEY);
    }

    return 'dashboard';
}

export const currentFrame = writable<FrameName>(loadInitialFrame());

if (browser) {
    currentFrame.subscribe((frame) => {
        const expiresAt = Date.now() + FRAME_CACHE_TTL_MS;
        localStorage.setItem(FRAME_CACHE_KEY, JSON.stringify({ frame, expiresAt }));
        document.cookie = `${FRAME_COOKIE_NAME}=${encodeURIComponent(frame)}; Path=/; Max-Age=${FRAME_COOKIE_MAX_AGE_SECONDS}; SameSite=Lax`;
    });
}
