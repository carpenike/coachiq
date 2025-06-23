#!/usr/bin/env python3
"""
Validate CoachIQ configuration and show what settings are in effect.
This helps debug configuration precedence issues.
"""

import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
from typing import Any, Dict

from backend.core.config import get_settings
from backend.services.feature_flags import load_feature_flags


def get_env_vars() -> dict[str, str]:
    """Get all COACHIQ_ environment variables."""
    return {k: v for k, v in os.environ.items() if k.startswith("COACHIQ_")}


def validate_config():
    """Validate configuration and show precedence."""
    print("=== CoachIQ Configuration Validator ===\n")

    # Show environment variables
    env_vars = get_env_vars()
    if env_vars:
        print("Environment Variables Set:")
        for key, value in sorted(env_vars.items()):
            # Mask sensitive values
            if any(
                sensitive in key.lower() for sensitive in ["secret", "key", "password", "token"]
            ):
                value = "***MASKED***"
            print(f"  {key}={value}")
    else:
        print("No COACHIQ_ environment variables set")

    print("\n" + "=" * 50 + "\n")

    # Load actual settings
    try:
        settings = get_settings()
        print("Effective Configuration:")

        # Show key settings
        config_dict = {
            "server": {
                "host": settings.server.host,
                "port": settings.server.port,
                "workers": settings.server.workers,
            },
            "features": {
                "domain_api_v2": settings.features.domain_api_v2,
                "entities_api_v2": settings.features.entities_api_v2,
                "j1939": settings.features.j1939,
                "firefly": settings.features.firefly,
            },
            "persistence": {
                "enabled": settings.persistence.enabled,
                "data_dir": str(settings.persistence.data_dir),
            },
            "logging": {
                "level": settings.logging.level,
            },
        }

        print(json.dumps(config_dict, indent=2))

    except Exception as e:
        print(f"ERROR loading configuration: {e}")
        return 1

    print("\n" + "=" * 50 + "\n")

    # Validate feature flags
    try:
        features = load_feature_flags()
        print(f"Feature Flags Loaded: {len(features)} features")

        # Check for conflicts
        for name, feature in features.items():
            if feature.get("enabled") and feature.get("depends_on"):
                for dep in feature["depends_on"]:
                    if not features.get(dep, {}).get("enabled"):
                        print(f"WARNING: Feature '{name}' depends on disabled feature '{dep}'")

    except Exception as e:
        print(f"ERROR loading feature flags: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(validate_config())
