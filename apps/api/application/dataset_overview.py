from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from contracts.datasources import (
    DatasetAlertRead,
    DatasetGroupItemRead,
    DatasetGroupRead,
    DatasetInsightRead,
    DatasetMetricRead,
    DatasetOverviewRead,
    DatasetQualityRead,
    DatasetTrendRead,
    DatasetTrendSeriesRead,
    SchemaColumnRead,
    SchemaSummaryRead,
)
from contracts.errors import AppError, ErrorCode
from contracts.status import DataSourceStatus
from data_gateway.types import QueryCancelToken

from application.datasources import DataSourceService

_TARGET_COLUMNS = (
    "purchased_flag",
    "subscribed_flag",
    "revenue_flag",
    "converted_flag",
    "purchase",
    "subscribed",
    "revenue",
    "converted",
)
_TARGET_IGNORED = {
    "weekend_flag",
    "weekend",
    "housing",
    "loan",
    "credit_default",
    "special_day",
}
_CATEGORY_COLUMNS = (
    "traffic_type",
    "job",
    "contact",
    "visitor_type",
    "region",
    "previous_outcome",
    "education",
    "marital",
    "browser",
    "operating_systems",
)
_NUMERIC_COLUMNS = (
    "balance",
    "page_values",
    "age",
    "duration",
    "product_related_duration",
    "campaign_contacts",
    "product_related",
    "bounce_rates",
    "exit_rates",
)
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
_TARGET_LABELS = {
    "purchased_flag": "购买转化率",
    "purchase": "购买转化率",
    "subscribed_flag": "营销认购率",
    "subscribed": "营销认购率",
    "revenue_flag": "购买转化率",
    "revenue": "购买转化率",
    "converted_flag": "转化率",
    "converted": "转化率",
    "conversion_flag": "转化率",
}
_CATEGORY_LABELS = {
    "traffic_type": "流量来源",
    "job": "职业",
    "contact": "联系方式",
    "visitor_type": "访客类型",
    "region": "区域",
    "previous_outcome": "上次活动结果",
    "education": "教育程度",
    "marital": "婚姻状态",
    "browser": "浏览器",
    "operating_systems": "操作系统",
    "housing": "住房贷款",
    "loan": "个人贷款",
}
_GROUP_VALUE_LABELS = {
    "job": {
        "admin.": "行政人员",
        "blue-collar": "蓝领",
        "management": "管理层",
        "technician": "技术人员",
        "services": "服务业",
        "retired": "退休",
        "self-employed": "自由职业",
        "entrepreneur": "创业者",
        "unemployed": "失业",
        "housemaid": "家政",
        "student": "学生",
        "unknown": "未知",
    },
    "visitor_type": {
        "Returning_Visitor": "回访访客",
        "New_Visitor": "新访客",
        "Other": "其他",
    },
    "marital": {
        "married": "已婚",
        "single": "单身",
        "divorced": "离异",
        "unknown": "未知",
    },
    "contact": {
        "cellular": "手机",
        "telephone": "电话",
        "unknown": "未知",
    },
    "previous_outcome": {
        "success": "上次成功",
        "failure": "上次失败",
        "nonexistent": "无记录",
        "unknown": "未知",
    },
    "education": {
        "basic.4y": "基础教育 4 年",
        "basic.6y": "基础教育 6 年",
        "basic.9y": "基础教育 9 年",
        "high.school": "高中",
        "professional.course": "职业课程",
        "university.degree": "大学学位",
        "illiterate": "未受教育",
        "unknown": "未知",
    },
}
_NUMERIC_LABELS = {
    "balance": ("平均账户余额", "currency"),
    "page_values": ("平均页面价值", "number"),
    "age": ("平均年龄", "age"),
    "duration": ("平均通话时长", "seconds"),
    "product_related_duration": ("平均产品页停留时长", "seconds"),
    "campaign_contacts": ("平均联系次数", "times"),
    "product_related": ("平均产品页浏览数", "pages"),
    "bounce_rates": ("平均跳出率", "rate"),
    "exit_rates": ("平均退出率", "rate"),
}
_NUMERIC_TYPES = (
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
)


@dataclass
class _MonthPoint:
    order: int
    label: str
    total: int
    positives: int | None


