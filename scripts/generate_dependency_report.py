#!/usr/bin/env python3
"""
Generate Service Dependency Report

This script starts up the EnhancedServiceRegistry to analyze dependencies
and generate comprehensive documentation about service relationships.
"""

import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.core.service_dependency_resolver import DependencyType, ServiceDependency
from backend.core.service_registry import EnhancedServiceRegistry
from backend.main import _configure_service_startup_stages


async def generate_report():
    """Generate dependency report from service definitions."""
    print("Generating Service Dependency Report...")
    print("=" * 70)
    print()

    # Create registry and configure services
    registry = EnhancedServiceRegistry()

    # Configure services (but don't start them)
    await _configure_service_startup_stages(registry)

    # Get dependency report
    report = registry.get_dependency_report()
    print(report)

    # Get Mermaid diagram
    print("\n\nMermaid Dependency Diagram")
    print("=" * 70)
    diagram = registry.export_mermaid_diagram()
    print(diagram)

    # Save to files
    output_dir = Path(__file__).parent.parent / "docs" / "architecture"
    output_dir.mkdir(parents=True, exist_ok=True)

    report_file = output_dir / "service-dependencies.md"
    with open(report_file, "w") as f:
        f.write("# Service Dependency Report\n\n")
        f.write("Generated from EnhancedServiceRegistry configuration.\n\n")
        f.write("```\n")
        f.write(report)
        f.write("\n```\n\n")
        f.write("## Mermaid Dependency Diagram\n\n")
        f.write("```mermaid\n")
        f.write(diagram)
        f.write("\n```\n")

    print(f"\n\nReport saved to: {report_file}")


if __name__ == "__main__":
    asyncio.run(generate_report())
