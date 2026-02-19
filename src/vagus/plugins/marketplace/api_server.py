"""FastAPI marketplace microservice for plugin catalog."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PluginUploadRequest(BaseModel):
    """Payload for marketplace plugin upload endpoint."""

    plugin_id: str = Field(..., min_length=2)
    name: str = Field(..., min_length=2)
    description: str = Field(default="")
    category: str = Field(default="general")
    author: str = Field(default="unknown")
    version: str = Field(..., min_length=3)
    download_url: str = Field(..., min_length=3)
    changelog: str = Field(default="")
    metadata: dict[str, Any] = Field(default_factory=dict)
    rating: Optional[float] = Field(default=None, ge=1.0, le=5.0)
    review: Optional[str] = None


class MarketplaceDatabase:
    """Thread-safe SQLite wrapper for marketplace data."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            cursor = self._connection.cursor()
            cursor.executescript(
                """
                CREATE TABLE IF NOT EXISTS plugins (
                    plugin_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    category TEXT NOT NULL,
                    author TEXT NOT NULL,
                    latest_version TEXT NOT NULL,
                    download_url TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS plugin_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plugin_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    changelog TEXT NOT NULL,
                    download_url TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(plugin_id, version)
                );

                CREATE TABLE IF NOT EXISTS plugin_reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plugin_id TEXT NOT NULL,
                    rating REAL NOT NULL,
                    review TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )
            self._connection.commit()

    def upload_plugin(self, payload: PluginUploadRequest) -> dict[str, Any]:
        now = _utc_now_iso()
        with self._lock:
            cursor = self._connection.cursor()
            cursor.execute(
                """
                INSERT INTO plugins (
                    plugin_id, name, description, category, author,
                    latest_version, download_url, metadata_json,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(plugin_id) DO UPDATE SET
                    name = excluded.name,
                    description = excluded.description,
                    category = excluded.category,
                    author = excluded.author,
                    latest_version = excluded.latest_version,
                    download_url = excluded.download_url,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at
                """,
                (
                    payload.plugin_id,
                    payload.name,
                    payload.description,
                    payload.category,
                    payload.author,
                    payload.version,
                    payload.download_url,
                    json.dumps(payload.metadata),
                    now,
                    now,
                ),
            )
            cursor.execute(
                """
                INSERT OR IGNORE INTO plugin_versions (
                    plugin_id, version, changelog, download_url, created_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    payload.plugin_id,
                    payload.version,
                    payload.changelog,
                    payload.download_url,
                    now,
                ),
            )
            if payload.rating is not None:
                cursor.execute(
                    """
                    INSERT INTO plugin_reviews (plugin_id, rating, review, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (payload.plugin_id, payload.rating, payload.review or "", now),
                )
            self._connection.commit()

        return self.get_plugin_details(payload.plugin_id)

    def search_plugins(
        self,
        *,
        query: str = "",
        category: Optional[str] = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        base_query = (
            """
            SELECT
                p.plugin_id,
                p.name,
                p.description,
                p.category,
                p.author,
                p.latest_version,
                p.download_url,
                p.metadata_json,
                COALESCE(AVG(r.rating), 0) AS avg_rating,
                COUNT(r.id) AS review_count
            FROM plugins p
            LEFT JOIN plugin_reviews r ON r.plugin_id = p.plugin_id
            """
        )
        conditions: list[str] = []
        params: list[Any] = []

        if query:
            conditions.append("(p.plugin_id LIKE ? OR p.name LIKE ? OR p.description LIKE ?)")
            like = f"%{query}%"
            params.extend([like, like, like])
        if category:
            conditions.append("p.category = ?")
            params.append(category)

        if conditions:
            base_query += " WHERE " + " AND ".join(conditions)

        base_query += " GROUP BY p.plugin_id ORDER BY avg_rating DESC, p.updated_at DESC LIMIT ?"
        params.append(max(1, int(limit)))

        with self._lock:
            cursor = self._connection.cursor()
            rows = cursor.execute(base_query, params).fetchall()

        return [self._plugin_row_to_payload(row, include_metadata=False) for row in rows]

    def get_plugin_details(self, plugin_id: str) -> dict[str, Any]:
        with self._lock:
            cursor = self._connection.cursor()
            row = cursor.execute(
                """
                SELECT
                    p.plugin_id,
                    p.name,
                    p.description,
                    p.category,
                    p.author,
                    p.latest_version,
                    p.download_url,
                    p.metadata_json,
                    COALESCE(AVG(r.rating), 0) AS avg_rating,
                    COUNT(r.id) AS review_count
                FROM plugins p
                LEFT JOIN plugin_reviews r ON r.plugin_id = p.plugin_id
                WHERE p.plugin_id = ?
                GROUP BY p.plugin_id
                """,
                (plugin_id,),
            ).fetchone()
            if row is None:
                raise KeyError(plugin_id)

            versions = cursor.execute(
                """
                SELECT version, changelog, download_url, created_at
                FROM plugin_versions
                WHERE plugin_id = ?
                ORDER BY created_at DESC
                """,
                (plugin_id,),
            ).fetchall()
            reviews = cursor.execute(
                """
                SELECT rating, review, created_at
                FROM plugin_reviews
                WHERE plugin_id = ?
                ORDER BY created_at DESC
                LIMIT 25
                """,
                (plugin_id,),
            ).fetchall()

        payload = self._plugin_row_to_payload(row, include_metadata=True)
        payload["versions"] = [dict(item) for item in versions]
        payload["reviews"] = [dict(item) for item in reviews]
        return payload

    def get_plugin_versions(self, plugin_id: str) -> list[dict[str, Any]]:
        with self._lock:
            cursor = self._connection.cursor()
            rows = cursor.execute(
                """
                SELECT version, changelog, download_url, created_at
                FROM plugin_versions
                WHERE plugin_id = ?
                ORDER BY created_at DESC
                """,
                (plugin_id,),
            ).fetchall()
        return [dict(item) for item in rows]

    def get_plugin_download(self, plugin_id: str, version: Optional[str] = None) -> dict[str, Any]:
        with self._lock:
            cursor = self._connection.cursor()
            if version:
                row = cursor.execute(
                    """
                    SELECT plugin_id, version, download_url
                    FROM plugin_versions
                    WHERE plugin_id = ? AND version = ?
                    """,
                    (plugin_id, version),
                ).fetchone()
            else:
                row = cursor.execute(
                    """
                    SELECT plugin_id, latest_version AS version, download_url
                    FROM plugins
                    WHERE plugin_id = ?
                    """,
                    (plugin_id,),
                ).fetchone()

        if row is None:
            raise KeyError(f"{plugin_id}:{version}" if version else plugin_id)
        return dict(row)

    def get_categories(self) -> list[str]:
        with self._lock:
            cursor = self._connection.cursor()
            rows = cursor.execute(
                "SELECT DISTINCT category FROM plugins ORDER BY category ASC"
            ).fetchall()
        return [str(row["category"]) for row in rows]

    def _plugin_row_to_payload(self, row: sqlite3.Row, *, include_metadata: bool) -> dict[str, Any]:
        payload = {
            "plugin_id": row["plugin_id"],
            "name": row["name"],
            "description": row["description"],
            "category": row["category"],
            "author": row["author"],
            "latest_version": row["latest_version"],
            "download_url": row["download_url"],
            "avg_rating": float(row["avg_rating"] or 0.0),
            "review_count": int(row["review_count"] or 0),
        }
        if include_metadata:
            payload["metadata"] = json.loads(row["metadata_json"] or "{}")
        return payload


def create_marketplace_app(db_path: str | Path = ":memory:") -> FastAPI:
    """Create FastAPI app instance for plugin marketplace."""
    app = FastAPI(title="Vagus Plugin Marketplace", version="0.1.0")
    database = MarketplaceDatabase(db_path=db_path)

    @app.get("/plugins/search")
    def search_plugins(
        query: str = Query(default=""),
        category: Optional[str] = Query(default=None),
        limit: int = Query(default=20, ge=1, le=100),
    ) -> list[dict[str, Any]]:
        return database.search_plugins(query=query, category=category, limit=limit)

    @app.get("/plugins/categories")
    def get_categories() -> list[str]:
        return database.get_categories()

    @app.get("/plugins/{plugin_id}")
    def get_plugin_details(plugin_id: str) -> dict[str, Any]:
        try:
            return database.get_plugin_details(plugin_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found") from exc

    @app.get("/plugins/{plugin_id}/versions")
    def get_plugin_versions(plugin_id: str) -> list[dict[str, Any]]:
        versions = database.get_plugin_versions(plugin_id)
        if not versions:
            raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
        return versions

    @app.get("/plugins/{plugin_id}/download")
    def download_plugin(plugin_id: str, version: Optional[str] = Query(default=None)) -> dict[str, Any]:
        try:
            return database.get_plugin_download(plugin_id, version=version)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found") from exc

    @app.post("/plugins/upload", status_code=201)
    def upload_plugin(payload: PluginUploadRequest) -> dict[str, Any]:
        plugin = database.upload_plugin(payload)
        return {"status": "uploaded", "plugin": plugin}

    app.state.marketplace_db = database
    return app


__all__ = ["PluginUploadRequest", "MarketplaceDatabase", "create_marketplace_app"]
