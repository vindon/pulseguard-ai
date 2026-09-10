// Mirrors pulseguard/models/*.py and the dict shapes built by
// pulseguard/gateway/routes.py — kept as plain interfaces (not codegen)
// since the backend doesn't publish a typed OpenAPI client.

export type SignalSource = 'x' | 'reddit';

export type Stage = 'validated' | 'triaged' | 'resolved' | 'escalated' | 'unknown';

export interface SentinelStage {
  source: SignalSource;
  carrier: string | null;
  is_valid: boolean;
  validity_reason: string | null;
  content_preview: string;
  url: string;
  posted_at: string;
  validated_at: string;
}

export interface TriageStage {
  category: string;
  resolution_tier: 0 | 1 | 2;
  severity_score: number;
  sentiment_score: number;
  churn_risk: boolean;
  routing_decision: 'RESOLVER' | 'ESCALATION';
  routing_rationale: string;
  triaged_at: string;
}

export interface ResolverStage {
  resolved: boolean;
  confidence_score: number;
  draft_response: string;
  escalation_reason: string | null;
  resolved_at: string;
}

export interface EscalationStage {
  severity: 'P1' | 'P2' | 'P3';
  summary: string;
  recommended_action: string;
  churn_risk: boolean;
  sentiment_score: number;
  acknowledged: boolean;
  acknowledged_by: string | null;
  escalated_at: string;
}

export interface SignalLifecycle {
  signal_id: string;
  stage: Stage;
  severity?: 'P1' | 'P2' | 'P3';
  acknowledged?: boolean;
  sentinel?: SentinelStage;
  triage?: TriageStage;
  resolver?: ResolverStage;
  escalation?: EscalationStage;
}

export interface PipelineSignalsResponse {
  signals: SignalLifecycle[];
  count: number;
}

export interface EscalationBrief {
  signal_id: string;
  summary: string;
  source_platform: string;
  carrier: string;
  category: string;
  severity: 'P1' | 'P2' | 'P3';
  sentiment_score: number;
  churn_risk: boolean;
  original_post_url: string;
  attempted_resolution: string | null;
  recommended_action: string;
  escalation_trace_id: string;
  escalated_at: string;
  acknowledged: boolean;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
}

export interface EscalationsResponse {
  briefs: EscalationBrief[];
  count: number;
}

export interface AdapterHealth {
  adapter_name: string;
  status: 'HEALTHY' | 'DEGRADED' | 'DOWN';
  last_successful_fetch: string | null;
  consecutive_errors: number;
  monthly_cap_used: number | null;
  monthly_cap_limit: number | null;
  error_message: string | null;
}

export interface AdapterStatusResponse {
  adapters: Record<string, AdapterHealth>;
  count: number;
}

export interface CircuitBreakerState {
  name: string;
  state: 'open' | 'closed' | 'half-open';
  consecutive_errors: number;
  opened_at: string | null;
}

export interface OrchestratorStatus {
  running: boolean;
  queue_depth_unacknowledged: number;
  global_circuit_open: boolean;
  adapter_circuit_breakers: Record<string, CircuitBreakerState>;
  x_monthly_reads: number;
  x_monthly_cap: number;
}

export interface PendingDraft {
  signal_id: string;
  carrier: string;
  category: string;
  severity: string | null;
  source_platform: SignalSource;
  source_url: string;
  draft_text: string;
  confidence_score: number;
  status: 'pending' | 'approved' | 'rejected';
  screen_flag: string | null;
  created_at: string;
  reviewed_at: string | null;
  reviewed_by: string | null;
}

export interface DraftsResponse {
  drafts: PendingDraft[];
  count: number;
}

export interface IngestRequest {
  source: SignalSource;
  source_id: string;
  author_handle: string;
  content: string;
  url: string;
  posted_at: string;
  carrier_hint?: string;
}

export interface IngestResponse {
  signal_id: string;
  trace_id: string;
  status: string;
}
