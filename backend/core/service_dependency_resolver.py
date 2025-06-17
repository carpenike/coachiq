"""
Enhanced Service Dependency Resolution for ServiceRegistry

This module provides advanced dependency resolution capabilities including:
- Circular dependency detection with detailed error messages
- Dependency visualization and reporting
- Stage optimization based on actual dependencies
- Runtime dependency validation
- Dependency-aware error propagation

Part of Phase 2F: Service Dependency Resolution Enhancement
"""

import logging
from collections import defaultdict, deque
from dataclasses import dataclass
from enum import Enum
from graphlib import CycleError, TopologicalSorter
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class DependencyError(Exception):
    """Raised when dependency resolution fails."""
    pass


class DependencyType(Enum):
    """Types of service dependencies."""
    REQUIRED = "required"  # Service cannot start without this dependency
    OPTIONAL = "optional"  # Service can start but with reduced functionality
    RUNTIME = "runtime"    # Dependency needed only after startup


@dataclass
class ServiceDependency:
    """Enhanced dependency information."""
    name: str
    type: DependencyType = DependencyType.REQUIRED
    version: Optional[str] = None
    fallback: Optional[str] = None  # Alternative service if primary unavailable


@dataclass
class DependencyNode:
    """Node in the dependency graph."""
    name: str
    dependencies: List[ServiceDependency]
    dependents: Set[str]  # Services that depend on this one
    stage: Optional[int] = None
    depth: int = 0  # Distance from root nodes


