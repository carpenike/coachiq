#!/usr/bin/env python3
"""
Analyze Service Dependencies

This script analyzes the service configuration without full imports
to generate dependency documentation.
"""

import ast
import re
from pathlib import Path


def extract_service_definitions(file_path):
    """Extract service definitions from main.py."""
    with open(file_path, 'r') as f:
        content = f.read()

    # Find the _configure_service_startup_stages function
    func_match = re.search(r'async def _configure_service_startup_stages.*?(?=\n\n\nasync def|\ndef|\Z)', content, re.DOTALL)
    if not func_match:
        return []

    func_content = func_match.group(0)

    # Extract service registrations
    services = []
    service_pattern = r'service_registry\.register_service\((.*?)\n    \)'

    for match in re.finditer(service_pattern, func_content, re.DOTALL):
        service_def = match.group(1)

        # Extract service details
        name_match = re.search(r'name="([^"]+)"', service_def)
        desc_match = re.search(r'description="([^"]+)"', service_def)
        tags_match = re.search(r'tags=\{([^}]+)\}', service_def)

        # Extract dependencies
        deps = []
        dep_pattern = r'ServiceDependency\("([^"]+)", DependencyType\.(\w+)\)'
        for dep_match in re.finditer(dep_pattern, service_def):
            deps.append({
                'name': dep_match.group(1),
                'type': dep_match.group(2)
            })

        # Also check for simple dependencies
        simple_deps_match = re.search(r'dependencies=\[\s*\]', service_def)
        if simple_deps_match:
            # No dependencies
            pass

        if name_match:
            service = {
                'name': name_match.group(1),
                'description': desc_match.group(1) if desc_match else '',
                'tags': [t.strip().strip('"') for t in tags_match.group(1).split(',')] if tags_match else [],
                'dependencies': deps
            }
            services.append(service)

    return services


def generate_markdown_report(services):
    """Generate markdown documentation."""
    lines = ["# Service Dependency Documentation\n"]
    lines.append("Generated from EnhancedServiceRegistry configuration in `backend/main.py`.\n")

    # Overview table
    lines.append("## Service Overview\n")
    lines.append("| Service | Description | Tags | Dependencies |")
    lines.append("|---------|-------------|------|--------------|")

    for service in services:
        deps_str = ', '.join([f"{d['name']} ({d['type']})" for d in service['dependencies']]) if service['dependencies'] else 'None'
        tags_str = ', '.join(service['tags'])
        lines.append(f"| {service['name']} | {service['description']} | {tags_str} | {deps_str} |")

    # Dependency stages
    lines.append("\n## Startup Stages\n")
    lines.append("Services are automatically grouped into stages based on dependencies:\n")

    # Calculate stages
    stages = {}
    stage_0 = [s for s in services if not s['dependencies']]
    if stage_0:
        stages[0] = stage_0

    # Simple stage calculation (not perfect but good enough)
    remaining = [s for s in services if s['dependencies']]
    stage_num = 1
    while remaining:
        stage_services = []
        for service in remaining[:]:
            # Check if all required deps are in earlier stages
            can_start = True
            for dep in service['dependencies']:
                if dep['type'] == 'REQUIRED':
                    # Check if dep is in an earlier stage
                    found = False
                    for stage, stage_svcs in stages.items():
                        if any(s['name'] == dep['name'] for s in stage_svcs):
                            found = True
                            break
                    if not found and dep['name'] != 'app_state':  # app_state is from FeatureManager
                        can_start = False
                        break

            if can_start:
                stage_services.append(service)
                remaining.remove(service)

        if stage_services:
            stages[stage_num] = stage_services
            stage_num += 1
        else:
            # Remaining services have unresolved deps
            if remaining:
                stages['unresolved'] = remaining
            break

    for stage, svcs in sorted(stages.items()):
        if stage == 'unresolved':
            lines.append(f"\n### Unresolved Dependencies")
            lines.append("These services have dependencies that couldn't be resolved:")
        else:
            lines.append(f"\n### Stage {stage}")

        for service in svcs:
            deps_str = ', '.join([f"{d['name']}" for d in service['dependencies']]) if service['dependencies'] else 'none'
            lines.append(f"- **{service['name']}**: {service['description']} (deps: {deps_str})")

    # Mermaid diagram
    lines.append("\n## Dependency Graph\n")
    lines.append("```mermaid")
    lines.append("graph TD")

    # Group by stages
    for stage, svcs in sorted(stages.items()):
        if stage != 'unresolved':
            lines.append(f"    subgraph Stage{stage}[Stage {stage}]")
            for service in svcs:
                lines.append(f"        {service['name']}")
            lines.append("    end")

    # Add edges
    for service in services:
        for dep in service['dependencies']:
            if dep['type'] == 'REQUIRED':
                lines.append(f"    {dep['name']} --> {service['name']}")

    lines.append("```")

    return '\n'.join(lines)


def main():
    """Main function."""
    # Find main.py
    main_py = Path(__file__).parent.parent / "backend" / "main.py"

    if not main_py.exists():
        print(f"Error: {main_py} not found")
        return

    # Extract service definitions
    services = extract_service_definitions(main_py)

    if not services:
        print("No services found")
        return

    print(f"Found {len(services)} services")

    # Generate report
    report = generate_markdown_report(services)

    # Save report
    output_dir = Path(__file__).parent.parent / "docs" / "architecture"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / "service-dependencies.md"
    with open(output_file, 'w') as f:
        f.write(report)

    print(f"Report saved to: {output_file}")
    print("\nReport preview:")
    print("=" * 70)
    print(report[:1000] + "..." if len(report) > 1000 else report)


if __name__ == "__main__":
    main()
