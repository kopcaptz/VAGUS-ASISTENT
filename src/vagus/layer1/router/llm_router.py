"""
LLMRouter — фасад системы, координация всех компонентов.
"""

import time
from typing import Dict, Any, Optional, AsyncGenerator
from ..providers.base_provider import LLMProvider
from ..providers.provider_factory import ProviderFactory
from ..cache.cache_service import CacheService
from ..budgeting.budgeting_service import BudgetingService
from ..monitoring.monitoring_service import MonitoringService
from ..monitoring.metrics_storage import MetricsStorage
from ..fallback.fallback_handler import FallbackHandler
from ..fallback.fallback_chain import FallbackChain
from ..balancing.strategy_manager import StrategyManager
from .request_handler import RequestHandler
from .response_builder import ResponseBuilder
from ...layer0.logging import get_logger

try:
    from ...layer3.api.metrics import (
        record_cache_hit,
        record_cache_miss,
        record_llm_request,
        update_circuit_breaker_state_from_router,
    )
except Exception:  # pragma: no cover - defensive fallback for import-time issues
    def record_cache_hit() -> None:
        return None

    def record_cache_miss() -> None:
        return None

    def record_llm_request(provider: str, model: str, status: str) -> None:
        return None

    def update_circuit_breaker_state_from_router(llm_router: object) -> None:
        return None


