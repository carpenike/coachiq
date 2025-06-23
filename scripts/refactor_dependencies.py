#!/usr/bin/env python3
"""Analyze service dependencies specifically for the refactoring plan.

This script analyzes the 18 services that need to be refactored to determine
the optimal order and grouping for parallel work.
"""

import ast
import json
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

# The 18 services to refactor
SERVICES_TO_REFACTOR = [
    "safety_service",
    "security_audit_service",
    "security_config_service",
    "network_security_service",
    "persistence_service",
    "dashboard_service",
    "analytics_dashboard_service",
    "coach_mapping_service",
    "journal_service",
    "docs_service",
    "notification_analytics_service",
    "notification_reporting_service",
    "predictive_maintenance_service",
    "secure_token_service",
    "user_invitation_service",
    "vector_service",
    "analytics_storage_service",
    "security_persistence_service",
]


def extract_dependencies_from_file(file_path: Path) -> dict[str, set[str]]:
    """Extract service and repository dependencies from a Python file."""
    try:
        with open(file_path) as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return {"services": set(), "repositories": set()}

    services = set()
    repositories = set()

    # Find imports
    import_pattern = r"from\s+backend\.services\.(\w+)\s+import"
    imports = re.findall(import_pattern, content)
    for imp in imports:
        if imp.replace("_service", "") in [s.replace("_service", "") for s in SERVICES_TO_REFACTOR]:
            services.add(imp)

    # Find service dependencies in __init__ method
    init_pattern = r"def\s+__init__\s*\([^)]+\):"
    init_match = re.search(init_pattern, content, re.MULTILINE)
    if init_match:
        # Extract the __init__ method body
        init_start = init_match.end()
        # Find all parameters that look like services
        param_pattern = r"(\w+):\s*(?:Optional\[)?(\w+Service)"
        params = re.findall(param_pattern, content[init_match.start() : init_start + 500])

        for param_name, service_type in params:
            # Normalize service name
            service_name = service_type.replace("Service", "").lower() + "_service"
            if service_name.replace("_service", "") in [
                s.replace("_service", "") for s in SERVICES_TO_REFACTOR
            ]:
                services.add(service_name)

    # Find repository dependencies
    repo_pattern = r"(\w+Repository)"
    repos = re.findall(repo_pattern, content)
    repositories.update(repos)

    # Also check for direct service references
    for service in SERVICES_TO_REFACTOR:
        if service in content and service != file_path.stem:
            services.add(service)

    return {"services": services, "repositories": repositories}


def analyze_dependencies() -> dict[str, dict]:
    """Analyze dependencies for all services to refactor."""
    services_dir = Path("backend/services")
    dependencies = {}

    for service_name in SERVICES_TO_REFACTOR:
        file_path = services_dir / f"{service_name}.py"
        if not file_path.exists():
            print(f"Warning: {file_path} not found")
            continue

        deps = extract_dependencies_from_file(file_path)

        # Filter service dependencies to only include those in our refactor list
        service_deps = []
        for dep in deps["services"]:
            dep_normalized = dep.replace("_service", "")
            if dep_normalized in [s.replace("_service", "") for s in SERVICES_TO_REFACTOR]:
                if dep_normalized != service_name.replace("_service", ""):  # Don't include self
                    service_deps.append(dep_normalized + "_service")

        dependencies[service_name] = {
            "service_dependencies": sorted(list(set(service_deps))),
            "repository_dependencies": sorted(list(deps["repositories"])),
            "dependency_count": len(service_deps),
        }

    return dependencies


def create_dependency_graph(dependencies: dict) -> dict[str, list[str]]:
    """Create a graph showing which services depend on which."""
    graph = defaultdict(list)

    for service, info in dependencies.items():
        for dep in info["service_dependencies"]:
            graph[dep].append(service)

    return dict(graph)


def find_circular_dependencies(dependencies: dict) -> list[list[str]]:
    """Find any circular dependencies."""

    def dfs(node, visited, rec_stack, path, cycles):
        visited.add(node)
        rec_stack.add(node)
        path.append(node)

        deps = dependencies.get(node, {}).get("service_dependencies", [])
        for dep in deps:
            if dep not in visited:
                dfs(dep, visited, rec_stack, path, cycles)
            elif dep in rec_stack:
                # Found a cycle
                cycle_start = path.index(dep)
                cycle = path[cycle_start:] + [dep]
                cycles.append(cycle)

        path.pop()
        rec_stack.remove(node)

    visited = set()
    cycles = []

    for service in dependencies:
        if service not in visited:
            dfs(service, visited, set(), [], cycles)

    return cycles


