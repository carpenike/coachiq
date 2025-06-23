#!/usr/bin/env python3
"""
Enforce quality standards for safety-critical commits.
This script should be run as part of pre-commit hooks.
"""

import subprocess
import sys
from pathlib import Path

# ANSI color codes
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


def run_command(cmd: list[str]) -> tuple[int, str, str]:
    """Run a command and return exit code, stdout, stderr."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return 1, "", str(e)


def check_security_issues() -> bool:
    """Check for security issues with Bandit."""
    print(f"{BLUE}🔒 Checking security issues with Bandit...{RESET}")

    exit_code, stdout, stderr = run_command(
        [
            "poetry",
            "run",
            "bandit",
            "-c",
            "pyproject.toml",
            "-r",
            "backend",
            "--severity-level",
            "low",
        ]
    )

    if exit_code != 0:
        print(f"{RED}❌ SECURITY ISSUES FOUND!{RESET}")
        print(f"{RED}No commits allowed with ANY security issues.{RESET}")
        print(stdout)
        return False

    print(f"{GREEN}✅ No security issues found{RESET}")
    return True


def check_type_safety() -> bool:
    """Check for type safety issues."""
    print(f"{BLUE}🔍 Checking type safety...{RESET}")

    # Check for 'any' types in TypeScript
    exit_code, stdout, stderr = run_command(
        ["grep", "-r", "--include=*.ts", "--include=*.tsx", ": any", "frontend/src"]
    )

    if exit_code == 0:  # grep returns 0 if matches found
        print(f"{RED}❌ FOUND 'any' TYPES IN TYPESCRIPT!{RESET}")
        print(f"{RED}Safety-critical systems cannot use 'any' types.{RESET}")
        print("Files with 'any' types:")
        for line in stdout.strip().split("\n")[:10]:  # Show first 10
            print(f"  {line}")
        return False

    print(f"{GREEN}✅ No 'any' types found{RESET}")
    return True


def check_critical_patterns() -> bool:
    """Check for critical anti-patterns."""
    print(f"{BLUE}🚨 Checking critical patterns...{RESET}")

    patterns = [
        {
            "name": "print statements",
            "pattern": r"^\s*print\(",
            "message": "Use logging instead of print statements",
        },
        {
            "name": "try-except-pass",
            "pattern": r"except.*:\s*\n\s*pass",
            "message": "Never silently ignore exceptions",
        },
        {
            "name": "TODO comments",
            "pattern": r"#\s*(TODO|FIXME|XXX)",
            "message": "Resolve TODOs before committing",
        },
    ]

    issues_found = False

    for pattern_info in patterns:
        exit_code, stdout, stderr = run_command(
            ["grep", "-r", "--include=*.py", "-E", pattern_info["pattern"], "backend"]
        )

        if exit_code == 0:
            print(f"{YELLOW}⚠️  Found {pattern_info['name']}:{RESET}")
            print(f"   {pattern_info['message']}")
            for line in stdout.strip().split("\n")[:5]:
                print(f"   {line}")
            issues_found = True

    return not issues_found


def check_build_integrity() -> bool:
    """Check if the project builds successfully."""
    print(f"{BLUE}🏗️  Checking build integrity...{RESET}")

    # Check Python imports
    exit_code, stdout, stderr = run_command(
        ["poetry", "run", "python", "-m", "py_compile", "backend/main.py"]
    )

    if exit_code != 0:
        print(f"{RED}❌ Python build check failed!{RESET}")
        print(stderr)
        return False

    print(f"{GREEN}✅ Build integrity verified{RESET}")
    return True


def main():
    """Main enforcement function."""
    print(f"\n{BLUE}{'=' * 60}{RESET}")
    print(f"{BLUE}Safety-Critical Commit Quality Enforcement{RESET}")
    print(f"{BLUE}{'=' * 60}{RESET}\n")

    all_checks_passed = True

    # Run all checks
    checks = [
        ("Security", check_security_issues),
        ("Type Safety", check_type_safety),
        ("Critical Patterns", check_critical_patterns),
        ("Build Integrity", check_build_integrity),
    ]

    for check_name, check_func in checks:
        if not check_func():
            all_checks_passed = False
            print()

    # Final verdict
    print(f"\n{BLUE}{'=' * 60}{RESET}")
    if all_checks_passed:
        print(f"{GREEN}✅ ALL CHECKS PASSED - Commit allowed{RESET}")
        print(f"{GREEN}Thank you for maintaining safety standards!{RESET}")
    else:
        print(f"{RED}❌ COMMIT BLOCKED - Fix issues above{RESET}")
        print(f"{RED}This is a safety-critical system.{RESET}")
        print(f"{RED}No exceptions to quality standards.{RESET}")
    print(f"{BLUE}{'=' * 60}{RESET}\n")

    sys.exit(0 if all_checks_passed else 1)


if __name__ == "__main__":
    main()
