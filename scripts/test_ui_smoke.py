"""Basic Dashboard UI smoke test with Playwright."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field


@dataclass
class CheckResult:
    name: str
    ok: bool
    details: str = ""


@dataclass
class SmokeReport:
    base_url: str
    checks: list[CheckResult] = field(default_factory=list)

    def add(self, name: str, ok: bool, details: str = "") -> None:
        self.checks.append(CheckResult(name=name, ok=ok, details=details))

    @property
    def ok(self) -> bool:
        return all(item.ok for item in self.checks)

    def to_json(self) -> str:
        return json.dumps(
            {
                "base_url": self.base_url,
                "ok": self.ok,
                "checks": [asdict(item) for item in self.checks],
            },
            ensure_ascii=False,
            indent=2,
        )


def _safe_click(page, selector: str) -> bool:
    locator = page.locator(selector)
    if locator.count() < 1:
        return False
    locator.first.click(timeout=5000)
    return True


def main() -> int:
    base_url = "http://127.0.0.1:8501"
    report = SmokeReport(base_url=base_url)

    try:
        from playwright.sync_api import TimeoutError as PWTimeout
        from playwright.sync_api import sync_playwright
    except Exception:
        report.add("playwright_import", False, "Install dependency: pip install playwright")
        print(report.to_json())
        return 1

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(base_url, wait_until="domcontentloaded", timeout=30000)
            report.add("dashboard_loads", True)
        except PWTimeout:
            report.add("dashboard_loads", False, "Timeout opening dashboard")
            print(report.to_json())
            browser.close()
            return 1

        # Login (best-effort, Streamlit DOM can differ by version/theme).
        try:
            inputs = page.locator("input")
            input_count = inputs.count()
            if input_count >= 2:
                inputs.nth(0).fill("admin")
                inputs.nth(1).fill("admin")
                clicked = (
                    _safe_click(page, "button:has-text('Войти')")
                    or _safe_click(page, "button:has-text('Login')")
                    or _safe_click(page, "button[kind='primary']")
                )
                report.add("login_submit", clicked, "Clicked login button" if clicked else "No login button found")
            else:
                report.add("login_submit", False, "Login inputs were not found")
        except Exception as exc:
            report.add("login_submit", False, f"{type(exc).__name__}: {exc}")

        # Navigate to plugins page.
        try:
            clicked_plugins = (
                _safe_click(page, "a:has-text('Plugins')")
                or _safe_click(page, "button:has-text('Plugins')")
                or _safe_click(page, "[data-testid='stSidebarNav'] a:has-text('Plugins')")
            )
            report.add("plugins_page_navigation", clicked_plugins, "Navigated" if clicked_plugins else "Plugins item not found")
        except Exception as exc:
            report.add("plugins_page_navigation", False, f"{type(exc).__name__}: {exc}")

        # Core tabs (best-effort, does not fail entire run if UI labels differ).
        tab_names = ["Installed", "Marketplace", "Trending", "Hot Reload"]
        for tab_name in tab_names:
            found = page.get_by_text(tab_name, exact=False).count() > 0
            report.add(f"tab_{tab_name.lower().replace(' ', '_')}", found, "" if found else "Tab label not visible")

        browser.close()

    print(report.to_json())
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