class LLMRouter:
    """Центральная точка входа для запросов к LLM."""

    def __init__(
        self,
        config_manager=None,
        *,
        enable_cache: bool = True,
        enable_budgeting: bool = True,
        enable_monitoring: bool = True,
        default_strategy: str = "hybrid",
        cache_ttl: int = 3600,
        cache_max_mb: int = 100,
        budget_daily: float = 10.0,
        budget_monthly: float = 200.0,
        monitoring_db: str = "metrics.db",
        monitoring_retention_days: int = 30,
        fallback_max_retries: int = 3,
        fallback_base_delay: float = 1.0,
        fallback_chain: Optional[list] = None,
        retry_max_attempts: int = 5,
        retry_backoff_factor: float = 2.0,
        retry_retryable_errors: Optional[list[str]] = None,
    ):
        self.config_manager = config_manager
        self.enable_cache = enable_cache
        self.enable_budgeting = enable_budgeting
        self.enable_monitoring = enable_monitoring
        self.default_strategy_name = default_strategy
        self.logger = get_logger("router")
        self._initialized = False

        self.cache = CacheService(ttl_seconds=cache_ttl, max_size_mb=cache_max_mb)
        self.budgeting = BudgetingService(
            daily_limit=budget_daily,
            monthly_limit=budget_monthly,
        )
        self.monitoring = MonitoringService(
            db_path=monitoring_db,
            retention_days=monitoring_retention_days,
        )
        self.fallback_handler = FallbackHandler(
            max_retries=fallback_max_retries,
            base_delay=fallback_base_delay,
            retry_config={
                "max_attempts": retry_max_attempts,
                "backoff_factor": retry_backoff_factor,
                "retryable_errors": retry_retryable_errors
                or ["timeout", "rate_limit", "network_error"],
            },
        )
        self.strategy_manager = StrategyManager()
        self.strategy_manager.set_default(default_strategy)
        self.provider_factory = ProviderFactory()
        self.request_handler = RequestHandler()
        self.response_builder = ResponseBuilder()

        self._providers: Dict[str, LLMProvider] = {}
        self._fallback_chain = FallbackChain(provider_ids=fallback_chain or ["openai", "anthropic", "deepseek"])
        self._stats: Dict[str, Any] = {"providers_used": 0, "total_cost": 0.0, "requests": 0}

    async def initialize(self, providers_config: Optional[Dict[str, Any]] = None) -> None:
        """
        Инициализация: загрузка провайдеров, стратегий, цепочек.
        """
        if self._initialized:
            return
        providers_config = providers_config or {}
        for pid, pcfg in providers_config.items():
            if isinstance(pcfg, dict) and pcfg.get("enabled", True):
                try:
                    prov = self.provider_factory.create_from_config(pcfg, pid)
                    self._providers[pid] = prov
                    self.logger.info(f"Provider loaded: {pid}")
                except Exception as e:
                    self.logger.warning(f"Failed to load provider {pid}: {e}")
        if not self._providers:
            for pid in ["openai", "anthropic", "deepseek"]:
                try:
                    prov = self.provider_factory.create(pid, "gpt-4o-mini" if pid == "openai" else "claude-3-5-sonnet-20241022" if pid == "anthropic" else "deepseek-chat")
                    if prov.is_available():
                        self._providers[pid] = prov
                except Exception as e:
                    self.logger.debug(f"Provider {pid} not available: {e}")
        self._initialized = True
        self.logger.info(f"LLMRouter initialized with {len(self._providers)} providers")

    async def route_request(
        self,
        prompt: str,
        stream: bool = True,
        priority: str = "normal",
        interactive: bool = False,
        model: Optional[str] = None,
        **kwargs,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Основной поток: кэш → бюджет → стратегия → fallback → кэш → метрики → бюджет.
        """
        req = self.request_handler.parse(
            prompt=prompt, stream=stream, priority=priority,
            interactive=interactive, model=model, **kwargs
        )
        trace_id = MetricsStorage.generate_trace_id()
        cache_key_kw = {"model": model or "default", "priority": priority}

        if self.enable_cache:
            cached = await self.cache.get(prompt, **cache_key_kw)
            if cached is not None:
                record_cache_hit()
                self.logger.debug("Cache HIT")
                if stream and isinstance(cached, str):
                    yield self.response_builder.build_chunk(cached, done=True)
                elif isinstance(cached, dict):
                    yield {**cached, "done": True}
                else:
                    yield self.response_builder.build_chunk(str(cached), done=True)
                return
            record_cache_miss()

        if self.enable_budgeting:
            await self.budgeting.check_budget(estimated_cost=0.01)

        strategy = self.strategy_manager.get_strategy()
        provider_infos = {}
        for pid, prov in self._providers.items():
            if prov.is_available():
                provider_infos[pid] = {
                    "cost": 0.001,
                    "latency": 100,
                    "quality": 0.7,
                    "provider_obj": prov,
                }
        if not provider_infos:
            raise RuntimeError("No available providers")

        chain_ids = self._fallback_chain.get_providers()
        chain_ids = [p for p in chain_ids if p in provider_infos] or list(provider_infos.keys())
        try:
            selected = strategy.select_provider(provider_infos, {"priority": priority, "interactive": interactive})
        except Exception:
            selected = chain_ids[0]

        async def do_request(pid: str):
            prov = self._providers.get(pid)
            if not prov:
                raise ValueError(f"Provider {pid} not found")
            gen = prov.request(
                prompt=req.prompt,
                stream=stream,
                model=model or prov.model,
                temperature=req.temperature,
                max_tokens=req.max_tokens,
                **kwargs,
            )
            if stream:
                chunks = []
                async for chunk in gen:
                    chunks.append(chunk)
                return chunks
            content_parts = []
            async for chunk in gen:
                content_parts.append(chunk.get("content", ""))
                if chunk.get("done"):
                    break
            return "".join(content_parts)

        result = None
        used_provider = None
        cost = 0.0
        start_time = time.monotonic()

        async def request_coro(pid: str):
            return await do_request(pid)

        try:
            exec_result = await self.fallback_handler.execute(
                provider_ids=chain_ids,
                request_func=request_coro,
                provider_getter=lambda pid: self._providers.get(pid),
            )
            result, used_provider = exec_result
        except Exception as e:
            self.logger.error(f"Request failed: {e}")
            record_llm_request(chain_ids[0], model or "unknown", "error")
            update_circuit_breaker_state_from_router(self)
            if self.enable_monitoring:
                self.monitoring.record_complete_request(
                    trace_id=trace_id, provider=chain_ids[0], model=model or "unknown",
                    success=False, error_type=type(e).__name__,
                )
            raise

        if stream and isinstance(result, list):
            for chunk in result:
                yield chunk
            content_str = "".join(c.get("content", "") for c in result)
        else:
            content_str = result if isinstance(result, str) else str(result)
        latency = (time.monotonic() - start_time) * 1000
        if used_provider and used_provider in self._providers:
            prov = self._providers[used_provider]
            cost = prov.calculate_cost(100, len(content_str) // 4)
        if self.enable_budgeting and cost > 0:
            await self.budgeting.record_expense(cost)
        if self.enable_monitoring:
            self.monitoring.record_complete_request(
                trace_id=trace_id, provider=used_provider or "unknown", model=model or "unknown",
                success=True, e2e_ms=latency, cost_usd=cost,
            )
        record_llm_request(used_provider or "unknown", model or "unknown", "success")
        update_circuit_breaker_state_from_router(self)
        if self.enable_cache and content_str:
            await self.cache.set(prompt, content_str, **cache_key_kw)
        self._stats["requests"] = self._stats.get("requests", 0) + 1
        self._stats["total_cost"] = self._stats.get("total_cost", 0) + cost

    def get_stats(self) -> Dict[str, Any]:
        """Агрегация статистики из Cache, Budgeting, Monitoring."""
        stats = dict(self._stats)
        try:
            stats["cache"] = self.cache.get_stats()
        except Exception:
            pass
        try:
            stats["budgeting"] = self.budgeting.get_stats()
        except Exception:
            pass
        try:
            stats["monitoring"] = self.monitoring.get_stats()
        except Exception:
            pass
        return stats
