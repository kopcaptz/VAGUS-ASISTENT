"""Tests for marketplace FastAPI microservice."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from vagus.plugins.marketplace import create_marketplace_app


def _upload_payload(plugin_id: str = "plugin_market") -> dict:
    return {
        "plugin_id": plugin_id,
        "name": "Plugin Market",
        "description": "Plugin from tests",
        "category": "utility",
        "author": "tests",
        "version": "1.0.0",
        "download_url": "https://example.com/plugins/plugin_market-1.0.0.zip",
        "changelog": "Initial release",
        "metadata": {"tags": ["utility"]},
        "rating": 4.5,
        "review": "Great plugin",
    }


def test_marketplace_api_upload_and_get_details(tmp_path: Path):
    app = create_marketplace_app(db_path=tmp_path / "marketplace.db")
    client = TestClient(app)

    upload_resp = client.post("/plugins/upload", json=_upload_payload())
    assert upload_resp.status_code == 201
    assert upload_resp.json()["status"] == "uploaded"

    details_resp = client.get("/plugins/plugin_market")
    assert details_resp.status_code == 200
    details = details_resp.json()
    assert details["plugin_id"] == "plugin_market"
    assert details["review_count"] == 1
    assert details["versions"][0]["version"] == "1.0.0"


def test_marketplace_api_search_and_categories(tmp_path: Path):
    app = create_marketplace_app(db_path=tmp_path / "marketplace.db")
    client = TestClient(app)
    client.post("/plugins/upload", json=_upload_payload("plugin_a"))
    payload = _upload_payload("plugin_b")
    payload["category"] = "productivity"
    client.post("/plugins/upload", json=payload)

    search_resp = client.get("/plugins/search", params={"query": "plugin", "limit": 10})
    assert search_resp.status_code == 200
    assert len(search_resp.json()) >= 2

    category_resp = client.get("/plugins/search", params={"category": "productivity"})
    assert category_resp.status_code == 200
    assert all(item["category"] == "productivity" for item in category_resp.json())

    categories_resp = client.get("/plugins/categories")
    assert categories_resp.status_code == 200
    assert "utility" in categories_resp.json()
    assert "productivity" in categories_resp.json()


def test_marketplace_api_versions_and_download(tmp_path: Path):
    app = create_marketplace_app(db_path=tmp_path / "marketplace.db")
    client = TestClient(app)
    client.post("/plugins/upload", json=_upload_payload())

    v2_payload = _upload_payload()
    v2_payload["version"] = "1.1.0"
    v2_payload["download_url"] = "https://example.com/plugins/plugin_market-1.1.0.zip"
    client.post("/plugins/upload", json=v2_payload)

    versions_resp = client.get("/plugins/plugin_market/versions")
    assert versions_resp.status_code == 200
    versions = versions_resp.json()
    assert any(item["version"] == "1.1.0" for item in versions)

    download_resp = client.get("/plugins/plugin_market/download")
    assert download_resp.status_code == 200
    assert download_resp.json()["version"] == "1.1.0"

    download_v1 = client.get("/plugins/plugin_market/download", params={"version": "1.0.0"})
    assert download_v1.status_code == 200
    assert download_v1.json()["version"] == "1.0.0"


def test_marketplace_api_returns_404_for_missing_plugin(tmp_path: Path):
    app = create_marketplace_app(db_path=tmp_path / "marketplace.db")
    client = TestClient(app)

    assert client.get("/plugins/missing").status_code == 404
    assert client.get("/plugins/missing/versions").status_code == 404
    assert client.get("/plugins/missing/download").status_code == 404


def test_marketplace_api_health_endpoint(tmp_path: Path):
    app = create_marketplace_app(db_path=tmp_path / "marketplace.db")
    client = TestClient(app)
    client.post("/plugins/upload", json=_upload_payload())

    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["plugins"] >= 1


def test_marketplace_api_metrics_endpoint(tmp_path: Path):
    app = create_marketplace_app(db_path=tmp_path / "marketplace.db")
    client = TestClient(app)
    client.post("/plugins/upload", json=_upload_payload())

    response = client.get("/metrics")
    assert response.status_code == 200
    body = response.text
    assert "marketplace_plugins_total" in body
    assert "marketplace_reviews_total" in body
