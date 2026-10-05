// Canvas exports use standard CSV quoting: names/sections can contain commas,
// doubled quotes, and newlines. Keep parsing separate from roster mutations so
// the entire file is validated before any students are added.
function readCsvRows(text: string): string[][] {
	const rows: string[][] = [];
	let row: string[] = [];
	let field = '';
	let inQuotes = false;
	let closedQuote = false;
	const source = text.replace(/^\uFEFF/, '');

	for (let index = 0; index < source.length; index += 1) {
		const char = source[index];
		if (inQuotes) {
			if (char === '"') {
				if (source[index + 1] === '"') {
					field += '"';
					index += 1;
				} else {
					inQuotes = false;
					closedQuote = true;
				}
			} else {
				field += char;
			}
		} else if (char === ',' || char === '\r' || char === '\n') {
			row.push(field);
			field = '';
			closedQuote = false;
			if (char !== ',') {
				rows.push(row);
				row = [];
				if (char === '\r' && source[index + 1] === '\n') index += 1;
			}
		} else if (char === '"' && !field.trim() && !closedQuote) {
			field = '';
			inQuotes = true;
		} else if (char === '"' || (closedQuote && char.trim())) {
			throw new Error('Invalid CSV quoting. Export the Class Roster from Canvas again.');
		} else {
			field += char;
		}
	}

	if (inQuotes) {
		throw new Error('The CSV has an unclosed quoted field. Export the Class Roster again.');
	}
	row.push(field);
	rows.push(row);
	return rows;
}

export function parseCanvasRosterEmails(text: string): string[] {
	const rows = readCsvRows(text);
	const headerIndex = rows.findIndex((row) => row.some((field) => field.trim()));
	if (headerIndex === -1) {
		throw new Error('The CSV is empty. Choose a Canvas Class Roster export.');
	}
	const headers = rows[headerIndex].map((field) => field.trim().toLowerCase());
	const emailIndex = headers.indexOf('email');
	if (emailIndex === -1) {
		throw new Error('The CSV needs an Email column. Export the Class Roster from Canvas.');
	}
	if (headers.lastIndexOf('email') !== emailIndex) {
		throw new Error('The CSV has multiple Email columns. Keep only one Email column.');
	}

	const emails = new Set<string>();
	for (let index = headerIndex + 1; index < rows.length; index += 1) {
		const row = rows[index];
		if (row.every((field) => !field.trim())) continue;
		if (row.length !== headers.length) {
			throw new Error(
				`CSV row ${index + 1} has the wrong number of columns. No students were imported.`
			);
		}
		const email = row[emailIndex].trim().toLowerCase();
		const [local, domain] = email.split('@');
		if (
			!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) ||
			local.startsWith('.') ||
			local.endsWith('.') ||
			domain.split('.').some((label) => !label)
		) {
			throw new Error(
				`CSV row ${index + 1} has a missing or invalid email. No students were imported.`
			);
		}
		emails.add(email);
	}
	if (!emails.size) {
		throw new Error('The CSV has no student rows. Choose a Canvas Class Roster export.');
	}
	return [...emails];
}
