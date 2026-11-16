import { requestJson } from "./client";

export interface DiagnosisColumn {
  name: string;
  label: string;
  data_type: string;
  aggregation: "sum" | null;
}

export interface DiagnosisCapabilities {
  datasource_id: string;
  datasource_name: string;
  table: string;
  row_count: number;
  schema_revision: number;
  ready: boolean;
  message: string;
  measures: DiagnosisColumn[];
  dimensions: DiagnosisColumn[];
  time_columns: DiagnosisColumn[];
  default_measure: string | null;
  default_dimension: string | null;
  default_time_column: string | null;
  masked_fields: string[];
}

export interface DiagnosisRequest {
  metric: string;
  time_column: string;
  dimension: string;
  top_n?: number;
  confidence_level?: number;
}

export interface DiagnosisPeriod {
  current_label: string;
  baseline_label: string;
  current_total: number;
  baseline_total: number;
  delta: number;
  delta_pct: number | null;
  current_rows: number;
  baseline_rows: number;
}

export interface DiagnosisContribution {
  group: string;
  current_value: number;
  baseline_value: number;
  delta: number;
  share_pct: number | null;
  robust_periods: number;
  robust_consistent: number;
  status: "supported" | "contradicting" | "unknown";
}

export interface DiagnosisChart {
  type: "waterfall";
  labels: string[];
  deltas: number[];
  shares_pct: Array<number | null>;
  baseline_label: string;
  current_label: string;
  baseline_total: number;
  current_total: number;
}

export interface DiagnosisEvidence {
  id: string;
  group: string;
  claim: string;
  value: number;
  unit: string;
  method: string;
  sample_size: number;
  robust_periods: number;
  robust_consistent: number;
  missing_rate: number;
  confidence_level: number;
  interval: number[] | null;
  caveats: string[];
  status: "supported" | "contradicting" | "unknown" | "invalid" | "insufficient";
}

export interface DiagnosisHypothesis {
  id: string;
  text: string;
  operators: string[];
  supporting: string[];
  contradicting: string[];
  score: number;
  score_breakdown: Record<string, number>;
  status: "leading" | "supporting" | "contradicted" | "unknown" | "rejected";
}

export interface DiagnosisVerificationCheck {
  name: string;
  label: string;
  passed: boolean;
  detail: string;
  confidence_level: number;
}

export interface DiagnosisVerification {
  status: "valid" | "invalid" | "insufficient";
  passed: number;
  total: number;
  confidence_level: number;
  checks: DiagnosisVerificationCheck[];
  caveats: string[];
}

export interface DiagnosisQuality {
  missing_rate: number;
  coverage_pct: number;
  freshness: "ok" | "stale" | "unknown";
  missing_cells: number;
  sampled_rows: number;
}

export interface DiagnosisResult {
  run_id: string;
  engine_version: string;
  datasource_id: string;
  datasource_name: string;
  table: string;
  schema_revision: number;
  metric_name: string;
  metric_label: string;
  aggregation: "sum";
  dimension_name: string;
  dimension_label: string;
  time_column: string;
  time_label: string;
  period: DiagnosisPeriod;
  contributions: DiagnosisContribution[];
  others: DiagnosisContribution | null;
  chart: DiagnosisChart;
  evidence: DiagnosisEvidence[];
  hypotheses: DiagnosisHypothesis[];
  verification: DiagnosisVerification;
  quality: DiagnosisQuality;
  narrative: string;
  recipe: Record<string, unknown>;
  recipe_id: string;
  recipe_hash: string;
  generated_at: string;
  duration_ms: number;
}

export interface DiagnosisIntent {
  question: string;
  understood: boolean;
  source: "model" | "rules";
  metric: string | null;
  metric_label: string | null;
  dimension: string | null;
  dimension_label: string | null;
  time_column: string | null;
  time_label: string | null;
  confidence: number;
  explanation: string;
  clarification: string | null;
}

export function getDiagnosisCapabilities(datasourceId: string): Promise<DiagnosisCapabilities> {
  return requestJson<DiagnosisCapabilities>(
    `/datasources/${encodeURIComponent(datasourceId)}/diagnosis/capabilities`,
  );
}

export function parseDiagnosisQuestion(
  datasourceId: string,
  question: string,
): Promise<DiagnosisIntent> {
  return requestJson<DiagnosisIntent>(
    `/datasources/${encodeURIComponent(datasourceId)}/diagnosis/intent`,
    { method: "POST", body: JSON.stringify({ question }) },
  );
}

export function runDiagnosis(
  datasourceId: string,
  body: DiagnosisRequest,
): Promise<DiagnosisResult> {
  return requestJson<DiagnosisResult>(
    `/datasources/${encodeURIComponent(datasourceId)}/diagnosis/runs`,
    { method: "POST", body: JSON.stringify(body) },
  );
}
