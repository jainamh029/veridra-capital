// Typed client for the Capital Call Verification Platform API (agents/app.py).
// Every shape here mirrors what the FastAPI endpoints actually return — see
// agents/app.py and the module cores (verification/, approvals/, cash_planning/,
// forecasting/, k1_routing/) for the source of truth.

export const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : `HTTP ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  const isJson = res.headers.get("content-type")?.includes("application/json");
  const body = isJson ? await res.json().catch(() => null) : null;
  if (!res.ok) throw new ApiError(res.status, body?.detail ?? body ?? res.statusText);
  return body as T;
}

// ---------------------------------------------------------------- health / funds
export interface HealthOut { ok: boolean; as_of: string; funds: number }
export interface FundLite { fund_id: string; fund_name: string }

export const getHealth = () => req<HealthOut>("/health");
export const getFunds = () => req<FundLite[]>("/funds");

// ---------------------------------------------------------------- Module 1: verification / decision
export interface NoticeIn {
  notice_text: string;
  sender_domain?: string | null;
  sender_email?: string | null;
  use_model?: boolean;
}

export interface CheckView {
  passed: boolean;
  severity: string;
  observed: unknown;
  baseline: unknown;
  detail: string;
  similarity_to_gp?: number | null;
  similarity?: number | null;
}

export interface DecisionAlert {
  subject: string;
  body: string;
  failed_checks: string[];
  fraud_labels: string[];
  overall_severity: string;
  recommended_action: string;
}

export interface DecisionOut {
  status: "OK" | "NEEDS_ONBOARDING";
  note?: string;
  extracted: Record<string, unknown>;
  sender_domain: { value: string | null; source: string };
  fund_baseline?: {
    fund_id: string; fund_name: string; gp_entity: string; bank: string;
    routing: string; authorized_domains: string[];
  };
  checks?: Record<string, CheckView>;
  decision: "PASS" | "REVIEW" | "BLOCK";
  fraud: boolean;
  fraud_type: string | null;
  fraud_labels: string[];
  failed_checks: string[];
  overall_severity: string;
  confidence: string;
  alert: DecisionAlert | null;
  approval?: { approval_id: string; state: string; assigned_approver: unknown };
}

export const postDecision = (body: NoticeIn) =>
  req<DecisionOut>("/decision", { method: "POST", body: JSON.stringify(body) });

// ---------------------------------------------------------------- Module 2: approvals
export interface ApprovalRecord {
  approval_id: string;
  verification_report_id: string;
  fund_id: string | null;
  fund_name: string | null;
  assigned_approver: { name: string; email: string; role: string } | null;
  created_at: string;
  hub_status: string;
  hub_decision: string;
  hub_severity: string;
  state: "PENDING_APPROVAL" | "APPROVED" | "REJECTED" | "NEEDS_MORE_INFO";
  decision_by: string | null;
  decision_at: string | null;
  decision_note: string | null;
  supersedes: string | null;
  superseded_by?: string | null;
  verification_report?: {
    decision: string; confidence: string; overall_severity: string;
    extracted: Record<string, unknown>;
    failed_checks: string[];
    alert: DecisionAlert | null;
  };
}

export const getApprovalsPending = () => req<ApprovalRecord[]>("/approvals/pending");
export const getApprovalsAll = () => req<ApprovalRecord[]>("/approvals");
export const getApproval = (id: string) => req<ApprovalRecord>(`/approvals/${encodeURIComponent(id)}`);
export const decideApproval = (
  id: string,
  body: { state: "APPROVED" | "REJECTED" | "NEEDS_MORE_INFO"; approver: string; note?: string | null },
) => req<ApprovalRecord>(`/approvals/${encodeURIComponent(id)}/decide`, {
  method: "POST", body: JSON.stringify(body),
});
export const reverseApproval = (id: string, body: { approver: string; note: string }) =>
  req<ApprovalRecord>(`/approvals/${encodeURIComponent(id)}/reverse`, {
    method: "POST", body: JSON.stringify(body),
  });

// ---------------------------------------------------------------- Module 3: cash planning
export interface CashPosition {
  fund_id: string;
  fund_name: string;
  as_of_ledger: string;
  reference_date: string;
  confirmed_cash_balance: number;
  confirmed_components: {
    historical_ledger_balance: number;
    approved_capital_calls_total: number;
    approved_capital_calls_count: number;
  };
  near_term_obligations: {
    horizon_days: number;
    items: { due_date: string; amount: number }[];
    total_not_yet_realized: number;
    count: number;
    pending_outside_window: number;
  };
  excluded_from_balance: { REJECTED: number; NEEDS_MORE_INFO: number };
  reconciliation: { ok: boolean; delta: number };
  narrative?: { generated: boolean; narrative?: string; reason?: string };
}

export const getCashPlanningAll = (opts?: { narrative?: boolean }) =>
  req<CashPosition[]>(`/cash-planning${opts?.narrative ? "?narrative=true" : ""}`);
export const getCashPlanningOne = (fundId: string, opts?: { narrative?: boolean }) =>
  req<CashPosition>(`/cash-planning/${encodeURIComponent(fundId)}${opts?.narrative ? "?narrative=true" : ""}`);

// ---------------------------------------------------------------- Module 4: forecasting
export interface ForecastOut {
  fund_id: string;
  fund_name: string;
  as_of: string;
  type: string;
  sufficient_history: boolean;
  reason?: string;
  history_call_count: number;
  history_used: { date: string; amount: number; source: string }[];
  next_expected_call?: {
    point_estimate_date: string;
    window_start: string;
    window_end: string;
    estimated_amount: number;
    confidence: string;
    overdue_relative_to_as_of: boolean;
  };
  basis?: {
    avg_interval_days: number;
    interval_spread_days: number;
    interval_sample_size: number;
    low_confidence: boolean;
    estimated_amount_basis: string;
    amount_trend: string;
    first_call_date: string;
    last_call_date: string;
  };
  method?: string;
  context: {
    confirmed_cash_balance: number;
    near_term_obligations_total: number;
    near_term_obligations_count: number;
    as_of_ledger: string;
    note: string;
  };
  narrative?: { generated: boolean; narrative?: string; reason?: string };
}

export const getForecastingAll = (opts?: { narrative?: boolean }) =>
  req<ForecastOut[]>(`/forecasting${opts?.narrative ? "?narrative=true" : ""}`);
export const getForecastingOne = (fundId: string, opts?: { narrative?: boolean }) =>
  req<ForecastOut>(`/forecasting/${encodeURIComponent(fundId)}${opts?.narrative ? "?narrative=true" : ""}`);

// ---------------------------------------------------------------- Module 5: K-1 routing
export interface K1Extracted {
  fund_name?: string; lp_name?: string; tax_year?: string | number;
  ordinary_business_income?: number; guaranteed_payments?: number;
  extraction_source: string;
}
export interface K1Match { exact: boolean; match_score: number; fund_id?: string; fund_name?: string; lp_id?: string; lp_name?: string }
export interface K1Document {
  doc_id: string;
  case: string | null;
  received_at: string;
  status: "RECEIVED" | "ROUTED" | "NEEDS_REVIEW" | "AWAITING_EXTRACTION";
  extracted: K1Extracted | null;
  routed_at: string | null;
  matched_fund: K1Match | null;
  matched_lp: K1Match | null;
  routed_to: { recipient: string; queue: string; recipient_ref: string } | null;
  review_reason: string | null;
  review_detail: string | null;
  extraction_error: string | null;
  retry_count: number;
}
export interface K1ListOut {
  documents: K1Document[];
  summary: { total: number; routed: number; needs_review: number; awaiting_extraction: number };
}

export const getK1Routing = () => req<K1ListOut>("/k1-routing");
export const getK1RoutingForFund = (fundId: string) =>
  req<{ fund_id: string; fund_name: string; documents: K1Document[]; count: number }>(
    `/k1-routing/${encodeURIComponent(fundId)}`,
  );
export const ingestK1 = (documentText: string) =>
  req<K1Document>("/k1-routing/ingest", { method: "POST", body: JSON.stringify({ document_text: documentText }) });
export const retryPendingK1 = () =>
  req<{ attempted: number; resolved: number; still_awaiting: number; records: K1Document[] }>(
    "/k1-routing/retry-pending", { method: "POST" },
  );

// Legacy stub (agents/k1_routing.py) — reused only as a source of realistic
// synthetic K-1 document text to prefill the ingest form.
export interface K1Sample { doc_id: string; fund_id: string; lp_id: string; text: string }
export const getK1Samples = () => req<K1Sample[]>("/k1/samples");
