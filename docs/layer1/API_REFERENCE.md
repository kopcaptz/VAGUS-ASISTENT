# API Справочник Слоя 1

## Инициализация
```python
from vagus.layer1 import LLMRouter

router = LLMRouter(
    enable_cache=True,
    enable_budgeting=True,
    enable_monitoring=True,
    default_strategy="hybrid",
    fallback_chain=["openai", "anthropic", "deepseek"],
)
await router.initialize()

# С конфигурацией:
from vagus.layer0 import ConfigManager
from vagus.layer1.integration import build_router_kwargs
config_manager = ConfigManager()
config = config_manager.get_config()
kwargs = build_router_kwargs(config)
router = LLMRouter(config_manager=config_manager, **kwargs)
providers_cfg = config.model_dump(by_alias=True).get("providers", {})
await router.initialize(providers_cfg)
```

## Базовый запрос
```python
async for chunk in router.route_request(
    prompt="Привет, как дела?",
    stream=True,
    priority="normal",
    interactive=False
):
    print(chunk.get("content", ""), end="")
```

## Получение статистики
```python
stats = router.get_stats()
print(f"Запросов: {stats.get('requests', 0)}")
print(f"Общая стоимость: ${stats['total_cost']:.2f}")
```