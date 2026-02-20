"""Data models for Layer2 specialized agents."""

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class UIAnalysis:
    """Basic UI analysis output."""

    colors: list[str]
    typography: list[str]
    layout: str
    accessibility_score: float


@dataclass(slots=True)
class UILayout:
    """Basic UI layout payload."""

    html: str
    css: str
    js: str
    responsive: bool


@dataclass(slots=True)
class Recommendation:
    """Recommendation for UI improvements."""

    type: str
    description: str
    priority: int


@dataclass(slots=True)
class Issue:
    """Structured design/accessibility issue."""

    code: str
    description: str
    severity: str
    element: str


@dataclass(slots=True)
class AccessibilityReport:
    """Accessibility summary based on rule-based checks."""

    score: float
    issues: list[Issue]
    recommendations: list[str]


@dataclass(slots=True)
class ColorPalette:
    """Generated color palette."""

    primary: str
    secondary: str
    accents: list[str]
    neutrals: list[str]


@dataclass(slots=True)
class CSSFramework:
    """CSS framework descriptor."""

    name: str
    version: str
    components: list[str]


@dataclass(slots=True)
class UITemplate:
    """Rule-based UI template payload."""

    name: str
    framework: str
    html: str
    css: str


@dataclass(slots=True)
class DesignRequest:
    """Input request for hybrid UI generation."""

    style: str
    framework: str
    requirements: dict[str, Any]


@dataclass(slots=True)
class GeneratedUI:
    """Output payload of hybrid UI generation."""

    html: str
    css: str
    js: str
    framework: str
    is_template: bool


__all__ = [
    "AccessibilityReport",
    "CSSFramework",
    "ColorPalette",
    "DesignRequest",
    "GeneratedUI",
    "Issue",
    "Recommendation",
    "UIAnalysis",
    "UILayout",
    "UITemplate",
]