@dataclass
class _GroupPoint:
    name: str
    total: int
    positives: int | None


class OverviewCache:
    """进程内短 TTL 缓存，避免驾驶舱每次刷新都重复聚合同一份数据。"""

    def __init__(self) -> None:
        self._items: dict[str, tuple[float, DatasetOverviewRead]] = {}

    def get(self, key: str, ttl_seconds: float) -> DatasetOverviewRead | None:
        item = self._items.get(key)
        if item is None:
            return None
        stored_at, value = item
        if time.monotonic() - stored_at > ttl_seconds:
            self._items.pop(key, None)
            return None
        return value

    def put(self, key: str, value: DatasetOverviewRead) -> None:
        self._items[key] = (time.monotonic(), value)


class DatasetOverviewService:
    """用真实数据源聚合驾驶舱指标；只读 SQL 仍经过统一 Data Gateway 与审计。"""

    def __init__(
        self,
        datasources: DataSourceService,
        cache: OverviewCache,
        *,
        query_timeout_seconds: int = 30,
        cache_ttl_seconds: float = 120,
    ) -> None:
        self.datasources = datasources
        self.cache = cache
        self.query_timeout_seconds = query_timeout_seconds
        self.cache_ttl_seconds = cache_ttl_seconds

    async def get(self, datasource_id: str, *, refresh: bool = False) -> DatasetOverviewRead:
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
        cache_key = (
            f"{source.id}:{source.schema_revision}:{source.updated_at.isoformat()}:"
            f"{','.join(sorted(source.mask_fields))}"
        )
        if not refresh:
            cached = self.cache.get(cache_key, self.cache_ttl_seconds)
            if cached is not None:
                return cached

        table = next((item for item in schema.tables if item.name == "dataset"), None)
        if table is None:
            if not schema.tables:
                raise AppError(
                    ErrorCode.DATASOURCE_NOT_READY,
                    "数据源没有可分析的物理表",
                    status_code=409,
                )
            table = schema.tables[0]

        overview = await self._build(
            datasource_id=source.id,
            datasource_name=source.name,
            datasource_type=source.type,
            schema=schema,
            table_name=table.name,
            row_count=table.row_count or 0,
            masked={name.casefold() for name in source.mask_fields},
            schema_revision=source.schema_revision,
            updated_at=source.updated_at,
            column_hint=table.columns,
        )
        self.cache.put(cache_key, overview)
        return overview

    async def _build(
        self,
        *,
        datasource_id: str,
        datasource_name: str,
        datasource_type: str,
        schema: SchemaSummaryRead,
        table_name: str,
        row_count: int,
        masked: set[str],
        schema_revision: int,
        updated_at: datetime,
        column_hint: list[SchemaColumnRead],
    ) -> DatasetOverviewRead:
        dialect = schema.dialect
        columns = [column for column in column_hint if column.name.casefold() not in masked]
        target = _pick_target(columns)
        category = _pick_category(columns, target.name if target else None)
        numeric = _pick_numeric(columns, target.name if target else None)
        month_column = next(
            (column for column in columns if column.name.casefold() == "month"), None
        )
        month_num_column = next(
            (column for column in columns if column.name.casefold() == "month_num"), None
        )

        aggregate = await self._query(
            datasource_id,
            _aggregate_sql(
                dialect,
                table_name,
                columns,
                target=target,
                numeric=numeric,
            ),
            schema_revision,
        )
        total = int(_value(aggregate, "total", row_count))
        positives = _optional_int(_value(aggregate, "positives", None))
        conversion_pct = (
            round(positives / total * 100, 1) if positives is not None and total > 0 else None
        )
        numeric_avg = _value(aggregate, "numeric_avg", None)
        non_null_cells = int(_value(aggregate, "non_null_cells", 0))

        months: list[_MonthPoint] = []
        if month_column is not None and total > 0:
            months = await self._load_months(
                datasource_id,
                dialect,
                table_name,
                month_column,
                month_num_column,
                target,
                schema_revision,
            )
        groups: list[_GroupPoint] = []
        if category is not None and total > 0:
            groups = await self._load_groups(
                datasource_id,
                dialect,
                table_name,
                category,
                target,
                schema_revision,
            )

        quality = _quality(total, len(columns), non_null_cells, columns)
        period_label = _period_label(months, total)
        metric_values = _metrics(
            total=total,
            column_count=len(columns),
            target=target,
            target_label=_target_label(target) if target else None,
            conversion_pct=conversion_pct,
            positives=positives,
            months=months,
            numeric=numeric,
            numeric_avg=numeric_avg,
            non_null_pct=quality.non_null_pct,
        )
        trend = _trend(target, _target_label(target) if target else None, months)
        distribution = _distribution(category, groups, total)
        ranking = _ranking(category, groups, target)
        alerts, insights = _signals(
            total=total,
            column_count=len(columns),
            target=target,
            category=category,
            target_label=_target_label(target) if target else None,
            conversion_pct=conversion_pct,
            groups=groups,
            months=months,
            months_span_years=_months_span_years(target),
            quality=quality,
        )
        prompts = _prompts(
            target_label=_target_label(target) if target else None,
            category=category,
            months=months,
            numeric=numeric,
        )
        briefing = _briefing(
            datasource_name=datasource_name,
            total=total,
            column_count=len(columns),
            period_label=period_label,
            target_label=_target_label(target) if target else None,
            conversion_pct=conversion_pct,
            groups=groups,
            category=category,
        )
        return DatasetOverviewRead(
            datasource_id=datasource_id,
            datasource_name=datasource_name,
            datasource_type=datasource_type,
            table=table_name,
            row_count=total,
            column_count=len(columns),
            schema_revision=schema_revision,
            target_column=target.name if target else None,
            target_label=_target_label(target) if target else None,
            conversion_pct=conversion_pct,
            period_label=period_label,
            updated_at=updated_at,
            metrics=metric_values,
            trend=trend,
            distribution=distribution,
            ranking=ranking,
            alerts=alerts,
            insights=insights,
            quality=quality,
            prompts=prompts,
            briefing=briefing,
        )

    async def _query(
        self,
        datasource_id: str,
        sql: str,
        schema_revision: int,
    ) -> dict[str, Any]:
        result = await self.datasources.run_readonly_sql(
            datasource_id=datasource_id,
            sql=sql,
            cancel_token=QueryCancelToken(),
            timeout_seconds=self.query_timeout_seconds,
            expected_schema_revision=schema_revision,
        )
        if not result.rows:
            return {}
        return dict(zip(result.columns, result.rows[0], strict=True))

    async def _load_months(
        self,
        datasource_id: str,
        dialect: str,
        table_name: str,
        month_column: SchemaColumnRead,
        month_num_column: SchemaColumnRead | None,
        target: SchemaColumnRead | None,
        schema_revision: int,
    ) -> list[_MonthPoint]:
        order_column = month_num_column or month_column
        expressions = [
            f"{_quote(order_column.name, dialect)} AS month_order",
            f"{_quote(month_column.name, dialect)} AS month_label",
            "COUNT(*) AS total",
        ]
        if target is not None:
            expressions.append(f"{_target_sum(target, dialect)} AS positives")
        group_by = "GROUP BY 1, 2" if month_num_column is not None else "GROUP BY 1"
        sql = (
            f"SELECT {', '.join(expressions)} FROM {_quote(table_name, dialect)} "
            f"{group_by} ORDER BY 1"
        )
        result = await self.datasources.run_readonly_sql(
            datasource_id=datasource_id,
            sql=sql,
            cancel_token=QueryCancelToken(),
            timeout_seconds=self.query_timeout_seconds,
            expected_schema_revision=schema_revision,
        )
        points: list[_MonthPoint] = []
        for row in result.rows:
            values = dict(zip(result.columns, row, strict=True))
            raw_order = values.get("month_order")
            raw_label = values.get("month_label")
            order = _month_order(raw_order, raw_label)
            points.append(
                _MonthPoint(
                    order=order,
                    label=_month_label(raw_label, order),
                    total=int(_value(values, "total", 0)),
                    positives=_optional_int(_value(values, "positives", None)),
                )
            )
        return sorted(points, key=lambda item: item.order)

    async def _load_groups(
        self,
        datasource_id: str,
        dialect: str,
        table_name: str,
        category: SchemaColumnRead,
        target: SchemaColumnRead | None,
        schema_revision: int,
    ) -> list[_GroupPoint]:
        expressions = [
            f"CAST({_quote(category.name, dialect)} AS VARCHAR) AS group_name",
            "COUNT(*) AS total",
        ]
        if target is not None:
            expressions.append(f"{_target_sum(target, dialect)} AS positives")
        sql = (
            f"SELECT {', '.join(expressions)} FROM {_quote(table_name, dialect)} "
            "GROUP BY 1 ORDER BY 2 DESC LIMIT 20"
        )
        result = await self.datasources.run_readonly_sql(
            datasource_id=datasource_id,
            sql=sql,
            cancel_token=QueryCancelToken(),
            timeout_seconds=self.query_timeout_seconds,
            expected_schema_revision=schema_revision,
        )
        items: list[_GroupPoint] = []
        for row in result.rows:
            values = dict(zip(result.columns, row, strict=True))
            items.append(
                _GroupPoint(
                    name=str(values.get("group_name") or "未知"),
                    total=int(_value(values, "total", 0)),
                    positives=_optional_int(_value(values, "positives", None)),
                )
            )
        return items


