"""E2E test fixtures: real LLMRouter, layer2 config for Context Rot tests."""
import os
from pathlib import Path

import pytest
import yaml

from vagus.layer1 import LLMRouter
from vagus.layer1.integration.config_integration import build_router_kwargs


def _load_runtime_config() -> dict:
    """Load runtime config from vagus.yaml or vagus.yaml.example."""
    candidates = [
        Path(os.getenv("VAGUS_CONFIG_PATH", "")),
        Path("configs/vagus.yaml"),
        Path("configs/vagus.yaml.example"),
    ]
    for path in candidates:
        if path and path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                if isinstance(data, dict):
                    return data
            except Exception:
                continue
    return {}


def _inject_provider_api_keys(config: dict) -> dict:
    """Inject API keys from env into providers config."""
    from vagus.layer0.config.secrets_manager import SecretsManager

    if "providers" not in config:
        return config
    config = dict(config)
    config["providers"] = dict(config["providers"])
    secrets = SecretsManager.from_config(config.get("secrets") or {})
    for name, pcfg in list(config["providers"].items()):
        key = secrets.get_provider_api_key(name)
        if key:
            pcfg = dict(pcfg) if isinstance(pcfg, dict) else {}
            pcfg["api_key"] = key
            config["providers"][name] = pcfg
    return config


@pytest.fixture
def layer2_context_rot_config(tmp_path):
    """Layer2 config for Context Rot E2E: threshold_steps=20, summarizer enabled."""
    return {
        "coherence": {"threshold_steps": 20},
        "conversation_summarizer": {
            "enabled": True,
            "max_input_steps": 50,
            "min_summary_words": 50,
            "max_summary_words": 500,
        },
        "procedural_memory": {
            "enabled": False,
            "db_path": ":memory:",
            "similarity_threshold": 0.7,
        },
        "communication": {"redis_url": None, "event_bus": {"enabled": True}},
        "blackboard": {"redis_url": None, "ttl_hours": 24},
        "intent_classifier": {"confidence_threshold": 0.5},
        "task_planner": {"max_steps": 55},
        "master_orchestrator": {"enable_reflexion": False, "enable_evaluator": False},
        "knowledge_base": {"backend": "sqlite", "sqlite_path": str(tmp_path / "artifact_kb.db")},
    }


@pytest.fixture
async def real_llm_router():
    """Create LLMRouter with real providers (OpenAI/DeepSeek) from config + env keys."""
    config = _load_runtime_config()
    config = _inject_provider_api_keys(config)

    runtime = {
        "layer1": config.get("layer1", {}),
        "retry": config.get("retry", {}),
    }
    router_kwargs = build_router_kwargs(runtime)
    # Disable cache and budgeting for tests to avoid side effects
    router_kwargs["enable_cache"] = False
    router_kwargs["enable_budgeting"] = False
    router_kwargs["enable_monitoring"] = False

    router = LLMRouter(**router_kwargs)
    providers_config = config.get("providers", {})
    if providers_config:
        await router.initialize(providers_config)
    else:
        await router.initialize()

    if not router._providers:
        pytest.skip(
            "No LLM providers available. Set OPENAI_API_KEY or DEEPSEEK_API_KEY to run E2E tests."
        )
    return router
