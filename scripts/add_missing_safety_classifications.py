#!/usr/bin/env python3
"""
Script to add missing safety classifications to feature_flags.yaml

This script adds appropriate safety classifications to features that are missing them
based on the feature name and description patterns.
"""

import re
import sys
from pathlib import Path


def add_safety_classification_after_enabled(
    content: str,
    feature_name: str,
    classification: str,
    action: str = "continue_operation",
    maintain: bool = True,
) -> str:
    """Add safety classification after the 'enabled:' line for a feature."""

    # Pattern to match the feature block
    pattern = rf"^({feature_name}:\s*\n\s*enabled:\s*(?:true|false)\s*\n)"

    replacement = (
        rf'\1  safety_classification: "{classification}"\n'
        rf'  safe_state_action: "{action}"\n'
        rf"  maintain_state_on_failure: {str(maintain).lower()}\n"
    )

    return re.sub(pattern, replacement, content, flags=re.MULTILINE)


def main():
    yaml_path = Path(__file__).parent.parent / "backend" / "services" / "feature_flags.yaml"

    with open(yaml_path) as f:
        content = f.read()

    # Define features and their appropriate classifications
    updates = [
        # Infrastructure and operational features
        ("multi_network_can", "operational", "continue_operation", True),
        ("api_docs", "maintenance", "continue_operation", False),
        ("notifications", "operational", "continue_operation", True),
        ("multi_factor_authentication", "operational", "continue_operation", True),
        # Dashboard and analytics features (operational)
        ("dashboard_aggregation", "operational", "continue_operation", True),
        ("system_analytics", "operational", "continue_operation", True),
        ("activity_tracking", "operational", "continue_operation", True),
        ("performance_analytics", "operational", "continue_operation", True),
        ("analytics_dashboard", "operational", "continue_operation", True),
        # Device and maintenance features
        ("device_discovery", "operational", "continue_operation", True),
        ("predictive_maintenance", "operational", "continue_operation", True),
        ("advanced_diagnostics", "safety_related", "continue_operation", True),
        # Domain API v2 features (critical for new architecture)
        ("domain_api_v2", "critical", "continue_operation", True),
        ("entities_api_v2", "position_critical", "maintain_position", True),
        ("diagnostics_api_v2", "safety_related", "continue_operation", True),
        ("analytics_api_v2", "operational", "continue_operation", True),
        ("networks_api_v2", "safety_related", "continue_operation", True),
        ("system_api_v2", "operational", "continue_operation", True),
    ]

    # Apply updates
    for feature_name, classification, action, maintain in updates:
        content = add_safety_classification_after_enabled(
            content, feature_name, classification, action, maintain
        )
        print(f"Updated {feature_name}: {classification}")

    # Write back to file
    with open(yaml_path, "w") as f:
        f.write(content)

    print(f"\n✅ Updated {len(updates)} features with safety classifications")
    print("Run validation script to verify changes:")
    print("poetry run python scripts/validate_feature_definitions.py")


if __name__ == "__main__":
    main()
