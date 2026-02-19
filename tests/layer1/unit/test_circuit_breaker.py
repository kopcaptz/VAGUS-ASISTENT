"""Unit-тесты Circuit Breaker."""
import pytest
from vagus.layer1.fallback import CircuitBreaker, CircuitBreakerOpenError, CircuitBreakerState


@pytest.mark.asyncio
async def test_circuit_closed_initial():
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=1)
    assert cb.is_closed()
    assert not cb.is_open()


@pytest.mark.asyncio
async def test_circuit_opens_after_failures():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=10)

    async def fail():
        raise ValueError("test")

    for _ in range(2):
        with pytest.raises(ValueError):
            await cb.call(fail)
    assert cb.is_open()


@pytest.mark.asyncio
async def test_circuit_open_raises():
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout=10)
    async def fail():
        raise RuntimeError()
    with pytest.raises(RuntimeError):
        await cb.call(fail)
    async def ok():
        return "ok"
    with pytest.raises(CircuitBreakerOpenError):
        await cb.call(ok)
