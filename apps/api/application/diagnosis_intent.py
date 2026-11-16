"""经营诊断的自然语言入口：模型优先解析意图，规则兜底。

解析只负责选择已有的指标、分组和时间字段，不做任何计算；
最终结果仍由确定性诊断引擎计算，保证可复现与可复核。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Literal

from application.datasources import DataSourceService
from application.diagnosis_service import DiagnosisService
from application.secret_cipher import SecretCipher
from contracts.diagnosis import (
    DiagnosisCapabilitiesRead,
    DiagnosisColumnRead,
    DiagnosisIntentRead,
)
from metadata.repositories import ModelProfileRepository, SecretRepository
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

_MEASURE_SYNONYMS: dict[str, tuple[str, ...]] = {
    "营收": ("revenue", "amount", "sales", "gmv", "turnover", "income"),
    "收入": ("revenue", "income"),
    "销售额": ("revenue", "sales", "amount"),
    "流水": ("revenue", "amount", "gmv"),
    "金额": ("revenue", "amount"),
    "订单数": ("order_count",),
    "单量": ("order_count",),
    "余额": ("balance",),
    "年龄": ("age",),
    "时长": ("duration", "product_related_duration"),
    "转化": ("subscribed_flag", "purchased_flag", "converted_flag"),
    "认购": ("subscribed_flag",),
    "购买": ("purchased_flag",),
}
_DIMENSION_SYNONYMS: dict[str, tuple[str, ...]] = {
    "区域": ("region", "area"),
    "地区": ("region", "area"),
    "大区": ("region", "area"),
    "渠道": ("channel",),
    "品类": ("category",),
    "类别": ("category", "type"),
    "客群": ("segment", "visitor_type"),
    "人群": ("segment", "visitor_type"),
    "职业": ("job",),
    "学历": ("education",),
    "教育": ("education",),
    "流量": ("traffic_type",),
    "访客": ("visitor_type",),
    "浏览器": ("browser",),
    "系统": ("operating_systems",),
}
_TIME_SYNONYMS: dict[str, tuple[str, ...]] = {
    "月份": ("month",),
    "按月": ("month",),
    "月": ("month",),
    "日期": ("order_date", "date"),
    "时间": ("order_date", "date", "timestamp", "time"),
}
_RELEVANCE_KEYWORDS = (
    "为什么",
    "为何",
    "原因",
    "下降",
    "上升",
    "增长",
    "下滑",
    "变化",
    "贡献",
    "拉动",
    "拖累",
    "影响",
    "诊断",
    "经营",
    "指标",
    "数据",
    "表现",
    "趋势",
    "对比",
)


class DiagnosisIntentService:
    """把中文问题解析成当前数据源可执行的诊断意图。"""

    def __init__(
        self,
        datasources: DataSourceService,
        models: ModelProfileRepository,
        secrets: SecretRepository,
        cipher: SecretCipher,
        *,
        enterprise_id: str | None,
        timeout_seconds: float = 6.0,
    ) -> None:
        self.diagnosis = DiagnosisService(datasources)
        self.models = models
        self.secrets = secrets
        self.cipher = cipher
        self.enterprise_id = enterprise_id
        self.timeout_seconds = timeout_seconds

    async def parse(self, datasource_id: str, question: str) -> DiagnosisIntentRead:
        capabilities = await self.diagnosis.capabilities(datasource_id)
        if not capabilities.ready:
            return DiagnosisIntentRead(
                question=question,
                understood=False,
                source="rules",
                confidence=0.0,
                explanation=capabilities.message,
                clarification=capabilities.message,
            )
        rule_intent = _rule_intent(capabilities, question)
        model_intent = await self._model_intent(capabilities, question, rule_intent)
        return model_intent or rule_intent

    async def _model_intent(
        self,
        capabilities: DiagnosisCapabilitiesRead,
        question: str,
        fallback: DiagnosisIntentRead,
    ) -> DiagnosisIntentRead | None:
        try:
            model = await self.models.get_active(self.enterprise_id)
            if model is None or model.secret_ref is None:
                return None
            secret = await self.secrets.get(model.secret_ref)
            if secret is None:
                return None
            api_key = self.cipher.decrypt(secret.encrypted_value)
            if not api_key.strip():
                return None
            payload = await asyncio.wait_for(
                _request_intent(
                    api_key=api_key,
                    base_url=model.base_url,
                    model_name=model.model_name,
                    capabilities=capabilities,
                    question=question,
                ),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.info("diagnosis intent model timed out, falling back to rules")
            return None
        except Exception as error:  # noqa: BLE001 - 意图解析失败必须回退，不阻塞诊断
            logger.warning("diagnosis intent model failed: %s", type(error).__name__)
            return None
        return _intent_from_payload(capabilities, question, payload, fallback)


async def _request_intent(
    *,
    api_key: str,
    base_url: str,
    model_name: str,
    capabilities: DiagnosisCapabilitiesRead,
    question: str,
) -> dict[str, Any]:
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=6.0,
        max_retries=0,
    )
    metric_lines = "\n".join(
        f"- {item.name}: {item.label}" for item in capabilities.measures
    )
    dimension_lines = "\n".join(
        f"- {item.name}: {item.label}" for item in capabilities.dimensions
    )
    time_lines = "\n".join(
        f"- {item.name}: {item.label}" for item in capabilities.time_columns
    )
    prompt = (
        "你是智析 ChatBI 经营诊断的意图解析器。你只负责从给定字段中选择，不做计算。\n"
        f"可用指标：\n{metric_lines}\n"
        f"可用分组：\n{dimension_lines}\n"
        f"可用时间字段：\n{time_lines}\n\n"
        f"用户问题：{question}\n\n"
        "只输出 JSON，格式："
        '{"metric":"字段名","dimension":"字段名","time_column":"字段名","confidence":0.0}\n'
        "要求：1）只能使用上面列出的字段名；2）问题没提到时选择最合适的一项；"
        "3）问题与经营分析无关时 confidence 设为 0。"
    )
    response = await client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=300,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content or ""
    return _load_json(content)


def _load_json(content: str) -> dict[str, Any]:
    text = content.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _intent_from_payload(
    capabilities: DiagnosisCapabilitiesRead,
    question: str,
    payload: dict[str, Any],
    fallback: DiagnosisIntentRead,
) -> DiagnosisIntentRead | None:
    confidence = payload.get("confidence")
    if not isinstance(confidence, (int, float)) or float(confidence) < 0.35:
        return None
    metric = _resolve(payload.get("metric"), capabilities.measures) or _resolve(
        fallback.metric, capabilities.measures
    )
    dimension = _resolve(payload.get("dimension"), capabilities.dimensions) or _resolve(
        fallback.dimension, capabilities.dimensions
    )
    time_column = _resolve(
        payload.get("time_column"), capabilities.time_columns
    ) or _resolve(fallback.time_column, capabilities.time_columns)
    if metric is None and dimension is None and time_column is None:
        return None
    metric = metric or _default_column(capabilities.measures, capabilities.default_measure)
    dimension = dimension or _default_column(capabilities.dimensions, capabilities.default_dimension)
    time_column = time_column or _default_column(
        capabilities.time_columns, capabilities.default_time_column
    )
    if metric is None or dimension is None or time_column is None:
        return None
    return _build_intent(
        question,
        metric,
        dimension,
        time_column,
        confidence=max(0.5, min(1.0, float(confidence))),
        source="model",
        used_defaults=[],
    )


def _rule_intent(
    capabilities: DiagnosisCapabilitiesRead, question: str
) -> DiagnosisIntentRead:
    metric = _match(question, capabilities.measures, _MEASURE_SYNONYMS)
    dimension = _match(question, capabilities.dimensions, _DIMENSION_SYNONYMS)
    time_column = _match(question, capabilities.time_columns, _TIME_SYNONYMS)
    if metric is None and dimension is None and not _looks_relevant(question):
        return DiagnosisIntentRead(
            question=question,
            understood=False,
            source="rules",
            confidence=0.0,
            explanation="没有识别出经营分析问题。",
            clarification="请描述想诊断的指标或分组，例如：本月营收为什么下降？按区域看看。",
        )
    explicit_time = time_column is not None
    used_defaults: list[str] = []
    if metric is None:
        metric = _default_column(capabilities.measures, capabilities.default_measure)
        used_defaults.append("指标")
    if dimension is None:
        dimension = _default_column(capabilities.dimensions, capabilities.default_dimension)
        used_defaults.append("分组")
    if time_column is None:
        time_column = _default_column(
            capabilities.time_columns, capabilities.default_time_column
        )
    if metric is None or dimension is None or time_column is None:
        return DiagnosisIntentRead(
            question=question,
            understood=False,
            source="rules",
            confidence=0.0,
            explanation="当前数据源缺少可诊断字段。",
            clarification=capabilities.message,
        )
    confidence = 0.6
    if "指标" not in used_defaults:
        confidence += 0.2
    if "分组" not in used_defaults:
        confidence += 0.15
    if explicit_time:
        confidence += 0.05
    return _build_intent(
        question,
        metric,
        dimension,
        time_column,
        confidence=min(0.95, confidence),
        source="rules",
        used_defaults=used_defaults,
    )


def _build_intent(
    question: str,
    metric: DiagnosisColumnRead,
    dimension: DiagnosisColumnRead,
    time_column: DiagnosisColumnRead,
    *,
    confidence: float,
    source: Literal["model", "rules"],
    used_defaults: list[str],
) -> DiagnosisIntentRead:
    explanation = f"识别为：{metric.label} · 按{dimension.label} · 最近两个可比月份"
    if used_defaults:
        explanation += f"（未提及{'、'.join(used_defaults)}，已使用默认项）"
    return DiagnosisIntentRead(
        question=question,
        understood=True,
        source=source,
        metric=metric.name,
        metric_label=metric.label,
        dimension=dimension.name,
        dimension_label=dimension.label,
        time_column=time_column.name,
        time_label=time_column.label,
        confidence=round(confidence, 2),
        explanation=explanation,
    )


def _looks_relevant(question: str) -> bool:
    return any(token in question for token in _RELEVANCE_KEYWORDS)


def _match(
    question: str,
    columns: list[DiagnosisColumnRead],
    synonyms: dict[str, tuple[str, ...]],
) -> DiagnosisColumnRead | None:
    folded = question.casefold()
    for column in columns:
        if column.label and column.label.casefold() in folded:
            return column
    for column in columns:
        if column.name.casefold() in folded:
            return column
    for token, names in synonyms.items():
        if token not in question:
            continue
        for name in names:
            for column in columns:
                if column.name.casefold() == name:
                    return column
    return None


def _resolve(value: Any, columns: list[DiagnosisColumnRead]) -> DiagnosisColumnRead | None:
    if not isinstance(value, str) or not value.strip():
        return None
    folded = value.strip().casefold()
    for column in columns:
        if column.name.casefold() == folded or column.label.casefold() == folded:
            return column
    return None


def _default_column(
    columns: list[DiagnosisColumnRead], default_name: str | None
) -> DiagnosisColumnRead | None:
    if default_name is not None:
        for column in columns:
            if column.name == default_name:
                return column
    return columns[0] if columns else None


__all__ = ["DiagnosisIntentService"]
