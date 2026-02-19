#!/usr/bin/env python3
"""
Скрипт для создания структуры Слоя 1 Vagus Asistent.
"""

import os
from pathlib import Path

# Базовый путь
base_path = Path(__file__).parent / "src" / "vagus" / "layer1"

# Структура Слоя 1 на основе ТЗ
structure = {
    "router": [
        "__init__.py",
        "llm_router.py",
        "router_manager.py", 
        "request_handler.py",
        "response_builder.py"
    ],
    "providers": [
        "__init__.py",
        "base_provider.py",
        "openai_provider.py",
        "anthropic_provider.py",
        "deepseek_provider.py",
        "openrouter_provider.py",
        "google_provider.py",
        "provider_factory.py",
        "provider_registry.py"
    ],
    "balancing": [
        "__init__.py",
        "base_strategy.py",
        "cost_strategy.py",
        "latency_strategy.py",
        "quality_strategy.py",
        "hybrid_strategy.py",
        "strategy_manager.py"
    ],
    "fallback": [
        "__init__.py",
        "circuit_breaker.py",
        "fallback_handler.py",
        "fallback_chain.py",
        "retry_manager.py"
    ],
    "monitoring": [
        "__init__.py",
        "monitoring_service.py",
        "metrics_collector.py",
        "latency_tracker.py",
        "cost_tracker.py",
        "quality_monitor.py",
        "metrics_storage.py"
    ],
    "cache": [
        "__init__.py",
        "cache_service.py",
        "cache_key_generator.py",
        "cache_stats.py"
    ],
    "budgeting": [
        "__init__.py",
        "budgeting_service.py",
        "budget_limits.py",
        "expense_tracker.py"
    ],
    "integration": [
        "__init__.py",
        "config_integration.py",
        "logging_integration.py",
        "hot_reload_integration.py"
    ]
}

# Создаём структуру
print(f"Создание структуры Слоя 1 в: {base_path}")

for folder, files in structure.items():
    folder_path = base_path / folder
    folder_path.mkdir(parents=True, exist_ok=True)
    print(f"  📁 Создана папка: {folder}")
    
    for file in files:
        file_path = folder_path / file
        if not file_path.exists():
            file_path.touch()
            print(f"    📄 Создан файл: {file}")
        else:
            print(f"    ⚠️  Файл уже существует: {file}")

# Создаём __init__.py для layer1
layer1_init = base_path.parent / "__init__.py"
if not layer1_init.exists():
    layer1_init.write_text('''
"""
Слой 1: Ядро LLM - мульти-модельный роутер.
"""

from .router import LLMRouter
from .providers import BaseProvider, ProviderFactory
from .balancing import BaseBalancingStrategy, HybridStrategy
from .fallback import CircuitBreaker, FallbackHandler
from .monitoring import MonitoringService
from .cache import CacheService
from .budgeting import BudgetingService

__all__ = [
    'LLMRouter',
    'BaseProvider',
    'ProviderFactory',
    'BaseBalancingStrategy',
    'HybridStrategy',
    'CircuitBreaker',
    'FallbackHandler',
    'MonitoringService',
    'CacheService',
    'BudgetingService'
]
''')
    print(f"  📄 Создан: src/vagus/layer1/__init__.py")

# Создаём тестовую структуру
tests_path = Path(__file__).parent / "tests" / "layer1"
tests_structure = {
    "unit": [
        "test_circuit_breaker.py",
        "test_cache_service.py",
        "test_budgeting_service.py",
        "test_strategies.py"
    ],
    "integration": [
        "test_fallback_chain.py",
        "test_full_request_cycle.py",
        "test_config_hot_reload.py"
    ],
    "load": [
        "locustfile.py"
    ]
}

print(f"\nСоздание структуры тестов в: {tests_path}")

