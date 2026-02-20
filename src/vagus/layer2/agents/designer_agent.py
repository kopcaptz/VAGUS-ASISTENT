"""DesignerAgent — hybrid UI/UX generation with rule-based fallback."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

from ..models import (
    AccessibilityReport,
    CSSFramework,
    ColorPalette,
    DesignRequest,
    GeneratedUI,
    Recommendation,
    UIAnalysis,
    UILayout,
)
from ..types import AgentContext, AgentResult, AgentTask
from .base_agent import BaseAgent
from .designer.analyzers import (
    build_accessibility_report,
    estimate_css_complexity,
    generate_color_palette,
)
from .designer.frameworks import get_framework_css, get_framework_descriptor, normalize_framework
from .designer.llm_ui import build_ui_prompt, parse_structured_ui_output
from .protocols import LLMRouterProtocol, PluginManagerProtocol
from .designer.template_engine import (
    load_template,
    merge_template_params,
    pick_template_file,
    render_template,
)


class DesignerAgent(BaseAgent):
    """Agent for hybrid UI generation and rule-based design analysis."""

    TASK_TYPES = (
        "design",
        "ui",
        "ux",
        "layout",
        "mockup",
        "template",
        "accessibility",
        "palette",
        "интерфейс",
        "дизайн",
    )

    def __init__(
        self,
        llm_router: LLMRouterProtocol,
        *,
        plugin_manager: Optional[PluginManagerProtocol] = None,
        description: str = "Агент для гибридной UI/UX генерации интерфейсов",
    ) -> None:
        super().__init__(name="designer", llm_router=llm_router, description=description)
        self.specialization = "ui_ux_design"
        self.plugin_manager = plugin_manager
        self._templates_dir = Path(__file__).resolve().parent / "designer" / "templates"
        self._ui_cache: dict[str, GeneratedUI] = {}

    def can_handle(self, task_type: str) -> bool:
        task_lower = (task_type or "").lower()
        return any(t in task_lower for t in self.TASK_TYPES) or task_type == "default"

    async def process(
        self,
        task: AgentTask,
        context: Optional[AgentContext] = None,
    ) -> AgentResult:
        """Process design requests using hybrid generation."""
        prompt = str(task.get("prompt", "")).strip()
        if not prompt:
            return {"content": "", "error": "Empty prompt", "metadata": {}}

        task_type = str(task.get("task_type", "design")).lower()
        if "improve" in task_type or "improvement" in task_type or "audit" in task_type:
            recommendations = self.recommend_improvements(prompt)
            content = "\n".join(f"- [{r.priority}] {r.type}: {r.description}" for r in recommendations)
            return {
                "content": content,
                "recommendations": recommendations,
                "metadata": self._build_metadata("recommend_improvements", context),
            }

        if "accessibility" in task_type:
            report = self.check_accessibility(prompt)
            return {
                "content": f"Accessibility score: {report.score:.2f}",
                "accessibility_report": report,
                "metadata": self._build_metadata("check_accessibility", context),
            }

        if "palette" in task_type or "color" in task_type:
            palette = self.generate_color_palette(str(task.get("base_color", "#2563EB")))
            return {
                "content": f"Primary: {palette.primary}; Secondary: {palette.secondary}",
                "palette": palette,
                "metadata": self._build_metadata("generate_color_palette", context),
            }

        if any(x in task_type for x in ("layout", "mockup", "template", "generate_ui")):
            request = DesignRequest(
                style=str(task.get("style", task.get("framework", "tailwind"))).lower(),
                framework=str(task.get("framework", task.get("style", "tailwind"))).lower(),
                requirements=task.get("requirements", {}) if isinstance(task.get("requirements"), dict) else {},
            )
            generated = await self.generate_ui(
                request=request,
                prompt=prompt,
                use_llm=bool(task.get("use_llm", True)),
            )
            report = self.check_accessibility(generated.html)
            return {
                "content": generated.html,
                "generated_ui": generated,
                "accessibility_report": report,
                "metadata": self._build_metadata(
                    "generate_ui",
                    context,
                    extra={"framework": generated.framework, "is_template": generated.is_template},
                ),
            }

        analysis = self.analyze_ui(prompt)
        return {
            "content": self._format_analysis(analysis),
            "analysis": analysis,
            "metadata": self._build_metadata("analyze_ui", context),
        }

    def analyze_ui(self, description: str) -> UIAnalysis:
        text = (description or "").lower()
        colors = ["#2563EB", "#F8FAFC"] if "dark" not in text else ["#0F172A", "#E2E8F0"]
        typography = ["Inter", "system-ui"] if "mobile" in text else ["Roboto", "Arial"]
        layout = "two-column" if any(k in text for k in ("dashboard", "panel", "admin")) else "single-column"
        accessibility_score = 0.9 if ("contrast" in text or "accessible" in text) else 0.82
        return UIAnalysis(colors=colors, typography=typography, layout=layout, accessibility_score=accessibility_score)

    def generate_layout(self, requirements: dict) -> UILayout:
        title = str(requirements.get("title", "UI Layout"))
        responsive = bool(requirements.get("responsive", True))
        framework = normalize_framework(str(requirements.get("framework", "tailwind")))
        html = self.generate_html_template(framework, {"title": title, "heading": title})
        css = self.generate_css_framework(framework)
        js = "document.addEventListener('DOMContentLoaded', () => console.log('layout ready'));"
        return UILayout(html=html, css=css, js=js, responsive=responsive)

    def generate_html_template(self, style: str = "tailwind", params: Optional[dict[str, str]] = None) -> str:
        file_name = pick_template_file(style)
        template = load_template(self._templates_dir, file_name)
        merged = merge_template_params(params)
        return render_template(template, merged)

    def generate_css_framework(self, framework: str = "tailwind") -> str:
        return get_framework_css(framework)

    def generate_responsive_layout(self, breakpoints: dict) -> UILayout:
        base = {"sm": 640, "md": 768}
        for key, value in (breakpoints or {}).items():
            try:
                base[str(key)] = int(value)
            except (TypeError, ValueError):
                continue
        html = "<main class=\"page\"><section class=\"grid\"><article>Card A</article><article>Card B</article></section></main>"
        css = [
            ".page{padding:16px;}",
            ".grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;}",
            "article{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:12px;}",
            f"@media (max-width:{base['md']}px){{.grid{{grid-template-columns:1fr;}}}}",
            f"@media (max-width:{base['sm']}px){{.page{{padding:8px;}}}}",
        ]
        js = "window.addEventListener('resize', () => document.body.dataset.responsive = '1');"
        return UILayout(html=html, css="".join(css), js=js, responsive=True)

    def check_accessibility(self, html: str) -> AccessibilityReport:
        return build_accessibility_report(html)

    def generate_color_palette(self, base_color: str) -> ColorPalette:
        return generate_color_palette(base_color)

    def recommend_improvements(self, existing_ui: str) -> List[Recommendation]:
        text = (existing_ui or "").lower()
        recs: List[Recommendation] = [
            Recommendation(
                type="accessibility",
                description="Increase text contrast and ensure keyboard focus states.",
                priority=1,
            ),
            Recommendation(
                type="layout",
                description="Improve spacing consistency using an 8px scale.",
                priority=2,
            ),
        ]
        if estimate_css_complexity(text) > 14:
            recs.append(
                Recommendation(
                    type="performance",
                    description="Reduce CSS selector nesting and duplicated rules for better performance.",
                    priority=2,
                )
            )
        if "form" in text or "login" in text:
            recs.append(
                Recommendation(
                    type="ux",
                    description="Add inline validation and clear error messages for form fields.",
                    priority=1,
                )
            )
        return recs

    async def generate_ui(self, request: DesignRequest, prompt: str, use_llm: bool = True) -> GeneratedUI:
        framework = normalize_framework(request.framework or request.style)
        cache_key = self._build_cache_key(prompt, framework, request.requirements)
        if cache_key in self._ui_cache:
            return self._ui_cache[cache_key]

        if use_llm and self.llm_router is not None:
            try:
                llm_prompt = build_ui_prompt(
                    prompt=prompt,
                    framework=framework,
                    requirements=request.requirements,
                )
                llm_result = await self._call_llm(llm_prompt)
                parsed = parse_structured_ui_output(llm_result, framework)
                self._ui_cache[cache_key] = parsed
                return parsed
            except Exception:
                self.logger.warning("LLM generation failed, fallback to rule-based template", exc_info=True)

        html = self.generate_html_template(framework, self._request_to_template_params(request.requirements))
        css = self.generate_css_framework(framework)
        generated = GeneratedUI(
            html=html,
            css=css,
            js="console.log('template mode');",
            framework=framework,
            is_template=True,
        )
        self._ui_cache[cache_key] = generated
        return generated

    def get_css_framework(self, framework: str) -> CSSFramework:
        return get_framework_descriptor(framework)

    async def _call_llm(self, prompt: str) -> str:
        content_parts: list[str] = []
        router = cast(LLMRouterProtocol, self.llm_router)
        async for chunk in router.route_request(prompt, stream=True):
            content_parts.append(chunk.get("content", ""))
            if chunk.get("done"):
                break
        return "".join(content_parts)

    def _build_cache_key(self, prompt: str, framework: str, requirements: dict[str, Any]) -> str:
        payload = json.dumps(
            {"prompt": prompt, "framework": framework, "requirements": requirements},
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _request_to_template_params(self, requirements: dict[str, Any]) -> dict[str, str]:
        return {
            "title": str(requirements.get("title", "Generated UI")),
            "heading": str(requirements.get("heading", "Generated heading")),
            "subheading": str(requirements.get("subheading", "Generated subheading")),
            "cta_text": str(requirements.get("cta_text", "Try now")),
            "body_text": str(requirements.get("body_text", "Generated by hybrid DesignerAgent.")),
            "primary_color": str(requirements.get("primary_color", "#2563EB")),
            "background_color": str(requirements.get("background_color", "#F8FAFC")),
        }

    def _build_metadata(
        self,
        method: str,
        context: Optional[AgentContext],
        *,
        extra: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "agent": "designer",
            "specialization": self.specialization,
            "method": method,
            "plugin_support": bool(self.plugin_manager),
            "cache_size": len(self._ui_cache),
        }
        if self.plugin_manager is not None:
            metadata["plugins"] = self._safe_list_plugins()
        if context:
            metadata["has_context"] = True
        if extra:
            metadata.update(extra)
        return metadata

    def _safe_list_plugins(self) -> List[str]:
        manager = self.plugin_manager
        if manager is None or not hasattr(manager, "list_plugins"):
            return []
        try:
            plugins = manager.list_plugins()
            if not isinstance(plugins, list):
                return []
            names: List[str] = []
            for plugin in plugins:
                if isinstance(plugin, dict):
                    name = plugin.get("name")
                    if isinstance(name, str) and name:
                        names.append(name)
            return names
        except Exception:
            return []

    @staticmethod
    def _format_analysis(analysis: UIAnalysis) -> str:
        return (
            f"Layout: {analysis.layout}\n"
            f"Colors: {', '.join(analysis.colors)}\n"
            f"Typography: {', '.join(analysis.typography)}\n"
            f"Accessibility score: {analysis.accessibility_score:.2f}"
        )


__all__ = ["DesignerAgent"]

