export type FrameName = 'dashboard' | 'users' | 'courses' | 'analytics' | 'account' | 'chat' | 'help';

const frameLabels: Record<FrameName, string> = {
	dashboard: 'Dashboard',
	users: 'Users',
	courses: 'Courses',
	analytics: 'Analytics',
	account: 'Account',
	chat: 'ChatView',
	help: 'Help'
};

export const primaryFrames: FrameName[] = ['dashboard', 'users', 'courses', 'analytics', 'chat', 'account'];

// const adminFrames: FrameName[] = ['dashboard', 'users', 'courses', 'analytics', 'account', 'help'];
// const clientFrames: FrameName[] = ['dashboard', 'courses', 'analytics', 'account', 'help'];
const adminFrames: FrameName[] = ['dashboard', 'users', 'courses', 'account', 'chat', 'help'];
const clientFrames: FrameName[] = ['dashboard', 'courses', 'account','chat', 'help'];

export function framesForRole(isAdmin: boolean): FrameName[] {
	return isAdmin ? adminFrames : clientFrames;
}

export function canAccessFrame(frame: FrameName, isAdmin: boolean): boolean {
	return framesForRole(isAdmin).includes(frame);
}

export function toFrameLabel(frame: FrameName): string {
	return frameLabels[frame];
}

export function toFrameName(value: string, fallback: FrameName = 'dashboard'): FrameName {
	if (value in frameLabels) {
		return value as FrameName;
	}

	return fallback;
}