for folder, files in tests_structure.items():
    folder_path = tests_path / folder
    folder_path.mkdir(parents=True, exist_ok=True)
    print(f"  📁 Создана папка: tests/layer1/{folder}")
    
    for file in files:
        file_path = folder_path / file
        if not file_path.exists():
            file_path.touch()
            print(f"    📄 Создан файл: {file}")

# Создаём документацию
docs_path = Path(__file__).parent / "docs" / "layer1"
docs_path.mkdir(parents=True, exist_ok=True)

docs_files = {
    "ARCHITECTURE.md": "# Архитектура Слоя 1\n\n## Компоненты\n\n### 1. Роутер (router/)\n- LLMRouter - фасад системы\n- RouterManager - управление роутером\n\n### 2. Провайдеры (providers/)\n- BaseProvider - абстрактный класс\n- Конкретные провайдеры: OpenAI, Anthropic, DeepSeek, OpenRouter\n\n### 3. Стратегии балансировки (balancing/)\n- BaseBalancingStrategy - абстрактный класс\n- HybridStrategy - основная стратегия\n\n### 4. Fallback система (fallback/)\n- CircuitBreaker - паттерн Circuit Breaker\n- FallbackHandler - управление fallback цепочками\n\n### 5. Мониторинг (monitoring/)\n- MonitoringService - сбор метрик\n- SQLite хранилище\n\n### 6. Кэширование (cache/)\n- CacheService - in-memory кэш с TTL\n\n### 7. Бюджетирование (budgeting/)\n- BudgetingService - контроль лимитов расходов\n\n### 8. Интеграция (integration/)\n- Интеграция с Слоем 0 (конфигурация, логирование)",
    "API_REFERENCE.md": "# API Справочник Слоя 1\n\n## Инициализация\n```python\nfrom vagus.layer0 import ConfigManager\nfrom vagus.layer1 import LLMRouter\n\nconfig_manager = ConfigManager()\nrouter = LLMRouter(config_manager)\nawait router.initialize()\n```\n\n## Базовый запрос\n```python\nasync for chunk in router.route_request(\n    prompt=\"Привет, как дела?\",\n    stream=True,\n    priority=\"normal\",\n    interactive=False\n):\n    print(chunk.get(\"content\", \"\"), end=\"\")\n```\n\n## Получение статистики\n```python\nstats = router.get_stats()\nprint(f\"Использовано провайдеров: {stats['providers_used']}\")\nprint(f\"Общая стоимость: ${stats['total_cost']:.2f}\")\n```",
    "CONFIGURATION.md": "# Конфигурация Слоя 1\n\n## Пример конфигурации (дополнение к vagus.yaml)\n```yaml\nlayer1:\n  router:\n    enable_cache: true\n    enable_budgeting: true\n    enable_monitoring: true\n    default_strategy: \"hybrid\"\n    \n  cache:\n    ttl_seconds: 3600\n    max_size_mb: 100\n    \n  budgeting:\n    daily_limit_usd: 10.0\n    monthly_limit_usd: 200.0\n    \n  monitoring:\n    db_path: \"metrics.db\"\n    retention_days: 30\n    \n  fallback:\n    max_retries: 3\n    base_delay_seconds: 1.0\n    circuit_breaker:\n      failure_threshold: 5\n      recovery_timeout_seconds: 60\n      \n  strategies:\n    hybrid:\n      weights:\n        normal: {cost: 0.33, latency: 0.33, quality: 0.34}\n        urgent: {cost: 0.10, latency: 0.80, quality: 0.10}\n        low: {cost: 0.80, latency: 0.10, quality: 0.10}\n```"
}

for filename, content in docs_files.items():
    file_path = docs_path / filename
    if not file_path.exists():
        file_path.write_text(content, encoding="utf-8")
        print(f"  📄 Создана документация: docs/layer1/{filename}")

print(f"\n✅ Структура Слоя 1 создана успешно!")
print(f"📁 Всего создано: {sum(len(files) for files in structure.values())} файлов")
print(f"📁 Папки: {', '.join(structure.keys())}")