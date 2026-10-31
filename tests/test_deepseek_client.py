from __future__ import annotations

import httpx
import pytest
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
