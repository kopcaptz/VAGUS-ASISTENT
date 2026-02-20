# DesignerAgent

## Назначение

`DesignerAgent` — гибридный агент UI/UX генерации в `layer2`:
- rule-based шаблоны для типовых интерфейсов;
- LLM-based генерация для custom запросов;
- fallback на rule-based при ошибке/недоступности LLM.

## Специализация

- `specialization`: `ui_ux_design`
- Типы задач: `design`, `ui`, `ux`, `layout`, `mockup`, `template`, `accessibility`, `palette`
- Поддерживаемые фреймворки: `tailwind`, `bootstrap`, `material`, `custom`

## Гибридная архитектура

1. `DesignRequest` проходит через стратегию генерации.
2. Если LLM доступен и включён (`use_llm=True`) — используется structured output (`[HTML]`, `[CSS]`, `[JS]`).
3. При ошибке LLM автоматически применяется rule-based шаблон.
4. Результат анализируется rule-based инструментами (accessibility/contrast/CSS complexity).

## Основные методы

- `analyze_ui(description: str) -> UIAnalysis`
- `generate_layout(requirements: dict) -> UILayout`
- `recommend_improvements(existing_ui: str) -> list[Recommendation]`
- `generate_html_template(style: str = "tailwind") -> str`
- `generate_css_framework(framework: str = "tailwind") -> str`
- `generate_responsive_layout(breakpoints: dict) -> UILayout`
- `check_accessibility(html: str) -> AccessibilityReport`
- `generate_color_palette(base_color: str) -> ColorPalette`
- `generate_ui(request: DesignRequest, prompt: str, use_llm: bool = True) -> GeneratedUI`

## Примеры использования

### 1) Генерация landing page

```python
request = DesignRequest(
    style="tailwind",
    framework="tailwind",
    requirements={"title": "Acme Landing", "heading": "Ship faster"},
)
ui = await designer.generate_ui(request=request, prompt="Create landing page", use_llm=True)
```

### 2) Создание дизайн-системы

```python
palette = designer.generate_color_palette("#2563EB")
framework = designer.get_css_framework("material")
css_base = designer.generate_css_framework("material")
```

### 3) Accessibility проверки

```python
report = designer.check_accessibility(ui.html)
print(report.score, [issue.code for issue in report.issues])
```

## Rule-based шаблоны

Шаблоны расположены в `src/vagus/layer2/agents/designer/templates/`:
- `landing_page.html` (Tailwind-oriented)
- `dashboard.html` (Bootstrap-like grid)
- `blog_post.html` (Material-like style)
- `admin_panel.html` (Custom CSS)

Каждый шаблон содержит placeholder-параметры вида `{{title}}`, `{{primary_color}}`, `{{heading}}`.

## Как добавить новый шаблон

1. Добавить новый HTML-файл в `src/vagus/layer2/agents/designer/templates/`.
2. Использовать placeholders `{{...}}` для параметризации текста/цветов.
3. Добавить mapping стиля в `DesignerAgent._TEMPLATE_FILE_BY_STYLE`.
4. Добавить тест в `tests/layer2/test_designer_agent.py`.

## Интеграция в систему

- Регистрируется через `AgentRegistry` и доступен в `TaskOrchestrator`.
- Включается в `create_orchestrator_full()`.
- Поддерживает `plugin_manager` (best-effort список установленных плагинов в metadata).
