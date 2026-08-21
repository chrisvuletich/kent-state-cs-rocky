export type FrameName =
	| 'dashboard'
	| 'analytics'
	| 'users'
	| 'courses'
	| 'admin'
	| 'audit'
	| 'api-keys'
	| 'account'
	| 'chat'
	| 'help';

const frameLabels: Record<FrameName, string> = {
	dashboard: 'Dashboard',
	analytics: 'Analytics',
	users: 'Users',
	courses: 'Courses',
	admin: 'Admin Panel',
	audit: 'Audit Logs',
	'api-keys': 'API Keys',
	account: 'Account',
	chat: 'Chat',
	help: 'Help'
};

export const primaryFrames: FrameName[] = [
	'dashboard',
	'analytics',
	'users',
	'courses',
	'chat',
	'account'
];

const adminFrames: FrameName[] = [
	'dashboard',
	'analytics',
	'users',
	'courses',
	'admin',
	'audit',
	'api-keys',
	'account',
	'chat',
	'help'
];
const clientFrames: FrameName[] = ['dashboard', 'courses', 'account', 'chat', 'help'];

export function framesForRole(isAdmin: boolean): FrameName[] {
	return isAdmin ? adminFrames : clientFrames;
}

export function canAccessFrame(frame: FrameName, isAdmin: boolean): boolean {
	return framesForRole(isAdmin).includes(frame);
}

export function toFrameLabel(frame: FrameName): string {
	return frameLabels[frame];
}

export function isFrameName(value: unknown): value is FrameName {
	return typeof value === 'string' && value in frameLabels;
}
