import { describe, expect, it, vi } from 'vitest';

vi.mock('$lib/config/env', () => ({ APP_ENV: 'testing' }));

import { parseThemeCookie, THEME_COOKIE_OPTIONS, themeCookieName } from './themePreferenceCookie';

describe('theme preference cookie', () => {
	it('keeps preferences scoped to a safe per-user cookie name', () => {
		expect(themeCookieName('student-1')).toBe('rocky_theme_student-1');
		expect(themeCookieName('student@example.invalid')).toBe('rocky_theme_student_example_invalid');
		expect(themeCookieName('student-1')).not.toBe(themeCookieName('student-2'));
	});

	it('accepts only supported themes and remains server-managed', () => {
		expect(parseThemeCookie('dark')).toBe('dark');
		expect(parseThemeCookie('light')).toBe('light');
		expect(parseThemeCookie('system')).toBeNull();
		expect(THEME_COOKIE_OPTIONS.httpOnly).toBe(true);
	});
});
