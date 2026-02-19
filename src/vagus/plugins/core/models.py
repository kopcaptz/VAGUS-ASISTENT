"""Core models for the Vagus plugin system."""

from __future__ import annotations

import inspect
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

try:
    from packaging.specifiers import InvalidSpecifier, SpecifierSet
except Exception:  # pragma: no cover - fallback for very minimal environments
    InvalidSpecifier = ValueError
    SpecifierSet = None  # type: ignore[assignment]


PLUGIN_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")
SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
ENTRY_POINT_PATTERN = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_.]*(?::[A-Za-z_][A-Za-z0-9_]*)?$"
)


class PluginLifecycleState(str, Enum):
    """Runtime lifecycle state of a plugin."""

    LOADED = "LOADED"
    ENABLED = "ENABLED"
    DISABLED = "DISABLED"
    ERROR = "ERROR"


class HookDefinition(BaseModel):
    """Hook declaration in a manifest or runtime registry."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = Field(..., description="Hook name")
    priority: int = Field(default=50, ge=1, le=100, description="Execution priority")
    callback: Union[str, Callable[..., Any]] = Field(..., description="Hook callback")
    is_async: bool = Field(default=False, description="Whether callback is async")

    @field_validator("name")
    @classmethod
    def validate_hook_name(cls, value: str) -> str:
        name = (value or "").strip()
        if not name:
            raise ValueError("Hook name must not be empty")
        return name

    @field_validator("callback")
    @classmethod
    def validate_callback(cls, value: Union[str, Callable[..., Any]]) -> Union[str, Callable[..., Any]]:
        if isinstance(value, str):
            callback_ref = value.strip()
            if not callback_ref:
                raise ValueError("Hook callback reference must not be empty")
            return callback_ref

        if not callable(value):
            raise TypeError("Hook callback must be callable or a callback reference string")

        return value

    @model_validator(mode="after")
    def infer_async_flag(self) -> "HookDefinition":
        if callable(self.callback) and inspect.iscoroutinefunction(self.callback):
            self.is_async = True
        return self


class PluginManifest(BaseModel):
    """Plugin manifest metadata loaded from manifest.json."""

    name: str
    version: str
    author: str
    description: str
    dependencies: list[str] = Field(default_factory=list)
    python_version: str = Field(default=">=3.10")
    vagus_version: str = Field(default=">=0.1.0")
    entry_point: str
    hooks: list[HookDefinition] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        name = (value or "").strip()
        if not PLUGIN_NAME_PATTERN.match(name):
            raise ValueError(
                "Plugin name must start with a letter and contain only letters, digits, '_', '-', '.'"
            )
        return name

    @field_validator("version")
    @classmethod
    def validate_semver(cls, value: str) -> str:
        version = (value or "").strip()
        if not SEMVER_PATTERN.match(version):
            raise ValueError("Plugin version must follow semantic versioning, e.g. 1.0.0")
        return version

    @field_validator("entry_point")
    @classmethod
    def validate_entry_point(cls, value: str) -> str:
        entry_point = (value or "").strip()
        if not ENTRY_POINT_PATTERN.match(entry_point):
            raise ValueError("Entry point must look like 'module.submodule:object_name'")
        return entry_point

    @field_validator("dependencies", "permissions")
    @classmethod
    def normalize_list_values(cls, values: list[str]) -> list[str]:
        normalized = []
        for value in values or []:
            text = str(value).strip()
            if text:
                normalized.append(text)
        return normalized

    @field_validator("python_version", "vagus_version")
    @classmethod
    def validate_version_specifier(cls, value: str) -> str:
        spec = (value or "").strip()
        if not spec:
            raise ValueError("Version specifier must not be empty")

        if SpecifierSet is not None:
            try:
                SpecifierSet(spec)
            except InvalidSpecifier as exc:
                raise ValueError(f"Invalid version specifier: {spec}") from exc

        return spec


class PluginState(BaseModel):
    """Current state and diagnostic metadata of a plugin."""

    state: PluginLifecycleState = Field(default=PluginLifecycleState.DISABLED)
    load_time: Optional[datetime] = None
    last_used: Optional[datetime] = None
    error_message: Optional[str] = None

    @field_validator("error_message")
    @classmethod
    def normalize_error_message(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        text = value.strip()
        return text or None


class PluginConfig(BaseModel):
    """Plugin configuration payload."""

    settings: dict[str, Any] = Field(default_factory=dict)
    secrets: dict[str, Any] = Field(default_factory=dict)
    ui_schema: dict[str, Any] = Field(default_factory=dict)


class LoadedPlugin(BaseModel):
    """Runtime representation of a loaded plugin."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    manifest: PluginManifest
    state: PluginState = Field(
        default_factory=lambda: PluginState(
            state=PluginLifecycleState.LOADED,
            load_time=datetime.now(timezone.utc),
        )
    )
    config: PluginConfig = Field(default_factory=PluginConfig)
    module: Optional[Any] = None
    entry_point: Optional[Any] = None
    source: Optional[str] = None

    @property
    def name(self) -> str:
        """Shortcut for plugin name."""
        return self.manifest.name

    @property
    def hooks(self) -> list[HookDefinition]:
        """Shortcut for manifest hook list."""
        return self.manifest.hooks
