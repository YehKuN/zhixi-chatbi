from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from application import deepseek_client
from application.deepseek_client import DeepSeekResponsesClient, classify_deepseek_error
from openai import APIStatusError, APITimeoutError


@pytest.mark.parametrize(
    ("status_code", "kind", "retryable"),
    [
        (401, "invalid_api_key", False),
        (402, "insufficient_balance", False),
        (429, "upstream_retryable", True),
        (500, "upstream_retryable", True),
    ],
)
def test_status_error_classification(status_code: int, kind: str, retryable: bool) -> None:
    request = httpx.Request("POST", "https://api.deepseek.com/responses")
    error = APIStatusError(
        "provider response",
        response=httpx.Response(status_code, request=request),
        body=None,
    )
    failure = classify_deepseek_error(error)
    assert failure.kind == kind
    assert failure.retryable is retryable
    assert failure.status_code == status_code


def test_timeout_error_is_retryable() -> None:
    error = APITimeoutError(request=httpx.Request("POST", "https://api.deepseek.com/responses"))
    failure = classify_deepseek_error(error)
    assert failure.kind == "timeout"
    assert failure.retryable is True


@pytest.mark.asyncio
async def test_missing_key_fails_closed_without_network_call() -> None:
    client = DeepSeekResponsesClient(api_key=None)
    events = [
        event
        async for event in client.stream_analysis(
            question="核对本月营收",
            dataset_context="累计订单金额 100 万元",
        )
    ]
    assert len(events) == 1
    assert events[0][0] == "error"
    assert "DEEPSEEK_API_KEY" in events[0][1]


class _FakeStream:
    def __init__(self, events: list[object]) -> None:
        self._events = events

    def __aiter__(self) -> _FakeStream:
        return self

    async def __anext__(self) -> object:
        if not self._events:
            raise StopAsyncIteration
        return self._events.pop(0)


class _FakeResponses:
    def __init__(self, events: list[object]) -> None:
        self._events = events
        self.calls = 0

    async def create(self, **kwargs: object) -> _FakeStream:
        del kwargs
        self.calls += 1
        return _FakeStream(list(self._events))


class _FakeOpenAI:
    events: list[object] = []

    def __init__(self, **kwargs: object) -> None:
        del kwargs
        self.responses = _FakeResponses(type(self).events)


def _delta(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="response.output_text.delta", delta=text)


def _incomplete(reason: str = "max_output_tokens") -> SimpleNamespace:
    return SimpleNamespace(
        type="response.incomplete",
        response=SimpleNamespace(incomplete_details=SimpleNamespace(reason=reason)),
    )


@pytest.mark.asyncio
async def test_incomplete_after_partial_output_is_kept_with_notice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakeOpenAI.events = [_delta("## 结论\n"), _incomplete()]
    monkeypatch.setattr(deepseek_client, "AsyncOpenAI", _FakeOpenAI)
    client = DeepSeekResponsesClient(api_key="test-key", max_retries=0)

    events = [
        event
        async for event in client.stream_analysis(question="详细分析", dataset_context="上下文")
    ]

    assert [kind for kind, _ in events] == ["delta", "delta", "done"]
    assert "长度上限" in events[1][1]
    assert all(kind != "error" for kind, _ in events)


@pytest.mark.asyncio
async def test_incomplete_without_output_returns_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeOpenAI.events = [_incomplete()]
    monkeypatch.setattr(deepseek_client, "AsyncOpenAI", _FakeOpenAI)
    client = DeepSeekResponsesClient(api_key="test-key", max_retries=0)

    events = [
        event
        async for event in client.stream_analysis(question="详细分析", dataset_context="上下文")
    ]

    assert len(events) == 1
    assert events[0][0] == "error"
    assert "未能完整生成" in events[0][1]
