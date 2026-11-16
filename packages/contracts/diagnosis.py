from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# 诊断只接受可加口径，保证“分组贡献之和等于整体变化”的不变量可验证。
DiagnosisAggregation = Literal["sum"]
DiagnosisEvidenceStatus = Literal["supported", "contradicting", "unknown", "invalid", "insufficient"]
DiagnosisHypothesisStatus = Literal["leading", "supporting", "contradicted", "unknown", "rejected"]
DiagnosisVerificationStatus = Literal["valid", "invalid", "insufficient"]


class DiagnosisColumnRead(BaseModel):
    """诊断可选的指标、维度或时间字段。"""

    name: str
    label: str
    data_type: str
    aggregation: DiagnosisAggregation | None = None


class DiagnosisCapabilitiesRead(BaseModel):
    """当前数据源可由确定性引擎诊断的能力清单。"""

    datasource_id: str
    datasource_name: str
    table: str
    row_count: int = Field(ge=0)
    schema_revision: int = Field(ge=0)
    ready: bool
    message: str
    measures: list[DiagnosisColumnRead] = Field(default_factory=list)
    dimensions: list[DiagnosisColumnRead] = Field(default_factory=list)
    time_columns: list[DiagnosisColumnRead] = Field(default_factory=list)
    default_measure: str | None = None
    default_dimension: str | None = None
    default_time_column: str | None = None
    masked_fields: list[str] = Field(default_factory=list)


class DiagnosisRequest(BaseModel):
    """一次经营诊断的受约束配方输入，不允许自由 SQL。"""

    metric: str = Field(min_length=1, max_length=128)
    aggregation: DiagnosisAggregation = "sum"
    time_column: str = Field(min_length=1, max_length=128)
    dimension: str = Field(min_length=1, max_length=128)
    top_n: int = Field(default=6, ge=3, le=12)
    confidence_level: float = Field(default=0.95, ge=0.5, le=0.99)


class DiagnosisQuestionRequest(BaseModel):
    """经营诊断的自然语言问题。"""

    question: str = Field(min_length=2, max_length=500)


class DiagnosisIntentRead(BaseModel):
    """自然语言解析出的诊断意图；解析结果必须对应当前数据源真实字段。"""

    question: str
    understood: bool
    source: Literal["model", "rules"]
    metric: str | None = None
    metric_label: str | None = None
    dimension: str | None = None
    dimension_label: str | None = None
    time_column: str | None = None
    time_label: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    explanation: str
    clarification: str | None = None


class DiagnosisPeriodRead(BaseModel):
    """本期与基期的确定性聚合结果。"""

    current_label: str
    baseline_label: str
    current_total: float
    baseline_total: float
    delta: float
    delta_pct: float | None = None
    current_rows: int = Field(ge=0)
    baseline_rows: int = Field(ge=0)


class DiagnosisContributionRead(BaseModel):
    """一个维度分组的贡献分解与稳定性。"""

    group: str
    current_value: float
    baseline_value: float
    delta: float
    share_pct: float | None = None
    robust_periods: int = Field(ge=0)
    robust_consistent: int = Field(ge=0)
    status: Literal["supported", "contradicting", "unknown"] = "supported"


class DiagnosisChartRead(BaseModel):
    """瀑布图所需的最小数据，前端只做渲染不做计算。"""

    type: Literal["waterfall"] = "waterfall"
    labels: list[str] = Field(default_factory=list)
    deltas: list[float] = Field(default_factory=list)
    shares_pct: list[float | None] = Field(default_factory=list)
    baseline_label: str
    current_label: str
    baseline_total: float
    current_total: float


class DiagnosisEvidenceRead(BaseModel):
    """可独立复核的证据项。"""

    id: str
    group: str
    claim: str
    value: float
    unit: str
    method: str
    sample_size: int = Field(ge=0)
    robust_periods: int = Field(ge=0)
    robust_consistent: int = Field(ge=0)
    missing_rate: float = Field(ge=0.0, le=1.0)
    confidence_level: float = Field(ge=0.0, le=1.0)
    interval: list[float] | None = None
    caveats: list[str] = Field(default_factory=list)
    status: DiagnosisEvidenceStatus = "supported"


class DiagnosisHypothesisRead(BaseModel):
    """带证据引用的排序假设，不宣称因果。"""

    id: str
    text: str
    operators: list[str] = Field(default_factory=list)
    supporting: list[str] = Field(default_factory=list)
    contradicting: list[str] = Field(default_factory=list)
    score: float = Field(ge=0.0, le=1.0)
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    status: DiagnosisHypothesisStatus = "supporting"


class DiagnosisVerificationCheckRead(BaseModel):
    """一条可独立审计的不变量检查。"""

    name: str
    label: str
    passed: bool
    detail: str
    confidence_level: float = Field(ge=0.0, le=1.0)


class DiagnosisVerificationRead(BaseModel):
    """诊断结论的确定性验证结果。"""

    status: DiagnosisVerificationStatus
    passed: int = Field(ge=0)
    total: int = Field(ge=0)
    confidence_level: float = Field(ge=0.0, le=1.0)
    checks: list[DiagnosisVerificationCheckRead] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)


class DiagnosisQualityRead(BaseModel):
    """诊断窗口内的数据质量摘要。"""

    missing_rate: float = Field(ge=0.0, le=1.0)
    coverage_pct: float = Field(ge=0.0, le=100.0)
    freshness: Literal["ok", "stale", "unknown"]
    missing_cells: int = Field(ge=0)
    sampled_rows: int = Field(ge=0)


class DiagnosisResultRead(BaseModel):
    """经营诊断的完整可复核结果。"""

    run_id: str
    engine_version: str = "V2.0"
    datasource_id: str
    datasource_name: str
    table: str
    schema_revision: int = Field(ge=0)
    metric_name: str
    metric_label: str
    aggregation: DiagnosisAggregation
    dimension_name: str
    dimension_label: str
    time_column: str
    time_label: str
    period: DiagnosisPeriodRead
    contributions: list[DiagnosisContributionRead]
    others: DiagnosisContributionRead | None = None
    chart: DiagnosisChartRead
    evidence: list[DiagnosisEvidenceRead]
    hypotheses: list[DiagnosisHypothesisRead]
    verification: DiagnosisVerificationRead
    quality: DiagnosisQualityRead
    narrative: str
    recipe: dict[str, Any]
    recipe_id: str
    recipe_hash: str
    generated_at: datetime
    duration_ms: int = Field(ge=0)


__all__ = [
    "DiagnosisAggregation",
    "DiagnosisCapabilitiesRead",
    "DiagnosisChartRead",
    "DiagnosisColumnRead",
    "DiagnosisContributionRead",
    "DiagnosisEvidenceRead",
    "DiagnosisHypothesisRead",
    "DiagnosisIntentRead",
    "DiagnosisPeriodRead",
    "DiagnosisQualityRead",
    "DiagnosisQuestionRequest",
    "DiagnosisRequest",
    "DiagnosisResultRead",
    "DiagnosisVerificationCheckRead",
    "DiagnosisVerificationRead",
]
