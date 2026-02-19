"""Vagus plugin system package."""

from .core import (
    FilesystemPermissions,
    HookDefinition,
    LoadedPlugin,
    PermissionLevel,
    PluginConfig,
    PluginLifecycleState,
    PluginManifest,
    PluginPermissions,
    PluginState,
)
from .hooks import HookSystem, SUPPORTED_HOOKS
from .loader import (
    DependencyVettingError,
    DependencyResolutionError,
    EntryPointImportError,
    GitLoader,
    LocalLoader,
    ManifestValidationError,
    PluginLoaderError,
    PyPILoader,
    SecurePluginLoader,
    SecurityScanError,
    SignatureValidationError,
)
from .marketplace import MarketplaceClient
from .monitoring import PluginHealthStatus, PluginMonitor, PluginRuntimeMetrics
from .registry import PluginRegistry
from .sandbox import (
    SandboxEngine,
    SandboxExecutionError,
    SandboxExecutor,
    SandboxLimits,
    SandboxPolicy,
    SecurityAuditEvent,
    SecurityManager,
    SecurityViolationError,
)
from .security import PluginSignatureVerifier, SignatureError, TrustStore

__all__ = [
    "PluginManifest",
    "PluginState",
    "PluginLifecycleState",
    "HookDefinition",
    "PluginConfig",
    "PluginPermissions",
    "PermissionLevel",
    "FilesystemPermissions",
    "LoadedPlugin",
    "PluginRegistry",
    "PluginLoaderError",
    "ManifestValidationError",
    "DependencyResolutionError",
    "EntryPointImportError",
    "SecurityScanError",
    "DependencyVettingError",
    "SignatureValidationError",
    "LocalLoader",
    "GitLoader",
    "PyPILoader",
    "SecurePluginLoader",
    "HookSystem",
    "SUPPORTED_HOOKS",
    "SandboxLimits",
    "SandboxExecutionError",
    "SandboxExecutor",
    "SandboxEngine",
    "SandboxPolicy",
    "SecurityManager",
    "SecurityViolationError",
    "SecurityAuditEvent",
    "PluginSignatureVerifier",
    "TrustStore",
    "SignatureError",
    "PluginMonitor",
    "PluginRuntimeMetrics",
    "PluginHealthStatus",
    "MarketplaceClient",
]
