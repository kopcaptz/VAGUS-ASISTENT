"""Unit tests for retry_handler exponential backoff."""

import pytest

from vagus.layer1.fallback.retry_handler import RetryConfig, RetryHandler


@pytest.mark.asyncio
async def test_retry_handler_retries_transient_errors_until_success():
    calls = {"count": 0}
    delays: list[float] = []

    async def fake_sleep(delay: float):
        delays.append(delay)

    async def flaky():
        calls["count"] += 1
        if calls["count"] < 3:
            raise TimeoutError("request timeout")
        return "ok"

    handler = RetryHandler(
        config=RetryConfig(
            max_attempts=5,
            backoff_factor=2.0,
            retryable_errors=["timeout", "rate_limit", "network_error"],
        ),
        base_delay_seconds=1.0,
        sleep_func=fake_sleep,
    )
    result = await handler.execute(flaky)
    assert result == "ok"
    assert calls["count"] == 3
    assert delays == [1.0, 2.0]


@pytest.mark.asyncio
async def test_retry_handler_does_not_retry_non_retryable_errors():
    calls = {"count": 0}
    delays: list[float] = []

    async def fake_sleep(delay: float):
        delays.append(delay)

    async def fail_once():
        calls["count"] += 1
        raise ValueError("validation failed")

    handler = RetryHandler(
        config=RetryConfig(
            max_attempts=5,
            backoff_factor=2.0,
            retryable_errors=["timeout", "rate_limit", "network_error"],
        ),
        sleep_func=fake_sleep,
    )
    with pytest.raises(ValueError):
        await handler.execute(fail_once)
    assert calls["count"] == 1
    assert delays == []


@pytest.mark.asyncio
async def test_retry_handler_exhausts_attempts_with_expected_backoff():
    calls = {"count": 0}
    delays: list[float] = []

    async def fake_sleep(delay: float):
        delays.append(delay)

    async def always_fail():
        calls["count"] += 1
        raise RuntimeError("network_error: transport dropped")

    handler = RetryHandler(
        config=RetryConfig(
            max_attempts=5,
            backoff_factor=2.0,
            retryable_errors=["timeout", "rate_limit", "network_error"],
        ),
        base_delay_seconds=1.0,
        sleep_func=fake_sleep,
    )
    with pytest.raises(RuntimeError):
        await handler.execute(always_fail)
    assert calls["count"] == 5
    assert delays == [1.0, 2.0, 4.0, 8.0]


def test_retry_config_from_dict_sanitizes_values():
    cfg = RetryConfig.from_dict(
        {
            "max_attempts": "7",
            "backoff_factor": "2.5",
            "retryable_errors": ["timeout", "", 123, "network_error"],
        }
    )
    assert cfg.max_attempts == 7
    assert cfg.backoff_factor == 2.5
    assert cfg.retryable_errors == ["timeout", "network_error"]
