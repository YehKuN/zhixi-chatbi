"""可验证经营诊断引擎：确定性聚合、贡献分解、不变量验证与假设-证据图。

本模块是软著《智析 ChatBI 可验证经营诊断引擎 V2.0》在平台内的运行入口：
LLM 不参与计算，所有数字都由受控只读 SQL + 确定性算子得到，并附带证据与验证。
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from application.datasources import DataSourceService
from contracts.datasources import DataSourceRead, SchemaColumnRead, SchemaSummaryRead, SchemaTableRead
from contracts.diagnosis import (
    DiagnosisCapabilitiesRead,
    DiagnosisChartRead,
    DiagnosisColumnRead,
    DiagnosisContributionRead,
    DiagnosisEvidenceRead,
    DiagnosisHypothesisRead,
    DiagnosisPeriodRead,
    DiagnosisQualityRead,
    DiagnosisRequest,
    DiagnosisResultRead,
    DiagnosisVerificationCheckRead,
    DiagnosisVerificationRead,
)
from contracts.errors import AppError, ErrorCode
from contracts.status import DataSourceStatus
from data_gateway.types import QueryCancelToken

ENGINE_VERSION = "V2.0"
_MAX_DIMENSION_VALUES = 60
_MAX_ROBUSTNESS_PERIODS = 3
_MISSING_RATE_LIMIT = 0.05
# 平台默认查询上限是 100 行；诊断显式声明 500，同时保证结果规模远低于该值。
_QUERY_ROW_LIMIT = 500

_NUMERIC_TYPES = {
    "HUGEINT",
    "UBIGINT",
    "BIGINT",
    "INTEGER",
    "INT",
    "SMALLINT",
    "TINYINT",
    "DOUBLE",
    "REAL",
    "DECIMAL",
    "NUMERIC",
    "FLOAT",
    "NUMBER",
    "INT64",
    "FLOAT64",
}
_BOOLEAN_TYPES = {"BOOLEAN", "BOOL"}
_TIME_TYPES = {"DATE", "TIMESTAMP", "DATETIME", "TIMESTAMP WITH TIME ZONE", "TIME"}
_TIME_NAME_HINTS = ("date", "time", "month", "period", "week", "quarter", "year")
_TIME_HELPER_NAMES = {"month_num", "day", "year_num", "week_num", "quarter_num"}
_IDENTIFIER_HINTS = ("_id", "_code", "_uuid", "_key", "_no")
_MEASURE_PRIORITY = (
    "revenue",
    "order_amount",
    "amount",
    "sales",
    "gmv",
    "turnover",
    "income",
    "profit",
    "balance",
    "cost",
    "price",
    "value",
    "duration",
    "campaign",
    "previous",
    "age",
)
_DIMENSION_PRIORITY = (
    "region",
    "area",
    "channel",
    "category",
    "segment",
    "job",
    "traffic_type",
    "visitor_type",
    "education",
    "marital",
    "contact",
    "poutcome",
    "browser",
    "operating_systems",
    "housing",
    "loan",
    "type",
    "status",
    "source",
)
_TIME_PRIORITY = ("order_date", "date", "month", "period", "created_at", "updated_at", "timestamp", "time")
_COLUMN_LABELS = {
    "revenue": "营收",
    "amount": "金额",
    "order_amount": "订单金额",
    "order_count": "订单数",
    "order_date": "订单日期",
    "sales": "销售额",
    "gmv": "GMV",
    "turnover": "营业额",
    "income": "收入",
    "profit": "利润",
    "balance": "账户余额",
    "age": "年龄",
    "duration": "通话时长",
    "campaign": "联系次数",
    "previous": "上次联系次数",
    "pdays": "距上次联系天数",
    "month": "月份",
    "month_num": "月份序号",
    "day": "日期序号",
    "region": "区域",
    "area": "大区",
    "channel": "渠道",
    "category": "品类",
    "segment": "客群",
    "job": "职业",
    "marital": "婚姻状态",
    "education": "教育程度",
    "contact": "联系方式",
    "poutcome": "上次活动结果",
    "housing": "住房贷款",
    "loan": "个人贷款",
    "credit_default": "信用违约",
    "traffic_type": "流量来源",
    "visitor_type": "访客类型",
    "browser": "浏览器",
    "operating_systems": "操作系统",
    "page_values": "页面价值",
    "bounce_rates": "跳出率",
    "exit_rates": "退出率",
    "product_related": "产品页浏览数",
    "administrative": "行政页面数",
    "subscribed_flag": "营销认购",
    "purchased_flag": "购买转化",
    "converted_flag": "转化",
}
_MONTH_NAMES = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


@dataclass
class _SourceContext:
    source: DataSourceRead
    schema: SchemaSummaryRead
    table: SchemaTableRead
    columns: list[SchemaColumnRead]
    masked: set[str]
    by_name: dict[str, SchemaColumnRead] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.by_name = {column.name.casefold(): column for column in self.columns}


@dataclass
class _GroupStat:
    name: str
    current_value: float = 0.0
    baseline_value: float = 0.0
    current_rows: int = 0
    baseline_rows: int = 0
    series: dict[str, tuple[float, int]] = field(default_factory=dict)

    @property
    def delta(self) -> float:
        return self.current_value - self.baseline_value


@dataclass(frozen=True)
class _Period:
    raw: str
    label: str
    order: tuple[int, float, str]


class DiagnosisService:
    """在当前企业的真实数据源上执行一次可复核的经营诊断。"""

    def __init__(self, datasources: DataSourceService, *, query_timeout_seconds: int = 30) -> None:
        self.datasources = datasources
        self.query_timeout_seconds = query_timeout_seconds

    async def capabilities(self, datasource_id: str) -> DiagnosisCapabilitiesRead:
        context = await self._context(datasource_id)
        measures = _measure_columns(context.columns)
        measure_names = {column.name.casefold() for column in measures}
        time_columns = _time_columns(context.columns)
        time_names = {column.name.casefold() for column in time_columns}
        dimensions = _dimension_columns(context.columns, measure_names, time_names)
        ready = bool(measures and dimensions and time_columns)
        if ready:
            message = "已识别可诊断的指标、时间字段和分组字段，可以直接开始诊断。"
        else:
            missing = []
            if not measures:
                missing.append("数值指标")
            if not time_columns:
                missing.append("时间字段")
            if not dimensions:
                missing.append("可分组维度")
            message = "当前数据源缺少" + "、".join(missing) + "，暂时无法运行经营诊断。"
        return DiagnosisCapabilitiesRead(
            datasource_id=context.source.id,
            datasource_name=context.source.name,
            table=context.table.name,
            row_count=context.table.row_count or 0,
            schema_revision=context.source.schema_revision,
            ready=ready,
            message=message,
            measures=measures,
            dimensions=dimensions,
            time_columns=time_columns,
            default_measure=_default_name(measures, _MEASURE_PRIORITY),
            default_dimension=_default_name(dimensions, _DIMENSION_PRIORITY),
            default_time_column=_default_name(time_columns, _TIME_PRIORITY),
            masked_fields=sorted(context.masked),
        )

    async def run(self, datasource_id: str, request: DiagnosisRequest) -> DiagnosisResultRead:
        started = time.monotonic()
        context = await self._context(datasource_id)
        metric = self._require_column(context, request.metric, "指标", numeric=True)
        dimension = self._require_column(context, request.dimension, "维度")
        time_column = self._require_column(context, request.time_column, "时间字段")
        if dimension.name.casefold() == metric.name.casefold():
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "维度不能与指标使用同一字段",
                status_code=422,
            )
        order_column = _order_column(context, time_column)
        dialect = context.schema.dialect

        distinct = await self._scalar(
            datasource_id,
            _distinct_sql(dialect, context.table.name, dimension),
            context.source.schema_revision,
        )
        if distinct > _MAX_DIMENSION_VALUES:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                f"维度「{_label(dimension.name)}」有 {distinct} 个取值，超过贡献分解上限 "
                f"{_MAX_DIMENSION_VALUES}，请换一个分组字段",
                status_code=422,
                details={"distinct_values": distinct, "limit": _MAX_DIMENSION_VALUES},
            )

        period_rows_raw = await self._query_rows(
            datasource_id,
            _periods_sql(dialect, context.table.name, time_column, order_column, dimension, metric),
            context.source.schema_revision,
        )
        if not period_rows_raw:
            raise AppError(ErrorCode.VALIDATION_ERROR, "当前数据源没有可诊断的记录", status_code=422)
        if len(period_rows_raw) >= _QUERY_ROW_LIMIT:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                f"时间跨度过大：已超过 {_QUERY_ROW_LIMIT} 个周期，无法保证诊断结果完整",
                status_code=422,
                details={"period_limit": _QUERY_ROW_LIMIT},
            )

        period_rows: dict[str, tuple[_Period, float, int]] = {}
        missing_group = 0
        missing_period = 0
        sampled_rows = 0
        for row in period_rows_raw:
            row_count = int(_to_float(row.get("row_count")) or 0)
            sampled_rows += row_count
            missing_group += int(_to_float(row.get("missing_group")) or 0)
            raw_period = row.get("period")
            if raw_period is None or str(raw_period).strip() == "":
                missing_period += row_count
                continue
            raw_key = _normalize_period(str(raw_period))
            raw_order = row.get("period_order")
            value = _to_float(row.get("value")) or 0.0
            if raw_key not in period_rows:
                period_rows[raw_key] = (
                    _Period(
                        raw=raw_key,
                        label=_period_label(raw_key, raw_order),
                        order=_period_order(raw_key, raw_order),
                    ),
                    value,
                    row_count,
                )
            else:
                period, total, count = period_rows[raw_key]
                period_rows[raw_key] = (period, total + value, count + row_count)

        if len(period_rows) < 2:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "至少需要两个可比周期才能做环比诊断，请检查时间字段或补充历史数据",
                status_code=422,
                details={"period_count": len(period_rows)},
            )

        periods = sorted((item[0] for item in period_rows.values()), key=lambda item: item.order)
        totals = {raw: item[1] for raw, item in period_rows.items()}
        current_period = periods[-1]
        baseline_period = periods[-2]
        current_total = totals[current_period.raw]
        baseline_total = totals[baseline_period.raw]
        total_delta = current_total - baseline_total
        current_rows = period_rows[current_period.raw][2]
        baseline_rows = period_rows[baseline_period.raw][2]

        # 只取最近四个周期做分组序列：既够算三次环比稳定性，又不会被结果行数上限截断。
        watch_periods = [item.raw for item in periods[-4:]]
        rows = await self._query_rows(
            datasource_id,
            _series_sql(
                dialect,
                context.table.name,
                time_column,
                dimension,
                metric,
                watch_periods,
            ),
            context.source.schema_revision,
        )
        groups: dict[str, _GroupStat] = {}
        for row in rows:
            raw_period = row.get("period")
            if raw_period is None or str(raw_period).strip() == "":
                continue
            raw_key = _normalize_period(str(raw_period))
            value = _to_float(row.get("value")) or 0.0
            row_count = int(_to_float(row.get("row_count")) or 0)
            group_name = str(row.get("grp") or "未标注")
            stat = groups.setdefault(group_name, _GroupStat(name=group_name))
            previous = stat.series.get(raw_key)
            if previous is None:
                stat.series[raw_key] = (value, row_count)
            else:
                stat.series[raw_key] = (previous[0] + value, previous[1] + row_count)

        stats: list[_GroupStat] = []
        for stat in groups.values():
            current_value, current_count = stat.series.get(current_period.raw, (0.0, 0))
            baseline_value, baseline_count = stat.series.get(baseline_period.raw, (0.0, 0))
            stat.current_value = current_value
            stat.baseline_value = baseline_value
            stat.current_rows = current_count
            stat.baseline_rows = baseline_count
            stats.append(stat)
        stats.sort(key=lambda item: abs(item.delta), reverse=True)

        selected = stats[: request.top_n]
        remainder = stats[request.top_n:]
        missing_rate = (missing_group + missing_period) / max(1, sampled_rows * 2)
        dimension_missing_rate = missing_group / max(1, sampled_rows)

        contributions: list[DiagnosisContributionRead] = []
        others: DiagnosisContributionRead | None = None
        sign = 1.0 if total_delta > 0 else -1.0 if total_delta < 0 else 0.0
        for stat in selected:
            robust_periods, robust_consistent = _robustness(stat, periods)
            contributions.append(
                DiagnosisContributionRead(
                    group=stat.name,
                    current_value=round(stat.current_value, 4),
                    baseline_value=round(stat.baseline_value, 4),
                    delta=round(stat.delta, 4),
                    share_pct=_share(stat.delta, total_delta),
                    robust_periods=robust_periods,
                    robust_consistent=robust_consistent,
                    status=(
                        "unknown"
                        if sign == 0
                        else "supported"
                        if robust_periods == 0 or robust_consistent > 0
                        else "contradicting"
                    ),
                )
            )
        if remainder:
            rest_current = sum(item.current_value for item in remainder)
            rest_baseline = sum(item.baseline_value for item in remainder)
            rest_delta = rest_current - rest_baseline
            others = DiagnosisContributionRead(
                group="其他分组",
                current_value=round(rest_current, 4),
                baseline_value=round(rest_baseline, 4),
                delta=round(rest_delta, 4),
                share_pct=_share(rest_delta, total_delta),
                robust_periods=0,
                robust_consistent=0,
                status="unknown" if sign == 0 else "supported",
            )

        evidence, hypotheses = _build_evidence_and_hypotheses(
            selected=selected,
            periods=periods,
            totals=totals,
            contributions=contributions,
            metric_label=_label(metric.name),
            confidence_level=request.confidence_level,
            dimension_missing_rate=dimension_missing_rate,
        )
        verification = _verify(
            total_delta=total_delta,
            contributions=contributions,
            others=others,
            current_rows=current_rows,
            baseline_rows=baseline_rows,
            dimension_missing_rate=dimension_missing_rate,
            confidence_level=request.confidence_level,
            period_count=len(periods),
        )

        latest_date = _latest_calendar_date(periods)
        freshness = "unknown"
        if latest_date is not None:
            freshness = "stale" if (datetime.now(UTC).date() - latest_date).days > 120 else "ok"
        quality = DiagnosisQualityRead(
            missing_rate=round(missing_rate, 6),
            coverage_pct=round(max(0.0, 100 * (1 - missing_rate)), 2),
            freshness=freshness,
            missing_cells=missing_group + missing_period,
            sampled_rows=sampled_rows,
        )

        period = DiagnosisPeriodRead(
            current_label=current_period.label,
            baseline_label=baseline_period.label,
            current_total=round(current_total, 4),
            baseline_total=round(baseline_total, 4),
            delta=round(total_delta, 4),
            delta_pct=(
                round(total_delta / abs(baseline_total) * 100, 4) if baseline_total else None
            ),
            current_rows=current_rows,
            baseline_rows=baseline_rows,
        )
        chart = DiagnosisChartRead(
            labels=[item.group for item in contributions] + ([others.group] if others else []),
            deltas=[item.delta for item in contributions] + ([others.delta] if others else []),
            shares_pct=[item.share_pct for item in contributions]
            + ([others.share_pct] if others else []),
            baseline_label=baseline_period.label,
            current_label=current_period.label,
            baseline_total=round(baseline_total, 4),
            current_total=round(current_total, 4),
        )
        recipe = {
            "engine": "zhixi-diagnose",
            "version": ENGINE_VERSION,
            "datasource_id": context.source.id,
            "schema_revision": context.source.schema_revision,
            "metric": metric.name,
            "aggregation": "sum",
            "dimension": dimension.name,
            "time_column": time_column.name,
            "comparison": "previous_period",
            "baseline_period": baseline_period.raw,
            "current_period": current_period.raw,
            "top_n": request.top_n,
            "steps": [
                {
                    "id": "aggregate",
                    "op": "aggregate",
                    "params": {
                        "metric": metric.name,
                        "group_by": [time_column.name, dimension.name],
                    },
                },
                {
                    "id": "compare",
                    "op": "compare",
                    "params": {"baseline": "previous_period"},
                },
                {
                    "id": "decompose",
                    "op": "decompose",
                    "params": {"dimension": dimension.name, "mode": "additive"},
                },
                {
                    "id": "verify",
                    "op": "verify",
                    "params": {
                        "invariants": [
                            "sum_contributions_equals_delta",
                            "shares_sum_to_one",
                        ]
                    },
                },
            ],
        }
        canonical = json.dumps(
            recipe, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        recipe_hash = hashlib.sha256(canonical).hexdigest()
        narrative = _narrative(
            period=period,
            contributions=contributions,
            others=others,
            hypotheses=hypotheses,
            verification=verification,
            quality=quality,
            metric_label=_label(metric.name),
            dimension_label=_label(dimension.name),
        )
        return DiagnosisResultRead(
            run_id=f"diag_{uuid.uuid4().hex[:16]}",
            engine_version=ENGINE_VERSION,
            datasource_id=context.source.id,
            datasource_name=context.source.name,
            table=context.table.name,
            schema_revision=context.source.schema_revision,
            metric_name=metric.name,
            metric_label=_label(metric.name),
            aggregation="sum",
            dimension_name=dimension.name,
            dimension_label=_label(dimension.name),
            time_column=time_column.name,
            time_label=_label(time_column.name),
            period=period,
            contributions=contributions,
            others=others,
            chart=chart,
            evidence=evidence,
            hypotheses=hypotheses,
            verification=verification,
            quality=quality,
            narrative=narrative,
            recipe=recipe,
            recipe_id=f"diag_recipe_{recipe_hash[:12]}",
            recipe_hash=recipe_hash,
            generated_at=datetime.now(UTC),
            duration_ms=int((time.monotonic() - started) * 1000),
        )

    def _require_column(
        self,
        context: _SourceContext,
        name: str,
        label: str,
        *,
        numeric: bool = False,
    ) -> SchemaColumnRead:
        column = context.by_name.get(name.casefold())
        if column is None or column.name.casefold() in context.masked:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                f"{label}字段不可用或已被遮蔽：{name}",
                status_code=422,
                details={"column": name},
            )
        if numeric and not _is_numeric(column) and not _is_boolean(column):
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                f"指标字段必须是数值类型：{name}",
                status_code=422,
                details={"column": name},
            )
        return column

    async def _context(self, datasource_id: str) -> _SourceContext:
        source = await self.datasources.get_readable(datasource_id)
        if source.status not in {
            DataSourceStatus.SCHEMA_READY.value,
            DataSourceStatus.READY.value,
        } or not source.mask_fields_confirmed:
            raise AppError(
                ErrorCode.DATASOURCE_NOT_READY,
                "数据源尚未完成检查或未确认遮蔽字段",
                status_code=409,
            )
        schema = await self.datasources.get_schema(datasource_id)
        if not schema.tables:
            raise AppError(
                ErrorCode.DATASOURCE_NOT_READY,
                "数据源没有可分析的物理表",
                status_code=409,
            )
        table = next((item for item in schema.tables if item.name == "dataset"), schema.tables[0])
        masked = {name.casefold() for name in source.mask_fields}
        columns = [column for column in table.columns if column.name.casefold() not in masked]
        return _SourceContext(
            source=source,
            schema=schema,
            table=table,
            columns=columns,
            masked=masked,
        )

    async def _query_rows(
        self,
        datasource_id: str,
        sql: str,
        schema_revision: int,
    ) -> list[dict[str, Any]]:
        result = await self.datasources.run_readonly_sql(
            datasource_id=datasource_id,
            sql=sql,
            cancel_token=QueryCancelToken(),
            timeout_seconds=self.query_timeout_seconds,
            expected_schema_revision=schema_revision,
        )
        return [dict(zip(result.columns, row, strict=True)) for row in result.rows]

    async def _scalar(self, datasource_id: str, sql: str, schema_revision: int) -> int:
        rows = await self._query_rows(datasource_id, sql, schema_revision)
        if not rows:
            return 0
        return int(_to_float(rows[0].get("distinct_values")) or 0)


def _quote(name: str, dialect: str) -> str:
    if dialect == "mysql":
        escaped = name.replace("`", "``")
        return f"`{escaped}`"
    escaped = name.replace('"', '""')
    return f'"{escaped}"'


def _cast_text(expression: str, dialect: str) -> str:
    if dialect == "mysql":
        return f"CAST({expression} AS CHAR)"
    return f"CAST({expression} AS VARCHAR)"


def _metric_expression(column: SchemaColumnRead, dialect: str, aggregation: str = "sum") -> str:
    reference = _quote(column.name, dialect)
    function = "AVG" if aggregation == "avg" else "SUM"
    if _is_boolean(column):
        return f"{function}(CASE WHEN {reference} THEN 1 ELSE 0 END)"
    if column.name.casefold().endswith("_flag") and _is_numeric(column):
        return f"{function}(CASE WHEN {reference} = 1 THEN 1 ELSE 0 END)"
    return f"{function}(CAST({reference} AS DOUBLE))"


def _distinct_sql(dialect: str, table_name: str, dimension: SchemaColumnRead) -> str:
    group = _cast_text(_quote(dimension.name, dialect), dialect)
    return f"SELECT COUNT(DISTINCT {group}) AS distinct_values FROM {_quote(table_name, dialect)}"


def _period_expression(time_reference: str, dialect: str) -> str:
    """把日期、时间戳或月份统一截取到月粒度，避免按天分组。"""

    return f"SUBSTR({_cast_text(time_reference, dialect)}, 1, 7)"


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _periods_sql(
    dialect: str,
    table_name: str,
    time_column: SchemaColumnRead,
    order_column: SchemaColumnRead | None,
    dimension: SchemaColumnRead,
    metric: SchemaColumnRead,
) -> str:
    """只返回周期合计，行数最多等于周期数，不会被查询行数上限截断。"""

    time_reference = _quote(time_column.name, dialect)
    period_expression = _period_expression(time_reference, dialect)
    order_expression = (
        _quote(order_column.name, dialect)
        if order_column is not None
        else period_expression
    )
    expressions = [
        f"{period_expression} AS period",
        f"{order_expression} AS period_order",
        f"{_metric_expression(metric, dialect)} AS value",
        "COUNT(*) AS row_count",
        f"SUM(CASE WHEN {_quote(dimension.name, dialect)} IS NULL THEN 1 ELSE 0 END) "
        "AS missing_group",
    ]
    group_by = [period_expression]
    if order_column is not None and order_column.name.casefold() != time_column.name.casefold():
        group_by.append(order_expression)
    return (
        f"SELECT {', '.join(expressions)} FROM {_quote(table_name, dialect)} "
        f"GROUP BY {', '.join(group_by)} ORDER BY 2 LIMIT {_QUERY_ROW_LIMIT}"
    )


def _series_sql(
    dialect: str,
    table_name: str,
    time_column: SchemaColumnRead,
    dimension: SchemaColumnRead,
    metric: SchemaColumnRead,
    periods: list[str],
) -> str:
    """只取最近几个周期的分组序列，保证结果规模远低于查询上限。"""

    time_reference = _quote(time_column.name, dialect)
    period_expression = _period_expression(time_reference, dialect)
    dimension_expression = _cast_text(_quote(dimension.name, dialect), dialect)
    filters = ", ".join(_sql_literal(item) for item in periods)
    return (
        f"SELECT {dimension_expression} AS grp, {period_expression} AS period, "
        f"{_metric_expression(metric, dialect)} AS value, COUNT(*) AS row_count "
        f"FROM {_quote(table_name, dialect)} "
        f"WHERE {period_expression} IN ({filters}) "
        f"GROUP BY {dimension_expression}, {period_expression} "
        f"LIMIT {_QUERY_ROW_LIMIT}"
    )


def _measure_columns(columns: list[SchemaColumnRead]) -> list[DiagnosisColumnRead]:
    candidates = [
        column
        for column in columns
        if (_is_numeric(column) or _is_boolean(column))
        and not _looks_like_identifier(column.name)
        and column.name.casefold() not in _TIME_HELPER_NAMES
    ]
    candidates.sort(key=lambda column: _priority(column.name, _MEASURE_PRIORITY))
    return [
        DiagnosisColumnRead(
            name=column.name,
            label=_label(column.name),
            data_type=column.type,
            aggregation="sum",
        )
        for column in candidates
    ]


def _dimension_columns(
    columns: list[SchemaColumnRead],
    measure_names: set[str],
    time_names: set[str],
) -> list[DiagnosisColumnRead]:
    candidates = [
        column
        for column in columns
        if column.name.casefold() not in measure_names
        and column.name.casefold() not in time_names
        and column.name.casefold() not in _TIME_HELPER_NAMES
        and not _looks_like_identifier(column.name)
        and not _is_time_type(column)
        and (not _is_numeric(column) or _is_boolean(column) or column.name.casefold().endswith("_flag"))
    ]
    candidates.sort(key=lambda column: _priority(column.name, _DIMENSION_PRIORITY))
    return [
        DiagnosisColumnRead(name=column.name, label=_label(column.name), data_type=column.type)
        for column in candidates
    ]


def _time_columns(columns: list[SchemaColumnRead]) -> list[DiagnosisColumnRead]:
    candidates = [
        column
        for column in columns
        if column.name.casefold() not in _TIME_HELPER_NAMES
        and (_is_time_type(column) or _looks_like_time_name(column.name))
    ]
    candidates.sort(key=lambda column: _priority(column.name, _TIME_PRIORITY))
    return [
        DiagnosisColumnRead(name=column.name, label=_label(column.name), data_type=column.type)
        for column in candidates
    ]


def _default_name(columns: list[DiagnosisColumnRead], priority: tuple[str, ...]) -> str | None:
    if not columns:
        return None
    by_name = {column.name.casefold(): column.name for column in columns}
    for name in priority:
        if name in by_name:
            return by_name[name]
    return columns[0].name


def _priority(name: str, priority: tuple[str, ...]) -> tuple[int, str]:
    folded = name.casefold()
    for index, candidate in enumerate(priority):
        if folded == candidate:
            return (index, folded)
    return (len(priority), folded)


def _order_column(context: _SourceContext, time_column: SchemaColumnRead) -> SchemaColumnRead | None:
    if time_column.name.casefold() != "month":
        return None
    return context.by_name.get("month_num")


def _is_numeric(column: SchemaColumnRead) -> bool:
    return column.type.upper() in _NUMERIC_TYPES


def _is_boolean(column: SchemaColumnRead) -> bool:
    return column.type.upper() in _BOOLEAN_TYPES


def _is_time_type(column: SchemaColumnRead) -> bool:
    return column.type.upper() in _TIME_TYPES


def _looks_like_time_name(name: str) -> bool:
    folded = name.casefold()
    return any(hint in folded for hint in _TIME_NAME_HINTS)


def _looks_like_identifier(name: str) -> bool:
    folded = name.casefold()
    return folded in {"id", "index", "row_id"} or folded.endswith(_IDENTIFIER_HINTS)


def _label(name: str) -> str:
    return _COLUMN_LABELS.get(name.casefold(), name.replace("_", " "))


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _share(delta: float, total_delta: float) -> float | None:
    if abs(total_delta) < 1e-9:
        return None
    return round(delta / total_delta * 100, 6)


def _normalize_period(raw: str) -> str:
    """把日期或带日的时间统一到月粒度，保证同一月份不会被拆成多个周期。"""

    text = raw.strip()
    match = re.match(r"^(\d{4})[-/.](\d{1,2})(?:[-/.]\d{1,2})?", text)
    if match:
        return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}"
    return text


def _period_order(raw: str, order_value: Any) -> tuple[int, float, str]:
    numeric = _to_float(order_value)
    if numeric is not None:
        return (0, numeric, raw)
    text = raw.strip()
    match = re.match(r"^(\d{4})[-/.](\d{1,2})", text)
    if match:
        return (1, int(match.group(1)) * 12 + int(match.group(2)), text)
    month = _MONTH_NAMES.get(text[:3].casefold())
    if month is not None and len(text) <= 9:
        return (2, float(month), text)
    return (3, 0.0, text)


def _period_label(raw: str, order_value: Any) -> str:
    text = raw.strip()
    match = re.match(r"^(\d{4})[-/.](\d{1,2})", text)
    if match:
        return f"{int(match.group(1))}年{int(match.group(2))}月"
    month = _MONTH_NAMES.get(text[:3].casefold())
    if month is not None and len(text) <= 9:
        return f"{month}月"
    numeric = _to_float(order_value)
    if numeric is not None and 1 <= numeric <= 12:
        return f"{int(numeric)}月"
    return text or "未知周期"


def _latest_calendar_date(periods: list[_Period]) -> date | None:
    latest: date | None = None
    for period in periods:
        match = re.match(r"^(\d{4})[-/.](\d{1,2})(?:[-/.](\d{1,2}))?", period.raw)
        if not match:
            continue
        try:
            candidate = date(
                int(match.group(1)),
                int(match.group(2)),
                int(match.group(3) or 1),
            )
        except ValueError:
            continue
        if latest is None or candidate > latest:
            latest = candidate
    return latest


def _robustness(stat: _GroupStat, periods: list[_Period]) -> tuple[int, int]:
    transitions: list[float] = []
    for index in range(1, len(periods)):
        previous = periods[index - 1].raw
        current = periods[index].raw
        previous_item = stat.series.get(previous)
        current_item = stat.series.get(current)
        if previous_item is None or current_item is None:
            continue
        if previous_item[1] == 0 or current_item[1] == 0:
            continue
        transitions.append(current_item[0] - previous_item[0])
    usable = transitions[-_MAX_ROBUSTNESS_PERIODS:]
    if not usable:
        return (0, 0)
    current_sign = 1 if stat.delta > 0 else -1 if stat.delta < 0 else 0
    consistent = sum(
        1
        for delta in usable
        if (1 if delta > 0 else -1 if delta < 0 else 0) == current_sign
    )
    return (len(usable), consistent)


def _build_evidence_and_hypotheses(
    *,
    selected: list[_GroupStat],
    periods: list[_Period],
    totals: dict[str, float],
    contributions: list[DiagnosisContributionRead],
    metric_label: str,
    confidence_level: float,
    dimension_missing_rate: float,
) -> tuple[list[DiagnosisEvidenceRead], list[DiagnosisHypothesisRead]]:
    evidence: list[DiagnosisEvidenceRead] = []
    hypotheses: list[DiagnosisHypothesisRead] = []
    for index, (stat, contribution) in enumerate(zip(selected, contributions, strict=True), start=1):
        robust_periods, robust_consistent = contribution.robust_periods, contribution.robust_consistent
        interval = _share_interval(stat, periods, totals)
        evidence_id = f"E{index}"
        evidence.append(
            DiagnosisEvidenceRead(
                id=evidence_id,
                group=stat.name,
                claim=(
                    f"{metric_label}在「{stat.name}」分组本期 {_fmt(stat.current_value)}、"
                    f"基期 {_fmt(stat.baseline_value)}，变化 {_fmt(stat.delta)}"
                ),
                value=round(stat.delta, 4),
                unit=metric_label + "变化额",
                method="additive_decomposition",
                sample_size=stat.current_rows + stat.baseline_rows,
                robust_periods=robust_periods,
                robust_consistent=robust_consistent,
                missing_rate=round(dimension_missing_rate, 6),
                confidence_level=confidence_level,
                interval=interval,
                caveats=["贡献分解只描述数量关系，不构成因果证明"],
                status="supported",
            )
        )
        supporting = [evidence_id]
        contradicting: list[str] = []
        if robust_periods >= 2 and robust_consistent < robust_periods:
            contradiction_id = f"E{index}c"
            evidence.append(
                DiagnosisEvidenceRead(
                    id=contradiction_id,
                    group=stat.name,
                    claim=(
                        f"「{stat.name}」的贡献方向在最近 {robust_periods} 个周期中"
                        f"只有 {robust_consistent} 次与本期一致"
                    ),
                    value=round(robust_consistent / robust_periods, 4),
                    unit="consistency",
                    method="temporal_stability",
                    sample_size=stat.current_rows + stat.baseline_rows,
                    robust_periods=robust_periods,
                    robust_consistent=robust_consistent,
                    missing_rate=round(dimension_missing_rate, 6),
                    confidence_level=confidence_level,
                    interval=None,
                    caveats=["稳定性检查只比较方向，不解释变化原因"],
                    status="contradicting",
                )
            )
            contradicting.append(contradiction_id)
        share = contribution.share_pct
        effect = min(1.0, abs(share) / 60.0) if share is not None else 0.0
        consistency = (
            robust_consistent / robust_periods if robust_periods > 0 else 0.5
        )
        quality = max(0.0, 1.0 - dimension_missing_rate)
        score = round(0.45 * effect + 0.3 * consistency + 0.25 * quality, 4)
        direction = "增加" if stat.delta > 0 else "减少" if stat.delta < 0 else "持平"
        status = "unknown" if share is None else "supporting"
        if index == 1 and share is not None and not contradicting:
            status = "leading"
        if contradicting and robust_consistent == 0:
            status = "contradicted"
        hypotheses.append(
            DiagnosisHypothesisRead(
                id=f"H{index}",
                text=(
                    f"「{stat.name}」的{metric_label}{direction} {_fmt(abs(stat.delta))}，"
                    f"对整体变化的贡献占比为 "
                    + (f"{share:.1f}%" if share is not None else "不可计算")
                ),
                operators=["decompose:" + stat.name, "compare:previous_period"],
                supporting=supporting,
                contradicting=contradicting,
                score=score,
                score_breakdown={
                    "effect": round(effect, 4),
                    "consistency": round(consistency, 4),
                    "quality": round(quality, 4),
                },
                status=status,
            )
        )
    hypotheses.sort(key=lambda item: item.score, reverse=True)
    return evidence, [
        item.model_copy(update={"id": f"H{index}"})
        for index, item in enumerate(hypotheses, start=1)
    ]


def _share_interval(
    stat: _GroupStat,
    periods: list[_Period],
    totals: dict[str, float],
) -> list[float] | None:
    history: list[float] = []
    for index in range(1, len(periods)):
        previous = periods[index - 1]
        current = periods[index]
        total_delta = totals[current.raw] - totals[previous.raw]
        if abs(total_delta) < 1e-9:
            continue
        previous_item = stat.series.get(previous.raw)
        current_item = stat.series.get(current.raw)
        if previous_item is None or current_item is None:
            continue
        history.append((current_item[0] - previous_item[0]) / total_delta * 100)
    usable = history[-_MAX_ROBUSTNESS_PERIODS:]
    if len(usable) < 2:
        return None
    return [round(min(usable), 4), round(max(usable), 4)]


def _verify(
    *,
    total_delta: float,
    contributions: list[DiagnosisContributionRead],
    others: DiagnosisContributionRead | None,
    current_rows: int,
    baseline_rows: int,
    dimension_missing_rate: float,
    confidence_level: float,
    period_count: int,
) -> DiagnosisVerificationRead:
    checks: list[DiagnosisVerificationCheckRead] = []
    tolerance = max(1e-6, abs(total_delta) * 1e-6)
    all_contributions = contributions + ([others] if others is not None else [])
    contribution_sum = sum(item.delta for item in all_contributions)
    difference = abs(contribution_sum - total_delta)
    checks.append(
        DiagnosisVerificationCheckRead(
            name="sum_contributions_equals_delta",
            label="分组贡献之和等于整体变化",
            passed=difference <= tolerance,
            detail=(
                f"分组贡献合计 {_fmt(contribution_sum)}，整体变化 {_fmt(total_delta)}，"
                f"偏差 {difference:.6f}"
            ),
            confidence_level=0.99,
        )
    )
    if abs(total_delta) > tolerance:
        share_sum = contribution_sum / total_delta * 100
        checks.append(
            DiagnosisVerificationCheckRead(
                name="shares_sum_to_one",
                label="贡献占比合计 100%",
                passed=abs(share_sum - 100) <= 1e-3,
                detail=f"贡献占比合计 {share_sum:.6f}%",
                confidence_level=0.99,
            )
        )
    checks.append(
        DiagnosisVerificationCheckRead(
            name="both_periods_have_rows",
            label="本期与基期均有样本",
            passed=current_rows > 0 and baseline_rows > 0,
            detail=f"本期 {current_rows} 行，基期 {baseline_rows} 行",
            confidence_level=0.95,
        )
    )
    checks.append(
        DiagnosisVerificationCheckRead(
            name="dimension_missing_within_limit",
            label="维度缺失率不超过 5%",
            passed=dimension_missing_rate <= _MISSING_RATE_LIMIT,
            detail=f"维度缺失率 {dimension_missing_rate * 100:.2f}%",
            confidence_level=0.9,
        )
    )
    passed = sum(1 for item in checks if item.passed)
    failed = [item for item in checks if not item.passed]
    caveats = ["贡献分解只描述数量关系，不构成因果证明"]
    if period_count == 2:
        caveats.append("仅有 2 个可比周期，无法估计跨周期稳定性区间")
    status = "invalid" if failed else "valid"
    if abs(total_delta) <= tolerance:
        status = "insufficient"
        caveats.append("本期与基期整体变化为 0，无法形成有效贡献结论")
    return DiagnosisVerificationRead(
        status=status,  # type: ignore[arg-type]
        passed=passed,
        total=len(checks),
        confidence_level=confidence_level,
        checks=checks,
        caveats=caveats,
    )


def _narrative(
    *,
    period: DiagnosisPeriodRead,
    contributions: list[DiagnosisContributionRead],
    others: DiagnosisContributionRead | None,
    hypotheses: list[DiagnosisHypothesisRead],
    verification: DiagnosisVerificationRead,
    quality: DiagnosisQualityRead,
    metric_label: str,
    dimension_label: str,
) -> str:
    direction = "上升" if period.delta > 0 else "下降" if period.delta < 0 else "持平"
    change = "持平" if period.delta == 0 else f"{direction} {_fmt(abs(period.delta))}"
    percent = f"（{period.delta_pct:+.2f}%）" if period.delta_pct is not None else ""
    lines = [
        "## 结论",
        f"{period.current_label}的{metric_label}合计 {_fmt(period.current_total)}，"
        f"较{period.baseline_label}的 {_fmt(period.baseline_total)} {change}{percent}。",
    ]
    lines += ["", "## 主要驱动"]
    if contributions:
        for item in contributions[:3]:
            share = f"，贡献占比 {item.share_pct:.1f}%" if item.share_pct is not None else ""
            lines.append(
                f"- {item.group}：本期 {_fmt(item.current_value)}，基期 "
                f"{_fmt(item.baseline_value)}，变化 {_fmt(item.delta)}{share}"
            )
        if others is not None:
            lines.append(f"- {others.group}：变化 {_fmt(others.delta)}")
    else:
        lines.append("- 当前没有可分解的分组变化。")
    lines += ["", "## 反证与不确定性"]
    lines.append(
        f"- 不变量验证：{verification.passed}/{verification.total} 项通过，"
        f"状态 {verification.status}。"
    )
    if hypotheses:
        leading = hypotheses[0]
        lines.append(
            f"- 排名第一的假设：{leading.text}（置信评分 {leading.score:.2f}）。"
        )
    for caveat in verification.caveats:
        lines.append(f"- {caveat}。")
    lines.append(
        f"- 数据质量：缺失率 {quality.missing_rate * 100:.2f}%，"
        f"新鲜度 {quality.freshness}。"
    )
    lines += [
        "",
        "## 下一步建议",
        f"- 优先下钻「{dimension_label}」中贡献最大的分组，核对口径与明细记录。",
        "- 结合更多周期复核方向稳定性，避免把数量贡献当作因果结论。",
    ]
    return "\n".join(lines)


def _fmt(value: float) -> str:
    if abs(value) >= 10000:
        return f"{value:,.0f}"
    if abs(value) >= 100:
        return f"{value:,.1f}"
    return f"{value:,.2f}"


__all__ = ["DiagnosisService"]
