// Mirrors src/ledgerguard/api/schemas.py. The snapshot file and the live API return the same
// shapes, so the UI parses one type either way and nothing branches on data source.

export type SignalStatus = "pass" | "warn" | "fail";

export interface BankLine {
  bank_line_id: string;
  utr: string | null;
  credit_paise: number;
  narration: string;
  value_date: string;
}

export interface Payment {
  payment_id: string;
  order_id: string;
  amount_paise: number;
  fee_paise: number;
  tax_paise: number;
  net_paise: number;
  captured_at: string;
  role: "matched" | "candidate";
}

export interface MatchSignal {
  label: string;
  value: string;
  status: SignalStatus;
  detail: string | null;
}

export interface PolicyCheck {
  label: string;
  required: string;
  actual: string;
  passed: boolean;
}

export interface QueueItem {
  bank_line_id: string;
  value_date: string;
  credit_paise: number;
  narration: string;
  resolver: string;
  rule_id: string | null;
  action: string;
  reason_code: string | null;
  calibrated_confidence: number;
  threshold: number;
  difficulty: string;
  order_ids: string[];
  has_anomaly: boolean;
}

export interface Dashboard {
  data_provenance: string;
  dataset: string;
  batch_id: string;
  total_bank_lines: number;
  counts_by_action: Record<string, number>;
  refused: number;
  auto_post_rate: number;
  precision_auto_posted: number;
  false_auto_match_rate: number;
  threshold: number;
  total_credit_paise: number;
  llm_invocation_count: number;
  demo_pair: string[];
}

export interface Anomaly {
  reason_code: string;
  evidence: string[];
}

export interface Investigation {
  data_provenance: string;
  bank_line: BankLine;
  payments: Payment[];
  resolver: string;
  rule_id: string | null;
  model: string | null;
  order_ids: string[];
  raw_confidence: number;
  calibrated_confidence: number;
  threshold: number;
  action: string;
  reason_code: string | null;
  evidence: string[];
  signals: MatchSignal[];
  policy: PolicyCheck[];
  anomalies: Anomaly[];
  difficulty: string;
  ground_truth_order_ids: string[] | null;
  decision_was_correct: boolean | null;
}

export interface ExecuteResult {
  data_provenance: string;
  bank_line_id: string;
  authorized: boolean;
  action: string;
  reason_code: string | null;
  policy: PolicyCheck[];
  message: string;
  decision_id: string | null;
  idempotency_key: string | null;
  newly_posted: boolean | null;
}

export interface AuditEvent {
  decision_id: string;
  batch_id: string;
  bank_line_id: string;
  resolver: string;
  action: string;
  reason_code: string | null;
  calibrated_confidence: number | null;
  threshold: number | null;
  idempotency_key: string;
  created_at: string;
  evidence: string[];
}

export interface AblationRow {
  stratum: string;
  n: number;
  rules_only_f1: number;
  hybrid_f1: number;
  llm_only_f1: number;
  llm_calls: number;
}

export interface OperationalRow {
  stratum: string;
  n: number;
  auto_match_rate: number;
  precision_auto_posted: number;
  recall: number;
  f1: number;
  false_auto_match_rate: number;
}

export interface RuleLearningRow {
  batch: number;
  total: number;
  invocation_rate: number;
  precision_auto_post: number;
  cost_usd: number;
  promoted: string[];
}

export interface Evaluation {
  ablation: AblationRow[];
  delta_hard_adversarial: number;
  delta_easy: number;
  band: string;
  verdict: string;
  operational: OperationalRow[];
  rule_learning: RuleLearningRow[];
  ece_raw: number;
  ece_calibrated: number;
  redteam_survived: number;
  redteam_total: number;
}

export interface Snapshot {
  generated_from: string;
  dashboard: Dashboard;
  queue: { data_provenance: string; total: number; items: QueueItem[] };
  investigations: Record<string, Investigation>;
  evaluation: Evaluation;
}

/** Where the data on screen came from. Never conflated — the UI labels each state. */
export type DataSource = "loading" | "snapshot" | "waking" | "live";