def _quote(name: str, dialect: str) -> str:
    if dialect == "mysql":
        escaped = name.replace("`", "``")
        return f"`{escaped}`"
    escaped = name.replace('"', '""')
    return f'"{escaped}"'


def _pick_target(columns: list[SchemaColumnRead]) -> SchemaColumnRead | None:
    by_name = {column.name.casefold(): column for column in columns}
    for name in _TARGET_COLUMNS:
        if name in by_name:
            return by_name[name]
    for column in columns:
        name = column.name.casefold()
        if name in _TARGET_IGNORED:
            continue
        if name.endswith("_flag") or _is_boolean(column):
            return column
    return None


def _pick_category(
    columns: list[SchemaColumnRead], target_name: str | None
) -> SchemaColumnRead | None:
    selectable = [
        column
        for column in columns
        if column.name.casefold() not in {"month", "month_num"}
        and column.name.casefold() != (target_name or "").casefold()
    ]
    by_name = {column.name.casefold(): column for column in selectable}
    for name in _CATEGORY_COLUMNS:
        if name in by_name:
            return by_name[name]
    return next((column for column in selectable if _is_categorical(column)), None)


def _pick_numeric(
    columns: list[SchemaColumnRead], target_name: str | None
) -> SchemaColumnRead | None:
    selectable = [
        column
        for column in columns
        if column.name.casefold() not in {"month_num", "day", "month"}
        and column.name.casefold() != (target_name or "").casefold()
        and not column.name.casefold().endswith("_flag")
        and not _is_boolean(column)
    ]
    by_name = {column.name.casefold(): column for column in selectable}
    for name in _NUMERIC_COLUMNS:
        if name in by_name:
            return by_name[name]
    return next(
        (
            column
            for column in selectable
            if _is_numeric(column) and not _looks_like_identifier(column.name)
        ),
        None,
    )


