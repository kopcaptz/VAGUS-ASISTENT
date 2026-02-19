"""Core models for the Vagus plugin system."""

from __future__ import annotations

import inspect
import os
import re
from pathlib import Path
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


class PermissionLevel(str, Enum):
    """Permission level for runtime plugin operations."""

    NONE = "NONE"
    READ = "READ"
    WRITE = "WRITE"
    NETWORK = "NETWORK"
    SYSTEM = "SYSTEM"


class FilesystemPermissions(BaseModel):
    """Filesystem access policy for plugin."""

    read: list[str] = Field(default_factory=list)
    write: list[str] = Field(default_factory=list)

    @field_validator("read", "write")
    @classmethod
    def normalize_paths(cls, paths: list[str]) -> list[str]:
        normalized: list[str] = []
        for path in paths or []:
            text = str(path).strip()
            if not text:
                continue
            normalized.append(os.path.normpath(os.path.expanduser(text)))
        return normalized


class PluginPermissions(BaseModel):
    """Runtime security limits and allow-lists for plugin sandbox."""

    level: PermissionLevel = PermissionLevel.NONE
    filesystem: FilesystemPermissions = Field(default_factory=FilesystemPermissions)
    network: list[str] = Field(default_factory=list)
    environment_variables: list[str] = Field(default_factory=list)
    max_memory_mb: int = Field(default=512, ge=16, le=16384)
    max_execution_time_seconds: int = Field(default=30, ge=1, le=3600)

    @field_validator("filesystem", mode="before")
    @classmethod
    def normalize_filesystem_input(cls, value: Any) -> Any:
        if value is None:
            return FilesystemPermissions()
        if isinstance(value, list):
            return {"read": value, "write": []}
        return value

    @field_validator("network", "environment_variables")
    @classmethod
    def normalize_string_lists(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values or []:
            text = str(value).strip()
            if text:
                normalized.append(text)
        return normalized

    def can_read_path(self, path: str | Path) -> bool:
        if self.level == PermissionLevel.SYSTEM:
            return True
        if self.level not in {PermissionLevel.READ, PermissionLevel.WRITE, PermissionLevel.NETWORK}:
            return False
        return self._is_path_allowed(path, self.filesystem.read + self.filesystem.write)

    def can_write_path(self, path: str | Path) -> bool:
        if self.level == PermissionLevel.SYSTEM:
            return True
        if self.level not in {PermissionLevel.WRITE, PermissionLevel.NETWORK}:
            return False
        return self._is_path_allowed(path, self.filesystem.write)

    def can_access_domain(self, domain: str) -> bool:
        if self.level == PermissionLevel.SYSTEM:
            return True
        if self.level != PermissionLevel.NETWORK:
            return False
        host = (domain or "").strip().lower()
        if not host:
            return False
        for allowed_domain in self.network:
            allowed = allowed_domain.lower()
            if host == allowed or host.endswith(f".{allowed}"):
                return True
        return False

    def can_access_env_var(self, env_var_name: str) -> bool:
        if self.level == PermissionLevel.SYSTEM:
            return True
        if self.level == PermissionLevel.NONE:
            return False
        return env_var_name in self.environment_variables

    @staticmethod
    def _is_path_allowed(candidate_path: str | Path, allowed_paths: list[str]) -> bool:
        if not allowed_paths:
            return False

        candidate = Path(candidate_path).expanduser().resolve()
        for allowed_raw in allowed_paths:
            allowed = Path(allowed_raw).expanduser().resolve()
            if candidate == allowed:
                return True
            if candidate.is_relative_to(allowed):
                return True
        return False


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
    runtime_permissions: PluginPermissions = Field(default_factory=PluginPermissions)
    signature_key_id: Optional[str] = None
    signature_algorithm: Optional[str] = None

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

    @model_validator(mode="before")
    @classmethod
    def normalize_permissions_payload(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        permissions_value = data.get("permissions")
        if isinstance(permissions_value, dict) and "runtime_permissions" not in data:
            data = dict(data)
            data["runtime_permissions"] = permissions_value
            data["permissions"] = []

        return data


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
