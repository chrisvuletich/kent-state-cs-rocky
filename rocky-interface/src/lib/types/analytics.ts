export type KpiMetric = {
	label: string;
	value: string;
	delta: string;
};

export type ActivityRow = {
	window: string;
	requests: number;
	flagged: number;
	successRate: string;
};

export const analyticsWindows = ['15m', '1h', '6h', '24h', '7d', '30d'] as const;
export const analyticsDimensions = [
	'user',
	'course',
	'key',
	'group',
	'model',
	'source',
	'outcome'
] as const;

export type AnalyticsWindow = (typeof analyticsWindows)[number];
export type AnalyticsDimension = (typeof analyticsDimensions)[number];
export type AnalyticsOutcome = 'completed' | 'rejected' | 'failed' | 'timed_out';
export const analyticsReviewStatuses = ['unreviewed', 'in_review', 'resolved'] as const;
export const analyticsReviewReasons = [
	'academic_integrity',
	'harmful_content',
	'security_abuse',
	'policy_violation',
	'system_quality',
	'other'
] as const;
export type AnalyticsReviewStatus = (typeof analyticsReviewStatuses)[number];
export type AnalyticsReviewReason = (typeof analyticsReviewReasons)[number];

export type AnalyticsReview = {
	version: number;
	flagged: boolean;
	flag_reasons: AnalyticsReviewReason[];
	status: AnalyticsReviewStatus;
	reviewed_by: { user_id?: string | null; email?: string | null } | null;
	reviewed_at: string | null;
	notes: string | null;
};

export type AnalyticsDuration = {
	samples: number;
	average_ms: number | null;
	p95_ms: number | null;
};

export type AnalyticsMetrics = {
	requests: number;
	terminal: number;
	active: number;
	outcomes: Record<AnalyticsOutcome, number>;
	flagged: number;
	success_rate: number | null;
	acceptance_rate: number | null;
	generation: {
		requests: number;
		inference_dispatches: number;
		outcomes: Record<AnalyticsOutcome, number>;
	};
	usage: {
		input_tokens: number;
		output_tokens: number;
		total_tokens: number;
		input_bytes: number;
		output_bytes: number;
	};
	latency_ms: {
		samples: number;
		average: number | null;
		p50: number | null;
		p95: number | null;
		p99: number | null;
	};
	api_latency_ms: {
		samples: number;
		average: number | null;
		p50: number | null;
		p95: number | null;
		p99: number | null;
	};
	model_performance: {
		total_duration: AnalyticsDuration;
		load_duration: AnalyticsDuration;
		prompt_eval_duration: AnalyticsDuration;
		generation_duration: AnalyticsDuration;
		prompt_tokens_per_second: number | null;
		generation_tokens_per_second: number | null;
	};
};

export type AnalyticsSummary = AnalyticsMetrics & {
	window: AnalyticsWindow;
	start: string;
	end: string;
	rates: {
		average_requests_per_minute: number;
		average_requests_per_hour: number;
		average_tokens_per_minute: number;
		average_tokens_per_hour: number;
		peak_requests_per_minute: number;
		peak_tokens_per_minute: number;
	};
};

export type AnalyticsTimeBucket = AnalyticsMetrics & {
	start: string;
	end: string;
	requests_per_minute: number;
	requests_per_hour: number;
	tokens_per_minute: number;
	tokens_per_hour: number;
};

export type AnalyticsTimeseries = {
	window: AnalyticsWindow;
	bucket: 'minute' | 'hour' | 'day';
	start: string;
	end: string;
	buckets: AnalyticsTimeBucket[];
};

export type AnalyticsBreakdownRow = AnalyticsMetrics & {
	id: string;
	label: string;
};

export type AnalyticsBreakdown = {
	window: AnalyticsWindow;
	start: string;
	end: string;
	dimension: AnalyticsDimension;
	rows: AnalyticsBreakdownRow[];
};

export type AnalyticsRequestSummary = {
	request_id: string;
	received_at: string | null;
	terminal_at: string | null;
	state: string | null;
	outcome: AnalyticsOutcome | 'active';
	http_status: number | null;
	source: string | null;
	operation: string | null;
	actor: { user_id?: string | null; email?: string | null; name?: string | null } | null;
	credential: {
		key_id?: string | null;
		key_name?: string | null;
		owner_type?: string | null;
	} | null;
	course: {
		course_id?: number | null;
		course_code?: string | null;
		group_id?: string | null;
	} | null;
	model: { public_model?: string | null; actual_model?: string | null } | null;
	usage: AnalyticsMetrics['usage'] | null;
	performance: Record<string, number | null> | null;
	review: AnalyticsReview | null;
	error_stage: string | null;
	error_type: string | null;
};