def topological_sort(dependencies: dict) -> list[list[str]]:
    """Perform topological sort to find refactoring order."""
    # Calculate in-degree for each service
    in_degree = dict.fromkeys(dependencies, 0)

    for service, info in dependencies.items():
        for dep in info["service_dependencies"]:
            if dep in in_degree:
                in_degree[dep] += 1

    # Group services by level
    groups = []
    remaining = set(dependencies.keys())

    while remaining:
        # Find all services with no dependencies on remaining services
        current_group = []
        for service in remaining:
            deps_in_remaining = [
                d for d in dependencies[service]["service_dependencies"] if d in remaining
            ]
            if not deps_in_remaining:
                current_group.append(service)

        if not current_group:
            # Circular dependency detected
            # Take the service with fewest dependencies
            min_deps = min(
                remaining,
                key=lambda s: len(
                    [d for d in dependencies[s]["service_dependencies"] if d in remaining]
                ),
            )
            current_group = [min_deps]
            print(f"Warning: Circular dependency detected, forcing {min_deps}")

        groups.append(sorted(current_group))
        remaining -= set(current_group)

    return groups


def categorize_services(dependencies: dict) -> dict[str, list[str]]:
    """Categorize services by type."""
    categories = {"safety_security": [], "core": [], "analytics": [], "auxiliary": []}

    for service in dependencies:
        if any(keyword in service for keyword in ["safety", "security", "auth"]):
            categories["safety_security"].append(service)
        elif any(keyword in service for keyword in ["persistence", "dashboard", "coach_mapping"]):
            categories["core"].append(service)
        elif any(keyword in service for keyword in ["analytics", "predictive"]):
            categories["analytics"].append(service)
        else:
            categories["auxiliary"].append(service)

    return categories


def main():
    """Main entry point."""
    print("Analyzing service dependencies for refactoring plan...")
    print("=" * 80)

    # Analyze dependencies
    dependencies = analyze_dependencies()

    # Find circular dependencies
    cycles = find_circular_dependencies(dependencies)
    if cycles:
        print("\n⚠️  CIRCULAR DEPENDENCIES DETECTED:")
        for cycle in cycles:
            print(f"  {' -> '.join(cycle)}")

    # Create dependency graph
    reverse_deps = create_dependency_graph(dependencies)

    # Perform topological sort
    groups = topological_sort(dependencies)

    # Categorize services
    categories = categorize_services(dependencies)

    # Output results
    print("\n" + "=" * 80)
    print("DEPENDENCY ANALYSIS RESULTS")
    print("=" * 80)

    print(f"\nTotal services to refactor: {len(dependencies)}")

    # Show dependencies for each service
    print("\n" + "-" * 80)
    print("SERVICE DEPENDENCIES")
    print("-" * 80)

    for service, info in sorted(dependencies.items(), key=lambda x: x[1]["dependency_count"]):
        print(f"\n{service}:")
        print(f"  Dependencies on other services: {info['service_dependencies'] or 'None'}")
        print(f"  Repository dependencies: {len(info['repository_dependencies'])}")
        if service in reverse_deps:
            print(f"  Services that depend on this: {reverse_deps[service]}")

    # Show refactoring groups
    print("\n" + "-" * 80)
    print("REFACTORING GROUPS (in order)")
    print("-" * 80)

    total_days = 0
    for i, group in enumerate(groups, 1):
        print(f"\nGroup {i}: {len(group)} services (can be done in parallel)")

        # Categorize this group
        group_categories = defaultdict(list)
        for service in group:
            for cat, services in categories.items():
                if service in services:
                    group_categories[cat].append(service)

        for cat, services in group_categories.items():
            if services:
                print(f"  {cat}: {', '.join(services)}")

        # Estimate time
        has_critical = any(s in categories["safety_security"] for s in group)
        days = 2 if has_critical else 1.5
        print(f"  Estimated time: {days} days")
        total_days += days

    print(f"\nTotal estimated time: {total_days} days")

    # Show service categories
    print("\n" + "-" * 80)
    print("SERVICE CATEGORIES")
    print("-" * 80)

    for category, services in categories.items():
        if services:
            print(f"\n{category.replace('_', ' ').title()}: {len(services)} services")
            for service in sorted(services):
                deps = dependencies[service]["service_dependencies"]
                print(f"  - {service} (deps: {len(deps)})")

    # Save results
    output = {
        "services": dependencies,
        "groups": [{"group": i + 1, "services": group} for i, group in enumerate(groups)],
        "categories": categories,
        "circular_dependencies": cycles,
        "estimated_days": total_days,
    }

    with open("refactor_dependency_analysis.json", "w") as f:
        json.dump(output, f, indent=2)

    print("\n✅ Results saved to refactor_dependency_analysis.json")

    # Create markdown report
    with open("REFACTORING_GROUPS.md", "w") as f:
        f.write("# Service Refactoring Groups\n\n")
        f.write("Based on dependency analysis, here are the recommended refactoring groups:\n\n")

        for i, group in enumerate(groups, 1):
            f.write(f"## Group {i}\n\n")
            f.write("**Services** (can be refactored in parallel):\n")
            for service in sorted(group):
                deps = dependencies[service]["service_dependencies"]
                f.write(f"- `{service}` - Dependencies: {', '.join(deps) if deps else 'None'}\n")
            f.write("\n")

    print("✅ Markdown report saved to REFACTORING_GROUPS.md")


if __name__ == "__main__":
    main()
