"""Unit-тесты DesignerAgent."""

from unittest.mock import MagicMock

import pytest

from vagus.layer2.agent_registry import AgentRegistry
from vagus.layer2.agents import DesignerAgent
from vagus.layer2.models import DesignRequest
from vagus.plugins.manager import PluginManager


async def _mock_llm_stream_ui(prompt: str, **kwargs):
    _ = kwargs
    _ = prompt
    yield {
        "content": (
            "[HTML]\n<main><h1>LLM UI</h1></main>\n[/HTML]\n"
            "[CSS]\nmain{padding:16px;}\n[/CSS]\n"
            "[JS]\nconsole.log('llm');\n[/JS]"
        ),
        "done": True,
    }


async def _mock_llm_stream_fail(prompt: str, **kwargs):
    _ = prompt
    _ = kwargs
    raise RuntimeError("LLM unavailable")
    yield {"content": "", "done": True}


def test_designer_agent_creation():
    """DesignerAgent создаётся с нужной специализацией."""
    mock_llm_router = MagicMock()
    agent = DesignerAgent(llm_router=mock_llm_router, plugin_manager=PluginManager())
    assert agent.name == "designer"
    assert agent.specialization == "ui_ux_design"
    assert agent.can_handle("ui") is True


def test_analyze_ui_method():
    """analyze_ui возвращает базовый UIAnalysis."""
    mock_llm_router = MagicMock()
    agent = DesignerAgent(llm_router=mock_llm_router)
    analysis = agent.analyze_ui("Create a dashboard with accessible contrast and dark mode.")
    assert analysis.layout in {"single-column", "two-column"}
    assert isinstance(analysis.colors, list)
    assert isinstance(analysis.typography, list)
    assert 0.0 <= analysis.accessibility_score <= 1.0


def test_generate_layout_method():
    """generate_layout возвращает HTML/CSS/JS каркас."""
    mock_llm_router = MagicMock()
    agent = DesignerAgent(llm_router=mock_llm_router)
    layout = agent.generate_layout({"title": "Admin Panel", "responsive": True})
    assert "<html" in layout.html.lower()
    assert "container" in layout.css or "page" in layout.css
    assert "DOMContentLoaded" in layout.js
    assert layout.responsive is True


def test_registration_in_registry():
    """DesignerAgent регистрируется и выбирается через AgentRegistry."""
    mock_llm_router = MagicMock()
    agent = DesignerAgent(llm_router=mock_llm_router)
    registry = AgentRegistry()
    registry.register(agent)
    selected = registry.find_by_task_type("ui_layout")
    assert selected is agent


@pytest.mark.parametrize(
    ("style", "signature"),
    [
        ("tailwind", "landing page template ready"),
        ("bootstrap", "dashboard template ready"),
        ("material", "blog template ready"),
        ("custom", "admin panel template ready"),
    ],
)
def test_generate_html_template(style: str, signature: str):
    """Генерация html шаблонов для всех поддерживаемых стилей."""
    agent = DesignerAgent(llm_router=MagicMock())
    html = agent.generate_html_template(style)
    assert "<html" in html.lower()
    assert signature in html.lower()


def test_generate_responsive_layout():
    """Генерация responsive layout с медиазапросами."""
    agent = DesignerAgent(llm_router=MagicMock())
    layout = agent.generate_responsive_layout({"sm": 600, "md": 840})
    assert "@media" in layout.css
    assert "max-width:840px" in layout.css
    assert layout.responsive is True


def test_check_accessibility():
    """Rule-based accessibility checker возвращает issues и score."""
    agent = DesignerAgent(llm_router=MagicMock())
    html = "<html><body><img src='x.png'><button>Click</button></body></html>"
    report = agent.check_accessibility(html)
    assert 0.0 <= report.score <= 1.0
    assert isinstance(report.recommendations, list)
    assert len(report.issues) >= 1


def test_generate_color_palette():
    """Генерация палитры на базе base color."""
    agent = DesignerAgent(llm_router=MagicMock())
    palette = agent.generate_color_palette("#2563EB")
    assert palette.primary == "#2563EB"
    assert palette.secondary.startswith("#")
    assert len(palette.accents) == 3
    assert len(palette.neutrals) >= 3


def test_css_framework_support():
    """Поддержка framework descriptors + CSS snippets."""
    agent = DesignerAgent(llm_router=MagicMock())
    for framework in ("tailwind", "bootstrap", "material", "custom"):
        css = agent.generate_css_framework(framework)
        descriptor = agent.get_css_framework(framework)
        assert isinstance(css, str) and len(css) > 10
        assert descriptor.name == framework
        assert len(descriptor.components) >= 3


@pytest.mark.asyncio
async def test_llm_generation_structured_output():
    """LLM-based генерация парсит structured output HTML/CSS/JS."""
    router = MagicMock()
    router.route_request = _mock_llm_stream_ui
    agent = DesignerAgent(llm_router=router)
    request = DesignRequest(style="tailwind", framework="tailwind", requirements={"title": "Landing"})
    result = await agent.generate_ui(request=request, prompt="Build a landing page", use_llm=True)
    assert result.is_template is False
    assert "<main>" in result.html
    assert "padding:16px" in result.css
    assert "console.log('llm')" in result.js


@pytest.mark.asyncio
async def test_llm_fallback_to_rule_based():
    """При недоступности LLM используется rule-based fallback."""
    router = MagicMock()
    router.route_request = _mock_llm_stream_fail
    agent = DesignerAgent(llm_router=router)
    request = DesignRequest(style="bootstrap", framework="bootstrap", requirements={"title": "Ops Dashboard"})
    result = await agent.generate_ui(request=request, prompt="Build admin dashboard", use_llm=True)
    assert result.is_template is True
    assert "dashboard template ready" in result.html.lower()
    assert result.framework == "bootstrap"
