import type { Component } from 'svelte';
import DashboardView from '$lib/components/views/DashboardView.svelte';
import AnalyticsView from '$lib/components/views/AnalyticsView.svelte';
import UsersView from '$lib/components/views/UsersView.svelte';
import CoursesView from '$lib/components/views/CoursesView.svelte';
import AdminPanel from '$lib/components/views/AdminPanel.svelte';
import AuditLogsView from '$lib/components/views/AuditLogsView.svelte';
import ApiKeysView from '$lib/components/views/ApiKeysView.svelte';
import AccountView from '$lib/components/views/AccountView.svelte';
import ChatView from '$lib/components/views/ChatView.svelte';
import HelpView from '$lib/components/views/HelpView.svelte';
import type { FrameName } from '$lib/types/frame';

export type FrameComponent = Component;

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

export const frameTitles: Record<FrameName, string> = {
	dashboard: 'Dashboard',
	analytics: 'Analytics',
	users: 'Users',
	courses: 'Courses',
	admin: 'Admin Dashboard',
	audit: 'Audit Logs',
	'api-keys': 'API Keys',
	account: 'Account',
	chat: 'Chat',
	help: 'Help Center'
};
