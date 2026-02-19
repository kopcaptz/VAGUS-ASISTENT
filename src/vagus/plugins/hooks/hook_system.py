"""Hook system for extending Vagus runtime behavior."""

from __future__ import annotations

import inspect
import threading
from typing import Any, Callable, Optional

from ..core.models import HookDefinition

SUPPORTED_HOOKS = {
    "pre_task_execution",
    "post_task_execution",
    "on_error",
    "on_message_received",
    "on_config_changed",
}


class HookSystem:
    """Priority-based hook execution with async/sync callback support."""

    def __init__(self) -> None:
        self._hooks: dict[str, list[HookDefinition]] = {name: [] for name in SUPPORTED_HOOKS}
        self._lock = threading.RLock()

    def register_hook(
        self,
        hook_name: str,
        callback: Callable[..., Any],
        priority: int = 50,
        is_async: Optional[bool] = None,
    ) -> HookDefinition:
        """Register a runtime hook callback."""
        self._ensure_supported_hook(hook_name)
        resolved_async = bool(is_async) if is_async is not None else inspect.iscoroutinefunction(callback)
        definition = HookDefinition(
            name=hook_name,
            priority=priority,
            callback=callback,
            is_async=resolved_async,
        )
        self._add_definition(definition)
        return definition

    def register_definition(self, definition: HookDefinition) -> HookDefinition:
        """Register a pre-validated HookDefinition object."""
        self._ensure_supported_hook(definition.name)
        self._add_definition(definition)
        return definition

    def register_manifest_hooks(self, plugin_object: Any, hooks: list[HookDefinition]) -> None:
        """Bind manifest hook definitions to callbacks from plugin object/module."""
        for hook in hooks:
            callback = self._resolve_callback(plugin_object, hook.callback)
            self.register_hook(
                hook_name=hook.name,
                callback=callback,
                priority=hook.priority,
                is_async=hook.is_async,
            )

    def unregister_hook(self, hook_name: str, callback: Callable[..., Any]) -> bool:
        """Unregister specific callback from hook chain."""
        self._ensure_supported_hook(hook_name)
        with self._lock:
            hooks = self._hooks[hook_name]
            for index, definition in enumerate(hooks):
                if definition.callback == callback:
                    hooks.pop(index)
                    return True
        return False

    def get_hooks(self, hook_name: str) -> list[HookDefinition]:
        """Return hook definitions for hook name sorted by priority."""
        self._ensure_supported_hook(hook_name)
        with self._lock:
            return list(self._hooks[hook_name])

    def clear(self) -> None:
        """Reset all hook registrations."""
        with self._lock:
            for hook_name in SUPPORTED_HOOKS:
                self._hooks[hook_name].clear()

    async def pre_task_execution(self, task: Any) -> Any:
        """Run hooks before task execution; hooks may modify task payload."""
        current_task = task
        for hook in self.get_hooks("pre_task_execution"):
            result = await self._invoke_hook(hook, current_task)
            if result is not None:
                current_task = result
        return current_task

    async def post_task_execution(self, task: Any, result: Any) -> Any:
        """Run hooks after task execution; hooks may transform result."""
        current_result = result
        for hook in self.get_hooks("post_task_execution"):
            updated_result = await self._invoke_hook(hook, task, current_result)
            if updated_result is not None:
                current_result = updated_result
        return current_result

    async def on_error(self, task: Any, error: Exception) -> None:
        """Run error hooks."""
        for hook in self.get_hooks("on_error"):
            await self._invoke_hook(hook, task, error)

    async def on_message_received(self, message: Any) -> Any:
        """Run message hooks; hooks may modify incoming message."""
        current_message = message
        for hook in self.get_hooks("on_message_received"):
            updated_message = await self._invoke_hook(hook, current_message)
            if updated_message is not None:
                current_message = updated_message
        return current_message

    async def on_config_changed(self, config: Any) -> Any:
        """Run config change hooks; hooks may return patched config."""
        current_config = config
        for hook in self.get_hooks("on_config_changed"):
            updated_config = await self._invoke_hook(hook, current_config)
            if updated_config is not None:
                current_config = updated_config
        return current_config

    def _add_definition(self, definition: HookDefinition) -> None:
        with self._lock:
            bucket = self._hooks[definition.name]
            bucket.append(definition)
            bucket.sort(key=lambda item: item.priority, reverse=True)

    async def _invoke_hook(self, definition: HookDefinition, *args: Any) -> Any:
        callback = definition.callback
        if isinstance(callback, str):
            raise TypeError(
                f"Hook '{definition.name}' callback must be bound to a callable, got '{callback}'"
            )

        if definition.is_async or inspect.iscoroutinefunction(callback):
            return await callback(*args)

        result = callback(*args)
        if inspect.isawaitable(result):
            return await result
        return result

    def _resolve_callback(
        self,
        plugin_object: Any,
        callback: str | Callable[..., Any],
    ) -> Callable[..., Any]:
        if callable(callback):
            return callback

        callback_name = callback.rsplit(".", maxsplit=1)[-1]
        if hasattr(plugin_object, callback_name):
            resolved = getattr(plugin_object, callback_name)
            if callable(resolved):
                return resolved

        raise AttributeError(f"Cannot resolve callback '{callback}' from plugin object")

    @staticmethod
    def _ensure_supported_hook(hook_name: str) -> None:
        if hook_name not in SUPPORTED_HOOKS:
            raise ValueError(
                f"Unsupported hook '{hook_name}'. Allowed hooks: {sorted(SUPPORTED_HOOKS)}"
            )