class ServiceDependencyResolver:
    """
    Advanced dependency resolver for ServiceRegistry.

    Provides comprehensive dependency analysis, circular dependency detection,
    and optimized stage calculation for parallel startup.
    """

    def __init__(self):
        self._nodes: Dict[str, DependencyNode] = {}
        self._dependency_graph: Dict[str, Set[str]] = defaultdict(set)
        self._reverse_graph: Dict[str, Set[str]] = defaultdict(set)
        self._stages: Dict[int, List[str]] = {}
        self._circular_paths: List[List[str]] = []

    def add_service(
        self,
        name: str,
        dependencies: List[ServiceDependency]
    ) -> None:
        """
        Add a service with its dependencies.

        Args:
            name: Service name
            dependencies: List of service dependencies
        """
        node = DependencyNode(
            name=name,
            dependencies=dependencies,
            dependents=set()
        )
        self._nodes[name] = node

        # Build dependency graphs
        for dep in dependencies:
            if dep.type == DependencyType.REQUIRED:
                self._dependency_graph[name].add(dep.name)
                self._reverse_graph[dep.name].add(name)

    def resolve_dependencies(self) -> Dict[int, List[str]]:
        """
        Resolve all dependencies and calculate optimal startup stages.

        Returns:
            Dictionary mapping stage numbers to service names

        Raises:
            DependencyError: If circular dependencies detected or missing dependencies
        """
        # Validate all dependencies exist
        self._validate_dependencies()

        # Detect circular dependencies
        self._detect_circular_dependencies()

        # Calculate stages using topological sort
        self._calculate_stages()

        # Optimize stages for maximum parallelization
        self._optimize_stages()

        return self._stages

    def _validate_dependencies(self) -> None:
        """Validate that all dependencies are defined."""
        all_services = set(self._nodes.keys())

        for service_name, node in self._nodes.items():
            for dep in node.dependencies:
                if dep.type == DependencyType.REQUIRED and dep.name not in all_services:
                    # Check if fallback is available
                    if dep.fallback and dep.fallback in all_services:
                        logger.warning(
                            f"Service '{service_name}' primary dependency '{dep.name}' "
                            f"not found, using fallback '{dep.fallback}'"
                        )
                        # Update dependency graph with fallback
                        self._dependency_graph[service_name].remove(dep.name)
                        self._dependency_graph[service_name].add(dep.fallback)
                        self._reverse_graph[dep.name].discard(service_name)
                        self._reverse_graph[dep.fallback].add(service_name)
                    else:
                        missing_deps = []
                        for d in node.dependencies:
                            if d.type == DependencyType.REQUIRED and d.name not in all_services:
                                missing_deps.append(d.name)

                        raise DependencyError(
                            f"Service '{service_name}' has missing required dependencies: "
                            f"{', '.join(missing_deps)}. Available services: "
                            f"{', '.join(sorted(all_services))}"
                        )

    def _detect_circular_dependencies(self) -> None:
        """Detect circular dependencies using DFS."""
        visited = set()
        rec_stack = set()

        def dfs(node: str, path: List[str]) -> bool:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in self._dependency_graph.get(node, []):
                if neighbor not in visited:
                    if dfs(neighbor, path.copy()):
                        return True
                elif neighbor in rec_stack:
                    # Found cycle
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    self._circular_paths.append(cycle)
                    return True

            path.pop()
            rec_stack.remove(node)
            return False

        for node in self._nodes:
            if node not in visited:
                if dfs(node, []):
                    # Format circular dependency error
                    cycles_str = []
                    for cycle in self._circular_paths:
                        cycles_str.append(" → ".join(cycle))

                    raise DependencyError(
                        f"Circular dependencies detected:\n" +
                        "\n".join(f"  • {cycle}" for cycle in cycles_str)
                    )

    def _calculate_stages(self) -> None:
        """Calculate startup stages using topological sort."""
        try:
            sorter = TopologicalSorter(self._dependency_graph)
            sorter.prepare()

            stage = 0
            while sorter.is_active():
                ready = list(sorter.get_ready())
                if ready:
                    self._stages[stage] = ready
                    for service in ready:
                        if service in self._nodes:
                            self._nodes[service].stage = stage
                    sorter.done(*ready)
                    stage += 1

        except CycleError as e:
            # This shouldn't happen as we detect cycles earlier
            raise DependencyError(f"Unexpected circular dependency: {e}")

    def _optimize_stages(self) -> None:
        """
        Optimize stages to maximize parallelization.

        Services can potentially start earlier if all their dependencies
        are satisfied in earlier stages.
        """
        # Calculate depth (distance from root) for each node
        self._calculate_depths()

        # Reassign stages based on actual dependency satisfaction
        optimized_stages = defaultdict(list)

        for service_name, node in self._nodes.items():
            # Find the maximum stage of all dependencies
            max_dep_stage = -1
            for dep in node.dependencies:
                if dep.type == DependencyType.REQUIRED and dep.name in self._nodes:
                    dep_stage = self._nodes[dep.name].stage
                    if dep_stage is not None:
                        max_dep_stage = max(max_dep_stage, dep_stage)

            # Service can start in the next stage after its dependencies
            optimal_stage = max_dep_stage + 1
            optimized_stages[optimal_stage].append(service_name)
            node.stage = optimal_stage

        # Convert to regular dict
        self._stages = dict(optimized_stages)

    def _calculate_depths(self) -> None:
        """Calculate depth of each node from root nodes."""
        # Find root nodes (no dependencies)
        roots = [
            name for name, deps in self._dependency_graph.items()
            if not deps
        ]

        # Add nodes with no entry in dependency graph (isolated nodes)
        for name in self._nodes:
            if name not in self._dependency_graph:
                roots.append(name)

        # BFS to calculate depths
        queue = deque([(root, 0) for root in roots])
        visited = set()

        while queue:
            node, depth = queue.popleft()
            if node in visited:
                continue

            visited.add(node)
            if node in self._nodes:
                self._nodes[node].depth = depth

            # Add dependents to queue
            for dependent in self._reverse_graph.get(node, []):
                if dependent not in visited:
                    queue.append((dependent, depth + 1))

    def get_dependency_report(self) -> str:
        """
        Generate a human-readable dependency report.

        Returns:
            Formatted dependency report string
        """
        lines = ["Service Dependency Report", "=" * 50]

        # Stage summary
        lines.append(f"\nStartup Stages ({len(self._stages)} total):")
        for stage_num in sorted(self._stages.keys()):
            services = self._stages[stage_num]
            lines.append(f"  Stage {stage_num}: {', '.join(sorted(services))}")

        # Service details
        lines.append("\nService Dependencies:")
        for name in sorted(self._nodes.keys()):
            node = self._nodes[name]
            lines.append(f"\n  {name}:")
            lines.append(f"    Stage: {node.stage}")
            lines.append(f"    Depth: {node.depth}")

            if node.dependencies:
                lines.append("    Dependencies:")
                for dep in node.dependencies:
                    dep_info = f"      - {dep.name} ({dep.type.value})"
                    if dep.fallback:
                        dep_info += f" [fallback: {dep.fallback}]"
                    lines.append(dep_info)
            else:
                lines.append("    Dependencies: None")

            if node.dependents:
                lines.append(f"    Dependents: {', '.join(sorted(node.dependents))}")

        # Parallelization opportunities
        lines.append("\nParallelization Analysis:")
        for stage_num in sorted(self._stages.keys()):
            services = self._stages[stage_num]
            if len(services) > 1:
                lines.append(
                    f"  Stage {stage_num}: {len(services)} services can start in parallel"
                )

        return "\n".join(lines)

    def get_startup_order(self) -> List[str]:
        """
        Get flat list of services in startup order.

        Returns:
            List of service names in order they should be started
        """
        order = []
        for stage_num in sorted(self._stages.keys()):
            order.extend(sorted(self._stages[stage_num]))
        return order

    def validate_runtime_dependencies(
        self,
        available_services: Set[str]
    ) -> Dict[str, List[str]]:
        """
        Validate runtime dependencies are satisfied.

        Args:
            available_services: Set of currently available service names

        Returns:
            Dictionary of service names to missing dependencies
        """
        missing = {}

        for service_name, node in self._nodes.items():
            if service_name not in available_services:
                continue

            missing_deps = []
            for dep in node.dependencies:
                if dep.type == DependencyType.RUNTIME and dep.name not in available_services:
                    if not dep.fallback or dep.fallback not in available_services:
                        missing_deps.append(dep.name)

            if missing_deps:
                missing[service_name] = missing_deps

        return missing

    def get_impacted_services(self, failed_service: str) -> Set[str]:
        """
        Get all services impacted by a service failure.

        Args:
            failed_service: Name of the failed service

        Returns:
            Set of service names that depend on the failed service
        """
        impacted = set()

        def traverse_dependents(service: str):
            for dependent in self._reverse_graph.get(service, []):
                if dependent not in impacted:
                    impacted.add(dependent)
                    traverse_dependents(dependent)

        traverse_dependents(failed_service)
        return impacted

    def export_mermaid_diagram(self) -> str:
        """
        Export dependency graph as Mermaid diagram.

        Returns:
            Mermaid diagram markup
        """
        lines = ["graph TD"]

        # Define nodes with stages
        for stage_num in sorted(self._stages.keys()):
            lines.append(f"    subgraph Stage{stage_num}[Stage {stage_num}]")
            for service in sorted(self._stages[stage_num]):
                lines.append(f"        {service}")
            lines.append("    end")

        # Add edges
        for service, deps in sorted(self._dependency_graph.items()):
            for dep in sorted(deps):
                lines.append(f"    {dep} --> {service}")

        return "\n".join(lines)
