#!/usr/bin/env python3
"""
Feature definitions validation script.

This script validates the feature_flags.yaml file against the new Pydantic models
to ensure all features have proper safety classifications and configurations.

Usage:
    poetry run python scripts/validate_feature_definitions.py
    poetry run python scripts/validate_feature_definitions.py --yaml-path custom_features.yaml
    poetry run python scripts/validate_feature_definitions.py --verbose
"""

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.services.feature_models import (
    FeatureConfigurationSet,
    FeatureDefinition,
    SafetyClassification,
)


def load_yaml_features(yaml_path: Path) -> dict[str, Any]:
    """Load feature definitions from YAML file."""
    try:
        with open(yaml_path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"❌ Failed to load YAML file '{yaml_path}': {e}")
        sys.exit(1)


def validate_features(
    features_data: dict[str, Any], verbose: bool = False
) -> FeatureConfigurationSet:
    """Validate features against Pydantic models."""

    print(f"🔍 Validating {len(features_data)} feature definitions...")

    # Convert raw YAML data to FeatureDefinition objects
    feature_definitions = {}
    validation_errors = []

    for feature_name, feature_data in features_data.items():
        try:
            # Add the feature name to the data
            feature_data_with_name = {"name": feature_name, **feature_data}

            # Validate individual feature
            feature_def = FeatureDefinition(**feature_data_with_name)
            feature_definitions[feature_name] = feature_def

            if verbose:
                print(f"  ✅ {feature_name}: {feature_def.safety_classification}")

        except ValidationError as e:
            validation_errors.append((feature_name, e))
            if verbose:
                print(f"  ❌ {feature_name}: {e}")

    if validation_errors:
        print(f"\n❌ Validation failed for {len(validation_errors)} features:")
        for feature_name, error in validation_errors:
            print(f"\n{feature_name}:")
            for err in error.errors():
                field = " -> ".join(str(loc) for loc in err["loc"])
                print(f"  - {field}: {err['msg']}")
        sys.exit(1)

    # Validate the complete configuration set
    try:
        config_set = FeatureConfigurationSet(features=feature_definitions)
        config_set.validate_dependency_graph()

    except ValidationError as e:
        print(f"❌ Configuration set validation failed: {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"❌ Dependency validation failed: {e}")
        sys.exit(1)

    return config_set


def analyze_feature_set(config_set: FeatureConfigurationSet, verbose: bool = False) -> None:
    """Analyze and report on the feature set."""

    print("\n📊 Feature Set Analysis:")
    print(f"  Total Features: {len(config_set.features)}")

    # Count by safety classification
    classification_counts = {}
    for classification in SafetyClassification:
        features = config_set.get_features_by_classification(classification)
        classification_counts[classification.value] = len(features)

        if verbose and features:
            feature_names = [f.name for f in features]
            print(f"  {classification.value.title()} ({len(features)}): {', '.join(feature_names)}")
        else:
            print(f"  {classification.value.title()}: {len(features)}")

    # Safety analysis
    critical_features = config_set.get_critical_features()
    toggleable_features = config_set.get_toggleable_features()

    print("\n🛡️  Safety Analysis:")
    print(f"  Safety-Critical Features: {len(critical_features)}")
    print(f"  Runtime Toggleable Features: {len(toggleable_features)}")

    # Dependency analysis
    startup_order = config_set.get_startup_order()
    print("\n🚀 Startup Order (first 10):")
    for i, feature_name in enumerate(startup_order[:10]):
        feature_def = config_set.features[feature_name]
        deps = ", ".join(feature_def.dependencies) if feature_def.dependencies else "none"
        print(f"  {i + 1:2d}. {feature_name} (deps: {deps})")

    if len(startup_order) > 10:
        print(f"     ... and {len(startup_order) - 10} more")


def generate_migration_report(config_set: FeatureConfigurationSet) -> None:
    """Generate a report for migrating from old core/enabled structure."""

    print("\n📝 Migration Report:")

    # Find features that might need attention
    critical_features = config_set.get_features_by_classification(SafetyClassification.CRITICAL)
    position_critical = config_set.get_features_by_classification(
        SafetyClassification.POSITION_CRITICAL
    )

    if critical_features:
        print("\n⚠️  Critical Features (cannot be toggled at runtime):")
        for feature in critical_features:
            print(f"  - {feature.name}: {feature.description}")

    if position_critical:
        print("\n🔒 Position-Critical Features (maintain position in safe state):")
        for feature in position_critical:
            print(f"  - {feature.name}: {feature.description}")

    # Check for potential issues
    issues = []

    for feature in config_set.features.values():
        # Check if safety classification matches expected patterns
        if "slide" in feature.name.lower() or "awning" in feature.name.lower():
            if feature.safety_classification != SafetyClassification.POSITION_CRITICAL:
                issues.append(
                    f"'{feature.name}' controls physical positioning but is not position_critical"
                )

        if "brake" in feature.name.lower() or "steering" in feature.name.lower():
            if feature.safety_classification not in [
                SafetyClassification.CRITICAL,
                SafetyClassification.SAFETY_RELATED,
            ]:
                issues.append(
                    f"'{feature.name}' appears safety-related but has classification: {feature.safety_classification}"
                )

    if issues:
        print("\n⚠️  Potential Classification Issues:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("\n✅ No obvious classification issues detected")


def main():
    """Main validation script."""
    parser = argparse.ArgumentParser(description="Validate feature definitions")
    parser.add_argument(
        "--yaml-path",
        type=Path,
        default=Path(__file__).parent.parent / "backend" / "services" / "feature_flags.yaml",
        help="Path to feature_flags.yaml file",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output showing details for each feature",
    )
    parser.add_argument(
        "--migration-report",
        action="store_true",
        help="Generate migration report for safety classifications",
    )

    args = parser.parse_args()

    # Validate YAML file exists
    if not args.yaml_path.exists():
        print(f"❌ YAML file not found: {args.yaml_path}")
        sys.exit(1)

    print("🔧 Feature Definitions Validator")
    print(f"📄 YAML File: {args.yaml_path}")
    print("=" * 60)

    # Load and validate features
    features_data = load_yaml_features(args.yaml_path)
    config_set = validate_features(features_data, verbose=args.verbose)

    print("✅ All feature definitions are valid!")

    # Generate analysis
    analyze_feature_set(config_set, verbose=args.verbose)

    # Generate migration report if requested
    if args.migration_report:
        generate_migration_report(config_set)

    print("\n🎉 Validation completed successfully!")


if __name__ == "__main__":
    main()