export type AnalyticsRequests = {
	window: AnalyticsWindow;
	start: string;
	end: string;
	matched: number;
	limit: number;
	requests: AnalyticsRequestSummary[];
};

export type AnalyticsRequestDetail = AnalyticsRequestSummary & {
	request?: { input_text?: string | null; body?: unknown; [key: string]: unknown };
	response?: { output_text?: string | null; body?: unknown; [key: string]: unknown };
	client?: Record<string, unknown>;
	[key: string]: unknown;
};

export type AnalyticsReviewPatch = Pick<
	AnalyticsReview,
	'version' | 'flagged' | 'flag_reasons' | 'status' | 'notes'
>;

export type AnalyticsRequestFilters = {
	user?: string;
	course?: string;
	key?: string;
	model?: string;
	operation?: 'models.list' | 'responses.create' | 'unknown' | '';
	outcome?: AnalyticsOutcome | 'active' | '';
	source?: string;
	flagged?: boolean;
	reviewStatus?: AnalyticsReviewStatus | '';
};

export type AnalyticsCurrent = {
	generated_at: string;
	updated_at: string | null;
	last_interaction_at: string | null;
	last_terminal_at: string | null;
	last_model: string | null;
	last_stop_reason: string | null;
	active_requests: number;
	unresolved_interactions: number;
	registered_users: number;
	lifetime: {
		requests: number;
		outcomes: Record<AnalyticsOutcome, number>;
		usage: {
			input_tokens: number;
			output_tokens: number;
			input_bytes: number;
			output_bytes: number;
		};
		latency_ms: { samples: number; average: number | null };
	};
};

export type AnalyticsMyUsage = {
	generated_at: string;
	today_start: string;
	requests_today: number;
	total_requests: number;
	active_requests: number;
	outcomes: Record<AnalyticsOutcome, number>;
	usage: AnalyticsMetrics['usage'];
	last_request_at: string | null;
};

export type AnalyticsHardwareMetric = {
	average: number | null;
	maximum: number | null;
};

export type AnalyticsHardwareBucket = {
	start: string;
	end: string;
	sample_count: number;
	hardware: {
		gpu_utilization_percent: AnalyticsHardwareMetric;
		gpu_memory_percent: AnalyticsHardwareMetric;
		gpu_temperature_c: AnalyticsHardwareMetric;
		gpu_power_watts: AnalyticsHardwareMetric;
		cpu_percent: AnalyticsHardwareMetric;
		system_memory_percent: AnalyticsHardwareMetric;
	};
	model: {
		loaded_model_count: number | null;
		loaded_models: Array<{ name: string; size_vram_bytes: number | null }>;
	};
	runtime: { active_inference_requests: number | null };
	workload: {
		requests: number;
		input_tokens: number;
		output_tokens: number;
		total_tokens: number;
		p95_latency_ms: number | null;
		generation_tokens_per_second: number | null;
		generation_duration_ms: number | null;
		load_duration_ms: number | null;
	};
};

export type AnalyticsHardware = {
	window: AnalyticsWindow;
	bucket: 'minute' | 'hour' | 'day';
	start: string;
	end: string;
	sample_interval_seconds: number;
	sample_count: number;
	status: 'live' | 'partial' | 'stale' | 'unavailable';
	latest: {
		sampled_at: string;
		source: { service?: string; host?: string };
		gpu: {
			available: boolean;
			count: number;
			utilization_percent: number | null;
			memory_used_bytes: number | null;
			memory_total_bytes: number | null;
			memory_percent: number | null;
			temperature_c: number | null;
			power_watts: number | null;
		} | null;
		system: {
			cpu_percent: number | null;
			memory_used_bytes: number | null;
			memory_total_bytes: number | null;
			memory_percent: number | null;
		} | null;
		model: {
			loaded_model_count: number;
			loaded_vram_bytes: number | null;
			loaded_models: Array<{ name: string; size_vram_bytes: number | null }>;
		} | null;
		runtime: { active_inference_requests: number } | null;
		partial: boolean;
		missing: string[];
	} | null;
	buckets: AnalyticsHardwareBucket[];
};

export function toKpiMetric(metric: Partial<KpiMetric>): KpiMetric {
	return {
		label: metric.label?.trim() || 'Unknown KPI',
		value: metric.value?.trim() || '0',
		delta: metric.delta?.trim() || '0%'
	};
}

export function toActivityRow(row: Partial<ActivityRow>): ActivityRow {
	return {
		window: row.window?.trim() || 'N/A',
		requests: typeof row.requests === 'number' && Number.isFinite(row.requests) ? row.requests : 0,
		flagged: typeof row.flagged === 'number' && Number.isFinite(row.flagged) ? row.flagged : 0,
		successRate: row.successRate?.trim() || '0%'
	};
}