def _aggregate_sql(
    dialect: str,
    table_name: str,
    columns: list[SchemaColumnRead],
    *,
    target: SchemaColumnRead | None,
    numeric: SchemaColumnRead | None,
) -> str:
    expressions = ["COUNT(*) AS total"]
    if target is not None:
        expressions.append(f"{_target_sum(target, dialect)} AS positives")
        expressions.append(f"COUNT({_quote(target.name, dialect)}) AS target_non_null")
    if numeric is not None:
        expressions.append(
            f"AVG(CAST({_quote(numeric.name, dialect)} AS DOUBLE)) AS numeric_avg"
        )
    non_null = " + ".join(f"COUNT({_quote(column.name, dialect)})" for column in columns)
    expressions.append(f"{non_null or 'COUNT(*)'} AS non_null_cells")
    return f"SELECT {', '.join(expressions)} FROM {_quote(table_name, dialect)}"


def _target_sum(column: SchemaColumnRead, dialect: str) -> str:
    reference = _quote(column.name, dialect)
    if _is_boolean(column):
        return f"SUM(CASE WHEN {reference} THEN 1 ELSE 0 END)"
    return f"SUM(CASE WHEN {reference} = 1 THEN 1 ELSE 0 END)"


def _value(source: dict[str, Any], key: str, fallback: Any) -> Any:
    value = source.get(key)
    return fallback if value is None else value


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_boolean(column: SchemaColumnRead) -> bool:
    return "BOOL" in column.type.upper()


