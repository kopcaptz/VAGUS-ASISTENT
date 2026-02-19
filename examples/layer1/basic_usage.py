#!/usr/bin/env python3
"""
Vagus Asistent — Layer 1 basic usage example.

Demonstrates:
  1. Initialising LLMRouter with cache, budgeting, monitoring
  2. Loading configuration from YAML via ConfigManager
  3. Sending a request and collecting the streamed response
  4. Retrieving aggregated statistics

Run:
    PYTHONPATH=src python examples/layer1/basic_usage.py
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from vagus.layer1 import LLMRouter
from vagus.layer1.integration.config_integration import build_router_kwargs


# ---------------------------------------------------------------------------
# Example 1: Quick start without YAML config
# ---------------------------------------------------------------------------

async def quick_start():
    """Minimal initialisation — no config file needed."""
    print("=" * 60)
    print("Example 1: Quick start (no config file)")
    print("=" * 60)

    router = LLMRouter(
        enable_cache=True,
        enable_budgeting=True,
        enable_monitoring=True,
        fallback_chain=["openai", "anthropic", "deepseek"],
    )
    await router.initialize()

    print(f"  Providers loaded: {list(router._providers.keys())}")
    print(f"  Stats: {router.get_stats()}")
    print()


# ---------------------------------------------------------------------------
# Example 2: Initialisation from YAML config
# ---------------------------------------------------------------------------

async def from_config():
    """Load settings from configs/vagus.yaml (if it exists)."""
    print("=" * 60)
    print("Example 2: From YAML config")
    print("=" * 60)

    config_path = Path("configs/vagus.yaml")
    if not config_path.exists():
        print("  configs/vagus.yaml not found — using defaults.")
        print("  Copy configs/vagus.yaml.example → configs/vagus.yaml to test.\n")
        return

    from vagus.layer0.config import ConfigManager

    cm = ConfigManager(config_path=str(config_path), enable_hot_reload=False)
    config = cm.load()
    kwargs = build_router_kwargs(config)

    router = LLMRouter(config_manager=cm, **kwargs)
    await router.initialize()

    print(f"  Model: {config.global_settings.default_model}")
    print(f"  Providers: {list(router._providers.keys())}")
    print(f"  Cache TTL: {kwargs.get('cache_ttl')}s")
    print(f"  Budget daily: ${kwargs.get('budget_daily')}")
    print()


# ---------------------------------------------------------------------------
# Example 3: Sending a request (requires a valid API key)
# ---------------------------------------------------------------------------

async def send_request():
    """Send a prompt and stream the response (requires API key)."""
    print("=" * 60)
    print("Example 3: Send a request (requires API key)")
    print("=" * 60)

    has_key = any(os.getenv(k) for k in [
        "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY",
    ])
    if not has_key:
        print("  No API key found — skipping live request.")
        print("  Set OPENAI_API_KEY (or another) in .env to test.\n")
        return

    router = LLMRouter(enable_cache=True, enable_budgeting=True)
    await router.initialize()

    prompt = "What is 2 + 2? Answer in one word."
    print(f"  Prompt: {prompt}")
    print("  Response: ", end="")

    async for chunk in router.route_request(prompt=prompt, stream=True):
        content = chunk.get("content", "")
        if content:
            print(content, end="", flush=True)
        if chunk.get("done"):
            break

    print()
    stats = router.get_stats()
    print(f"  Total cost: ${stats.get('total_cost', 0):.6f}")
    print()


# ---------------------------------------------------------------------------

async def main():
    await quick_start()
    await from_config()
    await send_request()
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
