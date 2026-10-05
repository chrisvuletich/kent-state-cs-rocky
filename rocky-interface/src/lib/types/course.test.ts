import { describe, expect, it } from 'vitest';
import { normalizeCourseGroup, type ApiCourseGroup } from './course';

describe('group joining settings', () => {
	it('keeps existing groups closed to self-joining with no size limit', () => {
		const group = normalizeCourseGroup({ id: 'group-a', memberIds: ['student@kent.edu'] });
		expect(group.selfJoinEnabled).toBe(false);
		expect(group.maxMembers).toBe(null);
		expect(group.memberIds).toEqual(['student@kent.edu']);
	});
	it('preserves an explicit opt-in and integer limit', () => {
		const group = normalizeCourseGroup({ self_join_enabled: true, max_members: 4 });
		expect(group.selfJoinEnabled).toBe(true);
		expect(group.maxMembers).toBe(4);
	});
	it('does not coerce strings into an enabled self-join policy', () => {
		expect(
			normalizeCourseGroup({ self_join_enabled: 'true' } as unknown as ApiCourseGroup)
				.selfJoinEnabled
		).toBe(false);
	});
	it.each([0, -1, 1.5, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1])(
		'rejects invalid display limits: %s',
		(limit) => {
			expect(normalizeCourseGroup({ max_members: limit }).maxMembers).toBe(null);
		}
	);
});