def _is_numeric(column: SchemaColumnRead) -> bool:
    upper = column.type.upper()
    return any(token in upper for token in _NUMERIC_TYPES)


def _is_categorical(column: SchemaColumnRead) -> bool:
    return not _is_numeric(column) and not _is_boolean(column)


def _looks_like_identifier(name: str) -> bool:
    folded = name.casefold()
    return folded.endswith("_id") or folded in {"id", "index", "row_id"}


def _month_order(raw_order: Any, raw_label: Any) -> int:
    try:
        value = int(raw_order)
        if 1 <= value <= 12:
            return value
    except (TypeError, ValueError):
        pass
    return _MONTH_NAMES.get(str(raw_label).strip().casefold(), 99)


def _month_label(raw_label: Any, order: int) -> str:
    if 1 <= order <= 12:
        return f"{order}月"
    text = str(raw_label or "").strip()
    return text or "未知月份"


def _target_label(column: SchemaColumnRead) -> str:
    folded = column.name.casefold()
    if folded in _TARGET_LABELS:
        return _TARGET_LABELS[folded]
    base = folded[:-5] if folded.endswith("_flag") else folded
    return f"{base}占比"


def _category_label(column: SchemaColumnRead) -> str:
    return _CATEGORY_LABELS.get(column.name.casefold(), column.name)


def _group_value_label(column: SchemaColumnRead, raw: str) -> str:
    folded = column.name.casefold()
    if raw == "其他":
        return raw
    mapped = _GROUP_VALUE_LABELS.get(folded, {}).get(raw)
    if mapped:
        return mapped
    if _is_numeric(column) and not _looks_like_identifier(folded):
        short = {
            "traffic_type": "流量类型",
            "region": "区域",
            "browser": "浏览器",
            "operating_systems": "操作系统",
        }.get(folded, _category_label(column))
        return f"{short} {raw}"
    return raw or "未知"


def _quality(
    total: int,
    column_count: int,
    non_null_cells: int,
    columns: list[SchemaColumnRead],
) -> DatasetQualityRead:
    cells = total * column_count
    missing = max(0, cells - non_null_cells)
    non_null_pct = round((non_null_cells / cells * 100) if cells else 0, 1)
    return DatasetQualityRead(
        non_null_pct=non_null_pct,
        missing_cells=missing,
        numeric_columns=sum(1 for column in columns if _is_numeric(column)),
        categorical_columns=sum(1 for column in columns if _is_categorical(column)),
        boolean_columns=sum(1 for column in columns if _is_boolean(column)),
    )


def _period_label(months: list[_MonthPoint], total: int) -> str:
    if not months:
        return f"全量数据 · {total:,} 条记录"
    first = months[0].label
    last = months[-1].label
    if first == last:
        return f"{first} · 覆盖 1 个月"
    return f"{first}—{last} · 覆盖 {len(months)} 个月"


def _metrics(
    *,
    total: int,
    column_count: int,
    target: SchemaColumnRead | None,
    target_label: str | None,
    conversion_pct: float | None,
    positives: int | None,
    months: list[_MonthPoint],
    numeric: SchemaColumnRead | None,
    numeric_avg: Any,
    non_null_pct: float,
) -> list[DatasetMetricRead]:
    record_spark = [float(point.total) for point in months]
    rate_spark = [
        round(point.positives / point.total * 100, 2)
        for point in months
        if point.positives is not None and point.total > 0
    ]
    metrics = [
        DatasetMetricRead(
            key="rows",
            label="总记录数",
            value=f"{total:,}",
            detail=f"{column_count} 个字段 · 全量扫描",
            tone="cyan",
            spark=record_spark,
        )
    ]
    if target is not None and conversion_pct is not None:
        metrics.append(
            DatasetMetricRead(
                key="conversion",
                label=target_label or "转化率",
                value=f"{conversion_pct:.1f}%",
                detail=f"{positives or 0:,} / {total:,} 条记录",
                tone="violet",
                spark=rate_spark,
            )
        )
    else:
        metrics.append(
            DatasetMetricRead(
                key="columns",
                label="字段总数",
                value=f"{column_count}",
                detail="未识别到可计算的目标结果列",
                tone="violet",
            )
        )
    if months:
        metrics.append(
            DatasetMetricRead(
                key="months",
                label="覆盖月份",
                value=f"{len(months)} 个",
                detail=f"{months[0].label}—{months[-1].label}",
                tone="blue",
                spark=record_spark,
            )
        )
    else:
        metrics.append(
            DatasetMetricRead(
                key="groups",
                label="数据范围",
                value="全量",
                detail="当前数据不含月份字段",
                tone="blue",
            )
        )
    if numeric is not None and numeric_avg is not None:
        label, unit = _NUMERIC_LABELS.get(
            numeric.name.casefold(), (f"平均{numeric.name}", "number")
        )
        metrics.append(
            DatasetMetricRead(
                key="numeric",
                label=label,
                value=_format_numeric_metric(float(numeric_avg), unit),
                detail=f"字段均值 · {numeric.name}",
                tone="green",
            )
        )
    else:
        metrics.append(
            DatasetMetricRead(
                key="quality",
                label="字段完整度",
                value=f"{non_null_pct:.1f}%",
                detail="非空单元格占比",
                tone="green",
            )
        )
    return metrics


