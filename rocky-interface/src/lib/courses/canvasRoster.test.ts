import { describe, expect, it } from 'vitest';

import { parseCanvasRosterEmails } from './canvasRoster';

describe('parseCanvasRosterEmails', () => {
	it('imports Canvas Class Roster emails with numeric Canvas IDs and empty SIS IDs', () => {
		const csv = [
			'Student Name,Student ID,Student SIS ID,Email,Section Name',
			'Example Student,155843,,student.one@kent.edu,Fall 2026 SOFTWARE ENGINEERING (CS-33901-001)',
			'Another Student,174726,,student.two@kent.edu,Fall 2026 SOFTWARE ENGINEERING (CS-33901-001)'
		].join('\n');
		expect(parseCanvasRosterEmails(csv)).toEqual(['student.one@kent.edu', 'student.two@kent.edu']);
	});

	it('handles a BOM, CRLF, reordered headers, whitespace, and quoted fields', () => {
		const csv =
			'\uFEFF" EMAIL ","Student Name","Section Name"\r\n' +
			'" Student.One@Kent.edu ","Student, Example","Section ""A"", morning\r\nlecture"\r\n';
		expect(parseCanvasRosterEmails(csv)).toEqual(['student.one@kent.edu']);
	});

	it('deduplicates emails across sections without treating blank rows as students', () => {
		const csv =
			'\nEmail,Section Name\nSTUDENT@kent.edu,Section A\n,\n student@kent.edu ,Section B\n\n';
		expect(parseCanvasRosterEmails(csv)).toEqual(['student@kent.edu']);
	});

	it('allows a minimal Email-only CSV and a final row without a newline', () => {
		expect(parseCanvasRosterEmails('Email\rfirst@kent.edu\rsecond@kent.edu')).toEqual([
			'first@kent.edu',
			'second@kent.edu'
		]);
	});

	it.each(['', ' \r\n,\r\n', '\uFEFF'])('rejects empty files: %j', (csv) => {
		expect(() => parseCanvasRosterEmails(csv)).toThrow('CSV is empty');
	});

	it('does not fall back to SIS IDs or email-like text outside the Email column', () => {
		expect(() =>
			parseCanvasRosterEmails('Student SIS ID,Student Name\nKSUID123456789,user@kent.edu')
		).toThrow('needs an Email column');
	});

	it('rejects duplicate Email headers', () => {
		expect(() => parseCanvasRosterEmails('Email,email\na@kent.edu,b@kent.edu')).toThrow(
			'multiple Email columns'
		);
	});

	it('rejects header-only exports', () => {
		expect(() => parseCanvasRosterEmails('Student Name,Email\n,\n')).toThrow('no student rows');
	});

	it.each([
		'',
		'not-an-email',
		'student@kent',
		'a@@kent.edu',
		'a b@kent.edu',
		'.a@kent.edu',
		'a.@kent.edu',
		'a@.kent.edu',
		'a@kent..edu',
		'a@kent.edu.'
	])('rejects invalid email %j before returning any students', (email) => {
		expect(() =>
			parseCanvasRosterEmails(`Student Name,Email\nValid,valid@kent.edu\nInvalid,${email}`)
		).toThrow('CSV row 3 has a missing or invalid email. No students were imported.');
	});

	it.each(['Name,user@kent.edu,extra', 'Name'])('rejects misaligned rows: %j', (row) => {
		expect(() => parseCanvasRosterEmails(`Student Name,Email\n${row}`)).toThrow(
			'wrong number of columns'
		);
	});

	it.each(['"Name,user@kent.edu', 'Na"me,user@kent.edu', '"Name"extra,user@kent.edu'])(
		'rejects malformed quoting: %j',
		(row) => {
			expect(() => parseCanvasRosterEmails(`Student Name,Email\n${row}`)).toThrow(/quoted|quoting/);
		}
	);
});
