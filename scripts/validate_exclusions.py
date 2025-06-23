#!/usr/bin/env python3
"""Validate that exclusion lists are synchronized across tools."""

import sys
from pathlib import Path

try:
    import toml
except ImportError:
    print("❌ Error: toml package not installed. Run: pip install toml")
    sys.exit(1)


def main():
    """Check that Ruff and Pyright exclusion lists match."""
    project_root = Path(__file__).parent.parent
    pyproject_path = project_root / "pyproject.toml"

    if not pyproject_path.exists():
        print(f"❌ Error: {pyproject_path} not found")
        sys.exit(1)

    try:
        with open(pyproject_path) as f:
            config = toml.load(f)
    except Exception as e:
        print(f"❌ Error reading pyproject.toml: {e}")
        sys.exit(1)

    # Get exclusion lists
    ruff_exclude = set(config.get("tool", {}).get("ruff", {}).get("exclude", []))
    pyright_exclude = set(config.get("tool", {}).get("pyright", {}).get("exclude", []))
    bandit_exclude = set(config.get("tool", {}).get("bandit", {}).get("exclude_dirs", []))

    # Check if lists exist
    if not ruff_exclude:
        print("⚠️  Warning: No exclusions found for Ruff")
    if not pyright_exclude:
        print("⚠️  Warning: No exclusions found for Pyright")
    if not bandit_exclude:
        print("⚠️  Warning: No exclusions found for Bandit")

    # Compare Ruff and Pyright (should be identical)
    if ruff_exclude != pyright_exclude:
        print("❌ Exclusion lists differ between Ruff and Pyright!")
        print(f"\nRuff only: {sorted(ruff_exclude - pyright_exclude)}")
        print(f"Pyright only: {sorted(pyright_exclude - ruff_exclude)}")
        success = False
    else:
        print("✅ Ruff and Pyright exclusion lists match")
        success = True

    # Bandit can have a subset (it doesn't need all exclusions)
    # But check for any Bandit exclusions not in Ruff
    bandit_extra = bandit_exclude - ruff_exclude
    if bandit_extra:
        print(f"\n⚠️  Bandit has exclusions not in Ruff: {sorted(bandit_extra)}")
        print("   Consider adding these to Ruff/Pyright or removing from Bandit")

    # Print summary
    print("\n📊 Exclusion Summary:")
    print(f"   Ruff:    {len(ruff_exclude)} exclusions")
    print(f"   Pyright: {len(pyright_exclude)} exclusions")
    print(f"   Bandit:  {len(bandit_exclude)} exclusions")

    if success:
        print("\n✅ Validation passed!")
        sys.exit(0)
    else:
        print("\n❌ Validation failed!")
        print("\nTo fix: Update pyproject.toml so Ruff and Pyright have identical exclusion lists")
        print("See docs/code-quality-exclusions.md for the canonical list")
        sys.exit(1)


if __name__ == "__main__":
    main()