def _format_numeric_metric(value: float, unit: str) -> str:
    if unit == "currency":
        return f"€{value:,.0f}"
    if unit == "age":
        return f"{value:.0f} 岁"
    if unit == "seconds":
        return f"{value:,.0f} 秒"
    if unit == "times":
        return f"{value:,.1f} 次"
    if unit == "pages":
        return f"{value:,.1f} 页"
    if unit == "rate":
        return f"{value * 100:.1f}%"
    return f"{value:,.1f}"


def _trend(
    target: SchemaColumnRead | None,
    target_label: str | None,
    months: list[_MonthPoint],
) -> DatasetTrendRead | None:
    if not months:
        return None
    labels = [point.label for point in months]
    series = [
        DatasetTrendSeriesRead(
            name="记录数",
            kind="bar",
            axis="count",
            values=[float(point.total) for point in months],
        )
    ]
    if target is not None:
        series.append(
            DatasetTrendSeriesRead(
                name=target_label or "转化率",
                kind="line",
                axis="rate",
                values=[
                    round((point.positives or 0) / point.total * 100, 2)
                    if point.total > 0
                    else 0.0
                    for point in months
                ],
            )
        )
    return DatasetTrendRead(
        title="月度记录与转化趋势" if target is not None else "月度记录趋势",
        subtitle="按数据中的月份字段聚合",
        labels=labels,
        series=series,
    )


def _compose_groups(
    column: SchemaColumnRead,
    points: list[_GroupPoint],
    total: int,
) -> list[DatasetGroupItemRead]:
    items: list[DatasetGroupItemRead] = []
    for point in points:
        items.append(
            DatasetGroupItemRead(
                name=_group_value_label(column, point.name),
                count=point.total,
                positives=point.positives,
                share_pct=round(point.total / total * 100, 1) if total else 0,
                conversion_pct=(
                    round(point.positives / point.total * 100, 1)
                    if point.positives is not None and point.total > 0
                    else None
                ),
            )
        )
    return items


def _distribution(
    category: SchemaColumnRead | None,
    points: list[_GroupPoint],
    total: int,
) -> DatasetGroupRead | None:
    if category is None or not points:
        return None
    # 保留前四类并合并其余，保证环图扇区仍覆盖全量记录。
    visible = points[:4]
    rest = points[4:]
    if rest:
        others_positive = (
            sum(point.positives or 0 for point in rest)
            if all(point.positives is not None for point in rest)
            else None
        )
        visible = [
            *visible,
            _GroupPoint(
                name="其他",
                total=sum(point.total for point in rest),
                positives=others_positive,
            ),
        ]
    return DatasetGroupRead(
        title=f"{_category_label(category)}结构",
        column=category.name,
        label=_category_label(category),
        metric_label="记录占比",
        items=_compose_groups(category, visible, total),
    )


