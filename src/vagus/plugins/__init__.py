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
from .hot_reload import HotReloadConfig, HotReloadManager, WATCHDOG_AVAILABLE
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
from .marketplace import MarketplaceClient, create_marketplace_app
from .monitoring import PluginHealthStatus, PluginMonitor, PluginRuntimeMetrics
from .analytics import PluginAnalytics, PluginUsageMetrics
from .dependencies import (
    DependencyEdge,
    PluginDependencyNode,
    PluginDependencyResolver,
)
from .tools import PluginTemplateError, PluginTemplateGenerator, create_plugin_template
from .backup import PluginBackupError, PluginBackupManager
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
    "HotReloadManager",
    "HotReloadConfig",
    "WATCHDOG_AVAILABLE",
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
    "PluginAnalytics",
    "PluginUsageMetrics",
    "PluginDependencyResolver",
    "PluginDependencyNode",
    "DependencyEdge",
    "PluginTemplateGenerator",
    "PluginTemplateError",
    "create_plugin_template",
    "PluginBackupManager",
    "PluginBackupError",
    "MarketplaceClient",
    "create_marketplace_app",
]
