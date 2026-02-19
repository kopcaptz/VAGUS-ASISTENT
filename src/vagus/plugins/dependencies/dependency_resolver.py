"""Plugin dependency resolver with semver-aware conflict detection."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Callable, Optional

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version


class DependencyResolutionError(RuntimeError):
    """Raised when dependency graph cannot be resolved."""


@dataclass
class DependencyEdge:
    """Dependency edge declaration."""

    plugin_name: str
    version_spec: str = ""


@dataclass
class PluginDependencyNode:
    """Plugin node and its declared dependencies."""

    name: str
    version: str
    dependencies: list[DependencyEdge] = field(default_factory=list)


class PluginDependencyResolver:
    """Resolves plugin dependency order and detects version conflicts."""

    DEP_PATTERN = re.compile(r"^([A-Za-z][A-Za-z0-9_.-]*)(.*)$")

    def __init__(self) -> None:
        self._nodes: dict[str, PluginDependencyNode] = {}

    def add_plugin(self, name: str, version: str, dependencies: list[str] | None = None) -> None:
        dep_edges = [self.parse_dependency(dep) for dep in (dependencies or [])]
        self._nodes[name] = PluginDependencyNode(name=name, version=version, dependencies=dep_edges)

    def parse_dependency(self, dependency: str) -> DependencyEdge:
        text = dependency.strip()
        if not text:
            raise DependencyResolutionError("Dependency string must not be empty")

        match = self.DEP_PATTERN.match(text)
        if not match:
            raise DependencyResolutionError(f"Invalid dependency string: {dependency}")

        plugin_name = match.group(1)
        version_spec = (match.group(2) or "").strip()
        if version_spec:
            try:
                SpecifierSet(version_spec)
            except InvalidSpecifier as exc:
                raise DependencyResolutionError(
                    f"Invalid dependency specifier '{version_spec}' in '{dependency}'"
                ) from exc
        return DependencyEdge(plugin_name=plugin_name, version_spec=version_spec)

    def resolve(self, targets: list[str]) -> list[str]:
        """Resolve dependency-aware install/load order."""
        ordered: list[str] = []
        temporary: set[str] = set()
        permanent: set[str] = set()

        def visit(plugin_name: str) -> None:
            if plugin_name in permanent:
                return
            if plugin_name in temporary:
                raise DependencyResolutionError(f"Cyclic dependency detected at '{plugin_name}'")
            if plugin_name not in self._nodes:
                raise DependencyResolutionError(f"Missing dependency '{plugin_name}'")

            temporary.add(plugin_name)
            node = self._nodes[plugin_name]
            for dep in node.dependencies:
                self._assert_dependency_version(node.name, dep)
                visit(dep.plugin_name)
            temporary.remove(plugin_name)
            permanent.add(plugin_name)
            ordered.append(plugin_name)

        for target in targets:
            visit(target)

        return ordered

    def detect_conflicts(self) -> dict[str, list[str]]:
        """Detect incompatible dependency requirements for each plugin."""
        requirements: dict[str, list[str]] = {}
        for node in self._nodes.values():
            for dep in node.dependencies:
                if dep.version_spec:
                    requirements.setdefault(dep.plugin_name, []).append(dep.version_spec)

        conflicts: dict[str, list[str]] = {}
        for plugin_name, specs in requirements.items():
            node = self._nodes.get(plugin_name)
            if node is None:
                conflicts[plugin_name] = specs + ["missing"]
                continue

            if not self._version_satisfies_all(node.version, specs):
                conflicts[plugin_name] = specs

        return conflicts

    def install_missing(
        self,
        targets: list[str],
        installer: Callable[[str, str], str],
    ) -> list[str]:
        """Install missing dependencies using installer callback."""
        installed: list[str] = []
        required = self._collect_required_plugins(targets)
        for plugin_name, spec in required.items():
            if plugin_name in self._nodes:
                continue
            resolved_version = installer(plugin_name, spec)
            self.add_plugin(plugin_name, version=resolved_version, dependencies=[])
            installed.append(plugin_name)
        return installed

    def dependency_graph(self) -> dict[str, list[str]]:
        return {
            node.name: [dep.plugin_name for dep in node.dependencies]
            for node in self._nodes.values()
        }

    def visualize_graph(self) -> str:
        """Return dependency graph in DOT format."""
        lines = ["digraph plugin_dependencies {"]
        for node_name, deps in self.dependency_graph().items():
            if not deps:
                lines.append(f'  "{node_name}";')
                continue
            for dep in deps:
                lines.append(f'  "{node_name}" -> "{dep}";')
        lines.append("}")
        return "\n".join(lines)

    def _assert_dependency_version(self, owner: str, dependency: DependencyEdge) -> None:
        dependency_node = self._nodes.get(dependency.plugin_name)
        if dependency_node is None:
            return
        if not dependency.version_spec:
            return
        if not self._version_satisfies(dependency_node.version, dependency.version_spec):
            raise DependencyResolutionError(
                f"Plugin '{owner}' requires '{dependency.plugin_name}{dependency.version_spec}', "
                f"but resolved version is {dependency_node.version}"
            )

    def _collect_required_plugins(self, targets: list[str]) -> dict[str, str]:
        required: dict[str, str] = {}
        visited: set[str] = set()

        def walk(plugin_name: str) -> None:
            if plugin_name in visited:
                return
            visited.add(plugin_name)
            node = self._nodes.get(plugin_name)
            if node is None:
                return
            for dep in node.dependencies:
                if dep.plugin_name not in self._nodes:
                    required.setdefault(dep.plugin_name, dep.version_spec)
                walk(dep.plugin_name)

        for name in targets:
            walk(name)
        return required

    def _version_satisfies(self, version: str, specifier: str) -> bool:
        try:
            parsed = Version(version)
        except InvalidVersion as exc:
            raise DependencyResolutionError(f"Invalid version '{version}'") from exc
        return parsed in SpecifierSet(specifier)

    def _version_satisfies_all(self, version: str, specifiers: list[str]) -> bool:
        return all(self._version_satisfies(version, spec) for spec in specifiers if spec)
