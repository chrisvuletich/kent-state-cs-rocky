import { describe, expect, it } from 'vitest';
import {
	appHref,
	buildAppUrl,
	isAccessibleRequestedFrame,
	parseConversationId,
	parseCourseId,
	resolveAppFrame
} from './appRoute';

describe('app route state', () => {
	it('uses an accessible requested frame ahead of the remembered frame', () => {
		expect(resolveAppFrame(new URLSearchParams('frame=courses'), 'account', false)).toBe('courses');
	});

	it('uses documentation as an intentional Help deep link', () => {
		expect(
			resolveAppFrame(new URLSearchParams('frame=dashboard&doc=intro'), 'account', false)
		).toBe('help');
	});

	it('uses the remembered frame only when the URL has no frame', () => {
		expect(resolveAppFrame(new URLSearchParams(), 'account', false)).toBe('account');
		expect(resolveAppFrame(new URLSearchParams('frame=unknown'), 'account', false)).toBe(
			'dashboard'
		);
	});

	it('does not expose administrator frames to students', () => {
		expect(resolveAppFrame(new URLSearchParams('frame=audit'), 'courses', false)).toBe('dashboard');
		expect(isAccessibleRequestedFrame('audit', false)).toBe(false);
		expect(isAccessibleRequestedFrame('audit', true)).toBe(true);
	});

	it('builds a course deep link and removes stale frame-specific state', () => {
		const current = new URL(
			'https://rocky.example/?frame=analytics&range=30d&request=req-1&doc=intro&conversation=old'
		);
		const url = buildAppUrl(current, { frame: 'courses', courseId: 42 });

		expect(url.pathname).toBe('/');
		expect(url.searchParams.get('frame')).toBe('courses');
		expect(url.searchParams.get('course')).toBe('42');
		expect(url.searchParams.has('range')).toBe(false);
		expect(url.searchParams.has('request')).toBe(false);
		expect(url.searchParams.has('doc')).toBe(false);
		expect(url.searchParams.has('conversation')).toBe(false);
	});

	it('builds bounded chat and documentation links', () => {
		expect(
			appHref(new URL('https://rocky.example/?frame=dashboard'), {
				frame: 'chat',
				conversationId: ' conversation-7 '
			})
		).toBe('/?conversation=conversation-7&frame=chat');
		expect(
			appHref(new URL('https://rocky.example/?frame=dashboard'), {
				frame: 'help',
				documentId: 'intro'
			})
		).toBe('/?doc=intro&frame=help');
	});

	it('parses only safe positive course IDs and non-empty conversation IDs', () => {
		expect(parseCourseId('17')).toBe(17);
		expect(parseCourseId('0')).toBeNull();
		expect(parseCourseId('-1')).toBeNull();
		expect(parseCourseId('1.5')).toBeNull();
		expect(parseCourseId('not-a-course')).toBeNull();
		expect(parseConversationId(' conversation-8 ')).toBe('conversation-8');
		expect(parseConversationId('   ')).toBeNull();
	});
});
