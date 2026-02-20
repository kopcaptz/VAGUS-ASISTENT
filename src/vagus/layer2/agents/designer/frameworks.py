"""Framework normalization and CSS descriptors for DesignerAgent."""

from __future__ import annotations

from ...models import CSSFramework

SUPPORTED_FRAMEWORKS = ("tailwind", "bootstrap", "material", "custom")
FRAMEWORK_ALIASES = {
    "pure css": "custom",
    "pure_css": "custom",
    "material design": "material",
}

CSS_SNIPPETS = {
    "tailwind": ".container{max-width:1200px;margin:0 auto;padding:1rem;} .grid{display:grid;gap:1rem;}",
    "bootstrap": ".container{width:100%;max-width:1140px;margin:auto;} .row{display:flex;flex-wrap:wrap;}",
    "material": ".md-surface{box-shadow:0 1px 3px rgba(0,0,0,.2);border-radius:12px;padding:16px;}",
    "custom": ".page{max-width:1200px;margin:0 auto;} .card{border:1px solid #e2e8f0;border-radius:12px;}",
}

CSS_DESCRIPTORS = {
    "tailwind": CSSFramework(
        name="tailwind",
        version="3.x",
        components=["grid", "cards", "buttons", "forms"],
    ),
    "bootstrap": CSSFramework(
        name="bootstrap",
        version="5.x",
        components=["container", "row", "col", "navbar"],
    ),
    "material": CSSFramework(
        name="material",
        version="3",
        components=["surface", "chips", "topbar", "cards"],
    ),
    "custom": CSSFramework(
        name="custom",
        version="1.0",
        components=["layout", "table", "widgets", "buttons"],
    ),
}


def normalize_framework(value: str) -> str:
    """Normalize framework aliases and fallback to tailwind."""
    candidate = (value or "tailwind").strip().lower()
    if candidate in SUPPORTED_FRAMEWORKS:
        return candidate
    return FRAMEWORK_ALIASES.get(candidate, "tailwind")


def get_framework_css(framework: str) -> str:
    """Return CSS baseline snippet for framework."""
    return CSS_SNIPPETS[normalize_framework(framework)]


def get_framework_descriptor(framework: str) -> CSSFramework:
    """Return framework descriptor model."""
    return CSS_DESCRIPTORS[normalize_framework(framework)]

