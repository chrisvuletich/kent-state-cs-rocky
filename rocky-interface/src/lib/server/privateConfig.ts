const PLACEHOLDER_PREFIXES = ['replace-with', 'change-me', 'changeme'];

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
