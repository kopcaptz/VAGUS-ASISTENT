"""Rule-based analyzers for accessibility, color and CSS complexity."""

from __future__ import annotations

import re

from ...models import AccessibilityReport, ColorPalette, Issue


def validate_html_structure(html: str) -> list[Issue]:
    """Validate minimal semantic HTML structure."""
    issues: list[Issue] = []
    content = html or ""
    if "<main" not in content:
        issues.append(
            Issue(
                code="html.main_missing",
                description="Missing <main> landmark.",
                severity="medium",
                element="main",
            )
        )
    if content.count("<h1") > 1:
        issues.append(
            Issue(
                code="html.multiple_h1",
                description="More than one <h1> found.",
                severity="low",
                element="h1",
            )
        )
    img_without_alt = re.findall(r"<img(?![^>]*\balt=)[^>]*>", content, flags=re.IGNORECASE)
    if img_without_alt:
        issues.append(
            Issue(
                code="a11y.img_alt_missing",
                description="Image without alt attribute.",
                severity="high",
                element="img",
            )
        )
    return issues


def accessibility_checklist(html: str) -> list[Issue]:
    """Run accessibility checklist heuristics."""
    issues: list[Issue] = []
    content = html or ""
    if "<html" in content and "lang=" not in content:
        issues.append(
            Issue(
                code="a11y.lang_missing",
                description="Missing lang attribute on <html>.",
                severity="medium",
                element="html",
            )
        )
    if "<button" in content and "aria-label" not in content:
        issues.append(
            Issue(
                code="a11y.button_label",
                description="Buttons may require aria-label for icon-only controls.",
                severity="low",
                element="button",
            )
        )
    ratio = calculate_contrast_ratio("#1F2937", "#FFFFFF")
    if ratio < 4.5:
        issues.append(
            Issue(
                code="a11y.contrast_low",
                description=f"Estimated contrast ratio is low: {ratio:.2f}",
                severity="high",
                element="body",
            )
        )
    return issues


def build_accessibility_report(html: str) -> AccessibilityReport:
    """Build aggregate accessibility report from rule-based checks."""
    issues = validate_html_structure(html)
    issues.extend(accessibility_checklist(html))
    score = max(0.0, round(1.0 - (len(issues) * 0.12), 2))
    recommendations = [
        "Ensure semantic headings hierarchy (h1-h3).",
        "Add alt text to all informative images.",
        "Keep color contrast ratio >= 4.5:1 for body text.",
    ]
    return AccessibilityReport(score=score, issues=issues, recommendations=recommendations)


def estimate_css_complexity(text: str) -> int:
    """Estimate CSS complexity by selectors, pseudo states and nesting."""
    selectors = text.count("{")
    pseudo = text.count(":hover") + text.count(":focus")
    nesting = text.count(">")
    return selectors + pseudo + nesting


def normalize_hex(color: str) -> str:
    """Normalize color to #RRGGBB or fallback."""
    candidate = (color or "").strip().lstrip("#")
    if len(candidate) == 3 and re.fullmatch(r"[0-9A-Fa-f]{3}", candidate):
        candidate = "".join(ch * 2 for ch in candidate)
    if not re.fullmatch(r"[0-9A-Fa-f]{6}", candidate):
        return "#2563EB"
    return f"#{candidate.upper()}"


def hex_to_rgb(color: str) -> tuple[int, int, int]:
    """Convert hex color to RGB."""
    normalized = normalize_hex(color).lstrip("#")
    return (int(normalized[0:2], 16), int(normalized[2:4], 16), int(normalized[4:6], 16))


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    """Convert RGB tuple to hex string."""
    r, g, b = rgb
    return f"#{r:02X}{g:02X}{b:02X}"


def mix_color(base: str, other: str, ratio: float) -> str:
    """Mix base color with other color by ratio [0..1]."""
    ratio = max(0.0, min(1.0, ratio))
    r1, g1, b1 = hex_to_rgb(base)
    r2, g2, b2 = hex_to_rgb(other)
    mixed = (
        int(r1 + (r2 - r1) * ratio),
        int(g1 + (g2 - g1) * ratio),
        int(b1 + (b2 - b1) * ratio),
    )
    return rgb_to_hex(mixed)


def calculate_contrast_ratio(color1: str, color2: str) -> float:
    """Calculate WCAG contrast ratio between two colors."""
    def linear_channel(value: int) -> float:
        srgb = value / 255.0
        return srgb / 12.92 if srgb <= 0.03928 else ((srgb + 0.055) / 1.055) ** 2.4

    r1, g1, b1 = hex_to_rgb(color1)
    r2, g2, b2 = hex_to_rgb(color2)
    l1 = 0.2126 * linear_channel(r1) + 0.7152 * linear_channel(g1) + 0.0722 * linear_channel(b1)
    l2 = 0.2126 * linear_channel(r2) + 0.7152 * linear_channel(g2) + 0.0722 * linear_channel(b2)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def generate_color_palette(base_color: str) -> ColorPalette:
    """Generate primary/secondary/accent/neutrals palette."""
    base = normalize_hex(base_color)
    secondary = mix_color(base, "#111827", 0.25)
    accents = [
        mix_color(base, "#FFFFFF", 0.22),
        mix_color(base, "#000000", 0.18),
        mix_color(base, "#22C55E", 0.18),
    ]
    neutrals = ["#111827", "#374151", "#9CA3AF", "#E5E7EB", "#F9FAFB"]
    return ColorPalette(primary=base, secondary=secondary, accents=accents, neutrals=neutrals)

