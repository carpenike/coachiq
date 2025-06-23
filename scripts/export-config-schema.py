#!/usr/bin/env python3
"""
Export configuration schema to help generate Nix module options.
This ensures Nix module stays in sync with backend expectations.
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, Type, get_args, get_origin

from pydantic import BaseModel
from pydantic.fields import FieldInfo

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.core.config import (
    CANSettings,
    CORSSettings,
    FeatureSettings,
    LoggingSettings,
    NotificationSettings,
    PersistenceSettings,
    RVCSettings,
    SecuritySettings,
    ServerSettings,
    Settings,
)


def get_type_info(field_type: type) -> dict[str, Any]:
    """Extract type information for documentation."""
    origin = get_origin(field_type)

    if origin is None:
        # Simple type
        if field_type == bool:
            return {"type": "bool", "nix_type": "lib.types.bool"}
        if field_type == int:
            return {"type": "int", "nix_type": "lib.types.int"}
        if field_type == float:
            return {"type": "float", "nix_type": "lib.types.float"}
        if field_type == str:
            return {"type": "string", "nix_type": "lib.types.str"}
        if issubclass(field_type, Path):
            return {"type": "path", "nix_type": "lib.types.path"}
    # Complex type
    elif origin is list:
        inner = get_args(field_type)[0]
        inner_info = get_type_info(inner)
        return {
            "type": f"list[{inner_info['type']}]",
            "nix_type": f"lib.types.listOf {inner_info['nix_type']}",
        }
    elif origin is dict:
        return {"type": "dict", "nix_type": "lib.types.attrs"}
    elif origin is type(None) or (hasattr(origin, "__name__") and "Union" in origin.__name__):
        # Optional type
        args = get_args(field_type)
        if type(None) in args:
            non_none = [a for a in args if a != type(None)][0]
            inner_info = get_type_info(non_none)
            return {
                "type": f"optional[{inner_info['type']}]",
                "nix_type": f"lib.types.nullOr {inner_info['nix_type']}",
                "optional": True,
            }

    return {"type": str(field_type), "nix_type": "lib.types.unspecified"}


def extract_schema(model: type[BaseModel], prefix: str = "") -> dict[str, Any]:
    """Extract schema from Pydantic model."""
    schema = {}

    for field_name, field_info in model.model_fields.items():
        field_type = field_info.annotation
        type_info = get_type_info(field_type)

        env_var = f"{prefix}{field_name.upper()}"

        schema[field_name] = {
            "env_var": env_var,
            "type": type_info.get("type"),
            "nix_type": type_info.get("nix_type"),
            "optional": type_info.get("optional", False),
            "default": field_info.default if field_info.default is not ... else None,
            "description": field_info.description or "",
        }

        # Handle nested models
        if hasattr(field_type, "model_fields"):
            schema[field_name]["nested"] = extract_schema(
                field_type, prefix=f"{prefix}{field_name.upper()}__"
            )

    return schema


def generate_nix_module_snippet(schema: dict[str, Any], indent: int = 0) -> str:
    """Generate Nix module definition from schema."""
    lines = []
    spaces = "  " * indent

    for field_name, info in schema.items():
        if "nested" in info:
            # Nested attribute set
            lines.append(f"{spaces}{field_name} = {{")
            lines.append(generate_nix_module_snippet(info["nested"], indent + 1))
            lines.append(f"{spaces}}};")
        else:
            # Regular option
            lines.append(f"{spaces}{field_name} = lib.mkOption {{")
            lines.append(f"{spaces}  type = {info['nix_type']};")
            if info["optional"]:
                lines.append(f"{spaces}  default = null;")
            lines.append(f"{spaces}  description = ''")
            lines.append(f"{spaces}    {info['description']}")
            if info["default"] is not None and not info["optional"]:
                lines.append(f"{spaces}    Default: {info['default']}")
            lines.append(f"{spaces}    Environment variable: {info['env_var']}")
            lines.append(f"{spaces}  '';")
            lines.append(f"{spaces}}};")
            lines.append("")

    return "\n".join(lines)


def main():
    """Export configuration schema."""
    print("=== CoachIQ Configuration Schema ===\n")

    # Extract schema from Settings model
    schema = extract_schema(Settings, prefix="COACHIQ_")

    # Output JSON schema
    with open("docs/config-schema.json", "w") as f:
        json.dump(schema, f, indent=2, default=str)
    print("✓ Exported JSON schema to docs/config-schema.json")

    # Generate Nix module snippet
    nix_module = generate_nix_module_snippet(schema["settings"]["nested"])
    with open("docs/nix-module-generated.nix", "w") as f:
        f.write("# Auto-generated Nix module options from backend schema\n")
        f.write("# Generated by scripts/export-config-schema.py\n\n")
        f.write("{\n")
        f.write(nix_module)
        f.write("}\n")
    print("✓ Generated Nix module snippet in docs/nix-module-generated.nix")

    # Generate environment variable reference
    with open("docs/environment-variables.md", "w") as f:
        f.write("# CoachIQ Environment Variables Reference\n\n")
        f.write("This document lists all environment variables recognized by CoachIQ.\n\n")

        def write_env_vars(schema: dict[str, Any], level: int = 2):
            for field_name, info in sorted(schema.items()):
                if "nested" in info:
                    f.write(f"{'#' * level} {field_name.title()}\n\n")
                    write_env_vars(info["nested"], level + 1)
                else:
                    f.write(f"{'#' * level} `{info['env_var']}`\n\n")
                    f.write(f"- **Type**: {info['type']}\n")
                    f.write(f"- **Description**: {info['description']}\n")
                    if info["default"] is not None:
                        f.write(f"- **Default**: `{info['default']}`\n")
                    f.write("\n")

        write_env_vars(schema)

    print("✓ Generated environment variable reference in docs/environment-variables.md")

    print("\nDone! Check the docs/ directory for generated files.")


if __name__ == "__main__":
    main()
