"""Vagus plugin system package."""

from .core import (
    HookDefinition,
    LoadedPlugin,
    PluginConfig,
    PluginLifecycleState,
    PluginManifest,
    PluginState,
)
from .hooks import HookSystem, SUPPORTED_HOOKS
from .loader import (
    DependencyResolutionError,
    EntryPointImportError,
    GitLoader,
    LocalLoader,
    ManifestValidationError,
    PluginLoaderError,
    PyPILoader,
)
from .marketplace import MarketplaceClient
from .registry import PluginRegistry
from .sandbox import SandboxExecutionError, SandboxExecutor, SandboxLimits

__all__ = [
    "PluginManifest",
    "PluginState",
    "PluginLifecycleState",
    "HookDefinition",
    "PluginConfig",
    "LoadedPlugin",
    "PluginRegistry",
    "PluginLoaderError",
    "ManifestValidationError",
    "DependencyResolutionError",
    "EntryPointImportError",
    "LocalLoader",
    "GitLoader",
    "PyPILoader",
    "HookSystem",
    "SUPPORTED_HOOKS",
    "SandboxLimits",
    "SandboxExecutionError",
    "SandboxExecutor",
    "MarketplaceClient",
]
