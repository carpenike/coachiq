#!/usr/bin/env python3
"""Line-level diff-aware ruff check for the CoachIQ CI quality gate.

Runs ``ruff check`` on every file changed since a base ref, then filters the
results down to the lines actually added or modified by those commits. This
implements the project's stated "pragmatic mode" policy: legacy debt on
lines we didn't touch is allowed, but any new violation on a line we DID
touch fails the gate.

Why this exists
---------------
``pre-commit run --from-ref --to-ref`` is *file-level* diff-aware: it only
re-runs hooks on changed files. But ``ruff`` then lints the entire file and
reports every issue. On a project with significant legacy ruff debt this
defeats the pragmatic-mode intent — touching a single line in a 1000-line
legacy module floods the gate with hundreds of pre-existing violations.

The script is intentionally small and dependency-free (stdlib only) so it
can run inside the same poetry environment the CI gate already provides.

Exit codes
----------
- 0: no NEW ruff issues on changed lines
- 1: at least one NEW ruff issue on a changed line (printed to stderr)
- 2: tooling failure (git command failed, ruff invocation failed, etc.)

Usage
-----
    poetry run python scripts/ruff_diff_check.py [BASE_REF]

BASE_REF defaults to ``origin/main``. The script compares
``BASE_REF...HEAD`` (three-dot range), matching what GitHub Actions uses
for PR diffs against the target branch.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path


def _run(cmd: list[str]) -> str:
    """Run a command and return stdout, raising on non-zero exit."""
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        # ruff returns 1 when issues are found and we still want the JSON;
        # only treat genuine tooling failures (no stdout, error on stderr)
        # as fatal.
        if result.stdout.strip():
            return result.stdout
        sys.stderr.write(f"command failed: {' '.join(cmd)}\n{result.stderr}")
        sys.exit(2)
    return result.stdout


def _changed_python_files(base_ref: str) -> list[str]:
    """Return PR-changed .py files (added/modified, not deleted)."""
    out = _run(
        ["git", "diff", "--name-only", "--diff-filter=AM", f"{base_ref}...HEAD"]
    )
    return [line for line in out.splitlines() if line.endswith(".py") and Path(line).exists()]


def _changed_lines(base_ref: str, files: list[str]) -> dict[str, set[int]]:
    """Return {repo-relative path: set of changed/added line numbers}.

    Uses ``git diff --unified=0`` so we get pure hunk ranges, not surrounding
    context. Parses the ``@@ -old +new[,len] @@`` headers directly.
    """
    if not files:
        return {}

    out = _run(
        ["git", "diff", "--unified=0", f"{base_ref}...HEAD", "--", *files]
    )

    result: dict[str, set[int]] = defaultdict(set)
    current_file: str | None = None

    for line in out.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:]
            continue
        if not line.startswith("@@") or current_file is None:
            continue

        # @@ -OLD,LEN +NEW,LEN @@  (LEN is optional; absent means 1)
        parts = line.split(" ")
        if len(parts) < 3:
            continue
        new_part = parts[2].lstrip("+")
        if "," in new_part:
            try:
                start_str, length_str = new_part.split(",")
                start = int(start_str)
                length = int(length_str)
            except ValueError:
                continue
        else:
            try:
                start = int(new_part)
            except ValueError:
                continue
            length = 1

        # length 0 means "this is a deletion only" — no lines added, skip
        if length == 0:
            continue

        for offset in range(length):
            result[current_file].add(start + offset)

    return result


def _ruff_issues(files: list[str]) -> list[dict]:
    """Run ruff check on the given files and return parsed issue list."""
    if not files:
        return []
    out = _run(
        ["poetry", "run", "ruff", "check", "--output-format=json", *files]
    )
    if not out.strip():
        return []
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"failed to parse ruff JSON: {exc}\n{out[:500]}\n")
        sys.exit(2)


def main() -> int:
    base_ref = sys.argv[1] if len(sys.argv) > 1 else "origin/main"

    files = _changed_python_files(base_ref)
    if not files:
        print(f"No changed Python files vs {base_ref} — nothing to check.")
        return 0

    diff_lines = _changed_lines(base_ref, files)
    issues = _ruff_issues(files)

    repo_root = Path.cwd().resolve()
    new_issues: list[dict] = []

    for issue in issues:
        # ruff emits absolute paths; convert to repo-relative for matching.
        try:
            rel = str(Path(issue["filename"]).resolve().relative_to(repo_root))
        except (KeyError, ValueError):
            continue

        line = issue.get("location", {}).get("row")
        if line is None:
            continue

        if line in diff_lines.get(rel, set()):
            new_issues.append(issue)

    if not new_issues:
        suppressed = len(issues) - len(new_issues)
        print(
            f"✅ No NEW ruff issues on changed lines "
            f"({len(files)} files checked, {suppressed} legacy issues ignored)."
        )
        return 0

    sys.stderr.write(
        f"❌ {len(new_issues)} NEW ruff issue(s) on lines added/changed in this PR:\n\n"
    )
    for issue in new_issues:
        loc = issue.get("location", {})
        sys.stderr.write(
            f"  {issue.get('filename', '?')}:{loc.get('row', '?')}:"
            f"{loc.get('column', '?')}: {issue.get('code', '?')} "
            f"{issue.get('message', '')}\n"
        )
    sys.stderr.write(
        f"\n({len(issues) - len(new_issues)} legacy issues on unchanged lines were ignored.)\n"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