def _ranking(
    category: SchemaColumnRead | None,
    points: list[_GroupPoint],
    target: SchemaColumnRead | None,
) -> DatasetGroupRead | None:
    if category is None or not points:
        return None
    total = sum(point.total for point in points)
    if target is None:
        items = _compose_groups(category, points, total)[:5]
        return DatasetGroupRead(
            title=f"记录量 TOP 5 · {_category_label(category)}",
            column=category.name,
            label=_category_label(category),
            metric_label="记录占比",
            items=items,
        )
    min_count = max(100, round(total * 0.005))
    eligible = [
        point
        for point in points
        if point.total >= min_count and point.positives is not None
    ]
    if not eligible:
        eligible = [point for point in points if point.positives is not None]
    ranked = sorted(
        eligible,
        key=lambda point: (point.positives or 0) / point.total if point.total else 0,
        reverse=True,
    )[:5]
    items = _compose_groups(category, ranked, total)
    return DatasetGroupRead(
        title=f"{_category_label(category)}{_target_label(target)} TOP 5",
        column=category.name,
        label=_category_label(category),
        metric_label="转化率",
        items=items,
    )


def _signals(
    *,
    total: int,
    column_count: int,
    target: SchemaColumnRead | None,
    category: SchemaColumnRead | None,
    target_label: str | None,
    conversion_pct: float | None,
    groups: list[_GroupPoint],
    months: list[_MonthPoint],
    months_span_years: bool,
    quality: DatasetQualityRead,
) -> tuple[list[DatasetAlertRead], list[DatasetInsightRead]]:
    alerts: list[DatasetAlertRead] = []
    insights: list[DatasetInsightRead] = []
    label = target_label or "目标结果"

    def display(name: str) -> str:
        return _group_value_label(category, name) if category is not None else name

    if target is not None and conversion_pct is not None and groups:
        min_count = max(100, round(total * 0.01))
        measurable = [
            point for point in groups if point.total >= min_count and point.positives is not None
        ]
        if measurable:
            low = min(
                measurable,
                key=lambda point: (point.positives or 0) / point.total if point.total else 1,
            )
            low_rate = (low.positives or 0) / low.total * 100 if low.total else 0
            high = max(
                measurable,
                key=lambda point: (point.positives or 0) / point.total if point.total else 0,
            )
            high_rate = (high.positives or 0) / high.total * 100 if high.total else 0
            insights.append(
                DatasetInsightRead(
                    kind="positive",
                    label="最高转化",
                    title=f"「{display(high.name)}」{label}最高",
                    detail=f"{high_rate:.1f}%，{high.positives or 0}/{high.total:,} 条记录。",
                )
            )
            alerts.append(
                DatasetAlertRead(
                    level="warning",
                    title=f"「{display(low.name)}」{label}偏低",
                    detail=(
                        f"仅 {low_rate:.1f}%，低于整体 {conversion_pct:.1f}%"
                        f"（{low.total:,} 条记录）。"
                    ),
                )
            )
            if conversion_pct - low_rate >= 3:
                insights.append(
                    DatasetInsightRead(
                        kind="warning",
                        label="待改进",
                        title=f"最低分组低于整体 {conversion_pct - low_rate:.1f} 个百分点",
                        detail=(
                            f"「{display(low.name)}」{low_rate:.1f}%，"
                            f"整体 {conversion_pct:.1f}%。"
                        ),
                    )
                )
        else:
            insights.append(
                DatasetInsightRead(
                    kind="positive",
                    label="整体转化",
                    title=f"{label} {conversion_pct:.1f}%",
                    detail=f"{total:,} 条记录中完成目标结果的比例。",
                )
            )

    if months:
        month_rates = [
            (
                point.label,
                (point.positives or 0) / point.total * 100 if point.total else 0,
                point.total,
            )
            for point in months
            if point.positives is not None and point.total > 0
        ]
        if target is not None and month_rates:
            best = max(month_rates, key=lambda item: item[1])
            worst = min(month_rates, key=lambda item: item[1])
            gap = best[1] - worst[1]
            note = (
                "原始数据不含年份，月度对比仅反映月份汇总。"
                if months_span_years
                else ""
            )
            detail = f"{best[0]} 与 {worst[0]} 相差 {gap:.1f} 个百分点"
            if note:
                detail += f"；{note}"
            alerts.append(
                DatasetAlertRead(
                    level="warning" if gap >= 10 else "info",
                    title=f"月度{label}最高为 {best[0]}（{best[1]:.1f}%）",
                    detail=detail,
                )
            )
            insights.append(
                DatasetInsightRead(
                    kind="neutral",
                    label="月度峰值",
                    title=f"{best[0]}达到 {best[1]:.1f}%",
                    detail=f"当月 {best[2]:,} 条记录，为当前数据中的最高月份。",
                )
            )
        elif target is None:
            ranked = sorted(months, key=lambda point: point.total, reverse=True)
            best = ranked[0]
            worst = ranked[-1]
            alerts.append(
                DatasetAlertRead(
                    level="info",
                    title=f"{best.label}记录量最高",
                    detail=f"{best.total:,} 条；最低为 {worst.label} 的 {worst.total:,} 条。",
                )
            )
            insights.append(
                DatasetInsightRead(
                    kind="neutral",
                    label="月度峰值",
                    title=f"{best.label}记录量最高",
                    detail=f"{best.total:,} 条记录，占全量的 {best.total / total * 100:.1f}%。",
                )
            )

    if quality.missing_cells > 0:
        alerts.append(
            DatasetAlertRead(
                level="warning",
                title=f"存在 {quality.missing_cells:,} 个缺失单元格",
                detail=f"字段完整度 {quality.non_null_pct:.1f}%，建议在分析前补齐。",
            )
        )
    insights.append(
        DatasetInsightRead(
            kind="neutral",
            label="数据规模",
            title=f"{total:,} 条记录 · {column_count} 个字段",
            detail=f"字段完整度 {quality.non_null_pct:.1f}%，全部指标均由当前数据源即时聚合。",
        )
    )
    return alerts[:3], insights[:3]


