const PLACEHOLDER_PREFIXES = ['replace-with', 'change-me', 'changeme'];

export function privateBoolean(
	name: string,
	value: string | undefined,
	fallback: boolean
): boolean {
	const normalized = value?.trim().toLowerCase();
	if (!normalized) return fallback;
	if (normalized === 'true') return true;
	if (normalized === 'false') return false;
	throw new Error(`${name} must be exactly true or false.`);
}

export function requireProductionSecret(name: string, value: string, appEnv: string): string {
	const normalized = value.trim();
	if (appEnv !== 'production') {
		return normalized;
	}

	const isPlaceholder = PLACEHOLDER_PREFIXES.some((prefix) =>
		normalized.toLowerCase().startsWith(prefix)
	);
	if (normalized.length < 32 || isPlaceholder) {
		throw new Error(
			`${name} must be a non-placeholder value of at least 32 characters in production.`
		);
	}
	return normalized;
}
