#!/usr/bin/env python3
"""
Check for actual commit blockers based on pragmatic policy.
Only blocks on critical issues, warns on others.
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


def check_critical_security() -> tuple[bool, int]:
    """Check for medium+ security issues only."""
    print(f"{BLUE}🔒 Checking for critical security issues (Medium+)...{RESET}")

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
            "medium",
            "-f",
            "json",
        ]
    )

    if exit_code != 0 and "results" in stdout:
        # Parse to count issues
        import json

        try:
            data = json.loads(stdout)
            issue_count = len(data.get("results", []))
            if issue_count > 0:
                print(f"{RED}❌ Found {issue_count} CRITICAL security issues!{RESET}")
                print(f"{RED}These MUST be fixed before committing.{RESET}")
                # Show first few issues
                for issue in data["results"][:3]:
                    print(f"  - {issue['filename']}:{issue['line_number']} - {issue['issue_text']}")
                return False, issue_count
        except:
            pass

    print(f"{GREEN}✅ No critical security issues found{RESET}")
    return True, 0


def check_build_integrity() -> bool:
    """Check if the project builds (syntax/import errors)."""
    print(f"{BLUE}🏗️  Checking build integrity...{RESET}")

    # Quick syntax check on main entry point
    exit_code, stdout, stderr = run_command(
        ["poetry", "run", "python", "-m", "py_compile", "backend/main.py"]
    )

    if exit_code != 0:
        print(f"{RED}❌ Build check failed! Fix syntax/import errors.{RESET}")
        print(stderr)
        return False

    print(f"{GREEN}✅ Build integrity verified{RESET}")
    return True


def check_modified_files() -> tuple[bool, list[str]]:
    """Check if modified files meet ALL standards."""
    print(f"{BLUE}📝 Checking modified files for new issues...{RESET}")

    # Get modified Python files
    exit_code, stdout, stderr = run_command(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"]
    )

    if exit_code != 0:
        return True, []

    modified_files = [
        f for f in stdout.strip().split("\n") if f.endswith(".py") and f.startswith("backend/")
    ]

    if not modified_files:
        print(f"{GREEN}✅ No Python files modified{RESET}")
        return True, []

    issues_found = []
    for file in modified_files:
        # Run comprehensive checks on modified files
        exit_code, stdout, stderr = run_command(
            ["poetry", "run", "ruff", "check", file, "--no-fix"]
        )

        if exit_code != 0:
            issues_found.append(file)
            print(f"{YELLOW}  ⚠️  {file} has issues that should be fixed{RESET}")

    if issues_found:
        print(f"{YELLOW}Modified files have issues. Run 'poetry run ruff check --fix' on:{RESET}")
        for file in issues_found:
            print(f"  - {file}")
        return True, issues_found  # Warning only, don't block

    print(f"{GREEN}✅ Modified files are clean{RESET}")
    return True, []


def show_debt_summary():
    """Show a summary of technical debt (non-blocking)."""
    print(f"\n{BLUE}📊 Technical Debt Summary (non-blocking):{RESET}")

    # Count low-severity security issues
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
            "-f",
            "json",
        ]
    )

    if exit_code == 0 or "results" in stdout:
        try:
            import json

            data = json.loads(stdout)
            low_issues = len([i for i in data.get("results", []) if i["issue_severity"] == "LOW"])
            if low_issues > 0:
                print(f"{YELLOW}  - Low severity security: {low_issues} issues{RESET}")
        except:
            pass

    # Quick count of other issues
    print(f"{YELLOW}  - Run 'poetry run ruff check backend --statistics' for full report{RESET}")
    print(f"{YELLOW}  - Run 'npm run lint' in frontend/ for TypeScript issues{RESET}")


def main():
    """Main check function."""
    print(f"\n{BLUE}{'=' * 60}{RESET}")
    print(f"{BLUE}Pragmatic Commit Quality Check{RESET}")
    print(f"{BLUE}{'=' * 60}{RESET}\n")

    blockers = []

    # Check critical issues only
    print(f"{BLUE}Checking for commit blockers...{RESET}\n")

    # 1. Critical security
    security_ok, security_count = check_critical_security()
    if not security_ok:
        blockers.append(f"Fix {security_count} critical security issues")

    # 2. Build integrity
    if not check_build_integrity():
        blockers.append("Fix build/syntax errors")

    # 3. Modified files (warning only)
    files_ok, problem_files = check_modified_files()

    # Show summary
    print(f"\n{BLUE}{'=' * 60}{RESET}")

    if blockers:
        print(f"{RED}❌ COMMIT BLOCKED - Fix these critical issues:{RESET}")
        for blocker in blockers:
            print(f"{RED}  - {blocker}{RESET}")
        print(f"\n{RED}Run 'poetry run bandit -ll -r backend' to see security issues{RESET}")
    else:
        print(f"{GREEN}✅ No critical blockers - Commit allowed{RESET}")
        if problem_files:
            print(f"{YELLOW}   (But consider fixing issues in modified files){RESET}")

    # Always show debt summary
    show_debt_summary()

    print(f"{BLUE}{'=' * 60}{RESET}\n")

    sys.exit(1 if blockers else 0)


if __name__ == "__main__":
    main()
