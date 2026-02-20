"""LLM prompt and structured output parsing helpers for UI generation."""

from __future__ import annotations

import json
import re
from typing import Any

from ...models import GeneratedUI


def build_ui_prompt(*, prompt: str, framework: str, requirements: dict[str, Any]) -> str:
    """Build system+user prompt for structured UI output."""
    system_prompt = (
        "You are a senior UI/UX designer. Generate production-ready UI with accessible semantics. "
        "Return strictly in this format:\n[HTML]\\n...\\n[/HTML]\\n[CSS]\\n...\\n[/CSS]\\n[JS]\\n...\\n[/JS]"
    )
    return (
        f"{system_prompt}\n\n"
        f"Framework: {framework}\n"
        f"Requirements JSON: {json.dumps(requirements, ensure_ascii=False)}\n"
        f"User request: {prompt}\n"
        "Include responsive layout and meaningful class names."
    )


def parse_structured_ui_output(text: str, framework: str) -> GeneratedUI:
    """Parse [HTML]/[CSS]/[JS] blocks into GeneratedUI."""
    html = extract_tagged_block(text, "HTML")
    css = extract_tagged_block(text, "CSS")
    js = extract_tagged_block(text, "JS")
    if not html:
        raise ValueError("LLM output did not include [HTML] block")
    return GeneratedUI(html=html, css=css, js=js, framework=framework, is_template=False)


def extract_tagged_block(text: str, tag: str) -> str:
    """Extract content from bracketed block, e.g. [HTML]...[/HTML]."""
    pattern = rf"\[{tag}\](.*?)\[/{tag}\]"
    match = re.search(pattern, text, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else ""