def _months_span_years(target: SchemaColumnRead | None) -> bool:
    """银行营销数据的月份是跨年活动汇总，缺少年份字段时必须显式提示。"""

    return target is not None and target.name.casefold() in {"subscribed_flag", "subscribed"}


def _prompts(
    *,
    target_label: str | None,
    category: SchemaColumnRead | None,
    months: list[_MonthPoint],
    numeric: SchemaColumnRead | None,
) -> list[str]:
    prompts: list[str] = []
    if target_label and category is not None:
        category_label = _category_label(category)
        if len(months) >= 2:
            heaviest = sorted(months, key=lambda point: point.total, reverse=True)[:2]
            heaviest = sorted(heaviest, key=lambda point: point.order)
            prompts.append(
                f"对比 {heaviest[0].label}和{heaviest[1].label}的{target_label}表现"
            )
        prompts.append(f"哪些{category_label}的{target_label}最高？")
        if numeric is not None:
            numeric_label = _NUMERIC_LABELS.get(
                numeric.name.casefold(), (numeric.name, "number")
            )[0]
            prompts.append(f"{numeric_label}与{target_label}有什么关系？")
    else:
        if months:
            prompts.append("各月份的记录量如何变化？")
        if category is not None:
            prompts.append(f"哪些{_category_label(category)}的记录最多？")
        prompts.append("这份数据的完整度如何？")
    return prompts[:3]


def _briefing(
    *,
    datasource_name: str,
    total: int,
    column_count: int,
    period_label: str,
    target_label: str | None,
    conversion_pct: float | None,
    groups: list[_GroupPoint],
    category: SchemaColumnRead | None,
) -> str:
    prefix = (
        f"已对「{datasource_name}」完成真实聚合：{total:,} 条记录、{column_count} 个字段，"
        f"{period_label}。"
    )
    if target_label is None or conversion_pct is None:
        return prefix
    text = prefix + f"整体{target_label} {conversion_pct:.1f}%"
    measurable = [point for point in groups if point.total > 0 and point.positives is not None]
    if measurable:
        high = max(measurable, key=lambda point: (point.positives or 0) / point.total)
        low = min(measurable, key=lambda point: (point.positives or 0) / point.total)
        high_rate = (high.positives or 0) / high.total * 100
        low_rate = (low.positives or 0) / low.total * 100
        high_name = _group_value_label(category, high.name) if category else high.name
        low_name = _group_value_label(category, low.name) if category else low.name
        text += f"；「{high_name}」最高（{high_rate:.1f}%），「{low_name}」最低（{low_rate:.1f}%）"
    return text + "。"
