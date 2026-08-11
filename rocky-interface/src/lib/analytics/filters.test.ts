import { describe, expect, it } from 'vitest';
import {
	analyticsFilterCount,
	analyticsUrl,
	defaultAnalyticsFilters,
	parseAnalyticsFilters
} from './filters';

describe('analytics URL filters', () => {
	it('parses recognized filters and safely defaults invalid values', () => {
		const parsed = parseAnalyticsFilters(
			new URLSearchParams(
				'range=7d&dimension=model&user=student%40kent.edu&operation=responses.create&outcome=failed&error_type=rate_limit_exceeded&review=flagged'
			)
		);
		expect(parsed).toMatchObject({
			window: '7d',
			dimension: 'model',
			user: 'student@kent.edu',
			operation: 'responses.create',
			outcome: 'failed',
			errorType: 'rate_limit_exceeded',
			review: 'flagged'
		});
		expect(parseAnalyticsFilters(new URLSearchParams('range=forever&outcome=anything'))).toEqual(
			defaultAnalyticsFilters
		);
	});

	it('accepts legacy analytics links and writes the canonical compact form', () => {
		const state = parseAnalyticsFilters(
			new URLSearchParams(
				'analytics_window=1h&analytics_dimension=course&analytics_outcome=completed&analytics_request=req-1'
			)
		);
		const url = analyticsUrl(new URL('https://rocky.example/?doc=reference'), state);
		expect(url.searchParams.get('frame')).toBe('analytics');
		expect(url.searchParams.get('range')).toBe('1h');
		expect(url.searchParams.get('dimension')).toBe('course');
		expect(url.searchParams.get('outcome')).toBe('completed');
		expect(url.searchParams.get('request')).toBe('req-1');
		expect(url.searchParams.has('analytics_window')).toBe(false);
	});

	it('round-trips the bounded error-type filter in canonical URLs', () => {
		const state = parseAnalyticsFilters(new URLSearchParams(`error_type=${'x'.repeat(140)}`));
		expect(state.errorType).toHaveLength(128);

		const url = analyticsUrl(new URL('https://rocky.example/'), state);
		expect(url.searchParams.get('error_type')).toBe('x'.repeat(128));
		expect(analyticsFilterCount(state)).toBe(1);
	});

	it('omits defaults and counts only active data filters', () => {
		const url = analyticsUrl(new URL('https://rocky.example/'), defaultAnalyticsFilters);
		expect(url.search).toBe('?frame=analytics');
		expect(analyticsFilterCount(defaultAnalyticsFilters)).toBe(0);
		expect(analyticsFilterCount({ ...defaultAnalyticsFilters, course: 'CS-44001' })).toBe(1);
	});
});
