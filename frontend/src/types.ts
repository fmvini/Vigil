export interface User { id: string; email: string }
export interface Session { user: User; csrf_token: string }
export interface Page<T> { items: T[]; total: number }
export interface Project {
  id: string;
  name: string;
  description: string | null;
  archived_at: string | null;
  public_slug: string;
  public_status_enabled: boolean;
  revision: number;
}
export type Health = 'online' | 'degraded' | 'offline';
export type Freshness = 'no_data' | 'fresh' | 'stale' | 'paused';
export interface MonitorConfig {
  name: string;
  url: string;
  interval_seconds: number;
  timeout_ms: number;
  expected_status: number;
  failure_threshold: number;
  retry_count: number;
  latency_threshold_ms: number | null;
  is_public: boolean;
}
export interface Monitor extends MonitorConfig {
  id: string;
  project_id: string;
  paused_at: string | null;
  archived_at: string | null;
  health_status: Health | null;
  freshness: Freshness;
  last_checked_at: string | null;
  last_http_status: number | null;
  last_latency_ms: number | null;
}

export type MetricPeriod = '24h' | '7d' | '30d';
export interface Bucket {
  bucket_start: string;
  success_count: number; failure_count: number; sample_count: number;
  uptime_percent: number | null; latency_sample_count: number;
  average_latency_ms: number | null; p95_latency_ms: number | null;
}
export interface Metrics extends Omit<Bucket, 'bucket_start'> {
  from: string; to: string; computed_at: string;
  excluded_count: number; cancelled_count: number; pending_count: number; skipped_slots: number;
  health_status: Health | null; data_complete: boolean;
  freshness_counts: Record<Freshness, number>;
  bucket_seconds: number; series: Bucket[];
}
export interface PublicIncident {
  id: string; monitor_id: string; monitor_name: string;
  started_at: string; detected_at: string; ended_at: string | null;
  end_reason: string | null;
}
export interface Incident extends PublicIncident {
  cause_code: string; failure_threshold_snapshot: number;
  opening_check_id: string | null; closing_check_id: string | null;
}
export interface Check {
  id: string; job_id: string; monitor_id: string; config_version: number;
  scheduled_at: string; started_at: string; completed_at: string;
  outcome: 'success' | 'failure'; http_status: number | null; latency_ms: number | null;
  cycle_duration_ms: number; queue_delay_ms: number; attempt_count: number;
  attempts: { http_status: number | null; error_code: string | null; latency_ms: number | null; duration_ms?: number | null }[];
  error_code: string | null; health_after: Health; degradation_reason: string | null;
}
export interface PublicStatus {
  name: string; slug: string; revision: number; computed_at: string;
  health_status: Health | null; data_complete: boolean; freshness_counts: Record<Freshness, number>;
  monitors: { id: string; name: string; health_status: Health | null; freshness: Freshness; last_checked_at: string | null }[];
}
