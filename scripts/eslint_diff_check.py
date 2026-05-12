#!/usr/bin/env python3
"""Line-level diff-aware ESLint check for the CoachIQ CI quality gate.

Frontend equivalent of ``scripts/ruff_diff_check.py``. Runs ``eslint`` on
every frontend file changed since a base ref, then filters the results down
to the lines actually added or modified by those commits. Implements the
project's "pragmatic mode" policy on the JavaScript/TypeScript side: legacy
debt on lines we didn't touch is allowed, but any new violation on a line
we DID touch fails the gate.

Why this exists
---------------
``pre-commit run --from-ref --to-ref`` is *file-level* diff-aware: it only
re-runs hooks on changed files. ESLint then lints the entire file and
reports every issue. With ~648 pre-existing ESLint errors and ~1496
warnings on the frontend, touching a single line in any frontend file
floods the gate with hundreds of legacy violations.

The script is intentionally small and stdlib-only, mirroring
``ruff_diff_check.py`` -- same exit codes, same output style, same overall
structure -- so the two ratchets behave consistently in CI logs.

Severity policy
---------------
ESLint emits both errors (``severity: 2``) and warnings (``severity: 1``).
By default this script BLOCKS on errors and reports warnings as advisory
(printed but exit 0 if errors are 0). Pass ``--warnings-fail`` to also
block on warnings.

Exit codes
----------
- 0: no NEW ESLint errors on changed lines (warnings may be present)
- 1: at least one NEW ESLint error on a changed line
- 2: tooling failure (git command failed, npm/eslint invocation failed,
  JSON parse failure, etc.)

Usage
-----
    poetry run python scripts/eslint_diff_check.py [BASE_REF] [--warnings-fail]

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

# Frontend extensions ESLint cares about. Mirrors the
# `files: ^frontend/.*\.(js|jsx|ts|tsx)$` regex in `.pre-commit-config.yaml`.
FRONTEND_EXTENSIONS = (".js", ".jsx", ".ts", ".tsx")

# A diff hunk header has the shape "@@ -OLD,LEN +NEW,LEN @@". After splitting
# on whitespace we expect at least the leading "@@", the "-OLD,LEN" range
# and the "+NEW,LEN" range -- three tokens. Anything shorter is malformed
# (or a noisy line) and should be skipped silently.
MIN_HUNK_HEADER_PARTS = 3

# ESLint severity codes (per https://eslint.org/docs/latest/integrate/nodejs-api).
SEVERITY_WARNING = 1
SEVERITY_ERROR = 2


def _run(cmd: list[str], *, cwd: Path | None = None, allow_nonzero: bool = False) -> str:
    """Run a command and return stdout, raising on non-zero exit unless allowed.

    ``allow_nonzero=True`` is the right setting for invoking eslint, which
    exits 1 when issues are found and we still want the JSON. Genuine
    tooling failures (no stdout, error on stderr) still exit 2.

    ``# noqa: S603/S607`` here mirror the rationale in ``ruff_diff_check.py``:
    this script INTENTIONALLY shells out to git, npm and eslint -- that's
    its whole job. Argument lists come from caller-controlled paths/refs,
    never from network input.
    """
    result = subprocess.run(  # noqa: S603
        cmd,
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )
    if result.returncode != 0 and not allow_nonzero:
        sys.stderr.write(f"command failed: {' '.join(cmd)}\n{result.stderr}")
        sys.exit(2)
    if result.returncode != 0 and allow_nonzero and not result.stdout.strip():
        # Tool exited non-zero AND produced no stdout -- this is a real
        # failure (e.g. eslint configuration broken), not just "found issues".
        sys.stderr.write(f"command failed: {' '.join(cmd)}\n{result.stderr}")
        sys.exit(2)
    return result.stdout


def _diff_range(base_ref: str) -> str:
    """Return the git diff range to use against ``base_ref``.

    Prefers three-dot (``A...HEAD``) which compares against the merge
    base -- matches GitHub PR diffs. Falls back to two-dot on shallow
    clones where the merge base isn't fetched.
    """
    probe = subprocess.run(  # noqa: S603 - controlled git invocation; see _run() docstring
        ["git", "merge-base", base_ref, "HEAD"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode == 0 and probe.stdout.strip():
        return f"{base_ref}...HEAD"
    return f"{base_ref}..HEAD"


def _changed_frontend_files(base_ref: str) -> list[str]:
    """Return PR-changed frontend source files (added/modified, not deleted).

    Filters by the ``frontend/`` prefix and the JS/TS extension set ESLint
    handles. Skips ``frontend/node_modules`` / ``dist`` / ``coverage`` so
    we don't accidentally lint installed packages or build artifacts that
    happen to appear in a diff (rare but possible during dependency
    bumps).
    """
    out = _run(
        ["git", "diff", "--name-only", "--diff-filter=AM", _diff_range(base_ref)],
    )
    skip_prefixes = (
        "frontend/node_modules/",
        "frontend/dist/",
        "frontend/coverage/",
    )
    files = []
    for line in out.splitlines():
        if not line.startswith("frontend/"):
            continue
        if any(line.startswith(p) for p in skip_prefixes):
            continue
        if not line.endswith(FRONTEND_EXTENSIONS):
            continue
        if Path(line).exists():
            files.append(line)
    return files


def _parse_hunk_header(line: str) -> tuple[int, int] | None:
    """Parse a `@@ -OLD,LEN +NEW,LEN @@` line into (new_start, new_length).

    Returns None for malformed headers so callers can skip silently.
    Same algorithm as ``ruff_diff_check.py`` -- duplicated rather than
    factored out because the two scripts are intentionally standalone
    (each one can be invoked without the other being installed/working).
    """
    parts = line.split(" ")
    if len(parts) < MIN_HUNK_HEADER_PARTS:
        return None
    new_part = parts[2].lstrip("+")
    try:
        if "," in new_part:
            start_str, length_str = new_part.split(",")
            return int(start_str), int(length_str)
        return int(new_part), 1
    except ValueError:
        return None


def _changed_lines(base_ref: str, files: list[str]) -> dict[str, set[int]]:
    """Return {repo-relative path: set of changed/added line numbers}.

    Uses ``git diff --unified=0`` so we get pure hunk ranges, not surrounding
    context. Parses the ``@@ -old +new[,len] @@`` headers directly via
    ``_parse_hunk_header``.
    """
    if not files:
        return {}

    out = _run(
        ["git", "diff", "--unified=0", _diff_range(base_ref), "--", *files],
    )

    result: dict[str, set[int]] = defaultdict(set)
    current_file: str | None = None

    for line in out.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:]
            continue
        if not line.startswith("@@") or current_file is None:
            continue

        parsed = _parse_hunk_header(line)
        if parsed is None:
            continue
        start, length = parsed

        # length 0 means "this is a deletion only" -- no lines added, skip
        if length == 0:
            continue

        for offset in range(length):
            result[current_file].add(start + offset)

    return result


def _eslint_issues(repo_relative_files: list[str], frontend_dir: Path) -> list[dict]:
    """Run ``eslint --format=json`` on the given files and return parsed list.

    ESLint runs from the ``frontend/`` directory, so file paths must be
    stripped of the ``frontend/`` prefix when invoking. The returned
    ``filePath`` is absolute, which we'll convert back to repo-relative
    in the caller.
    """
    if not repo_relative_files:
        return []

    # Strip "frontend/" prefix -- eslint runs from the frontend dir.
    stripped = [f[len("frontend/") :] for f in repo_relative_files]

    out = _run(
        ["npx", "eslint", "--format=json", "--no-error-on-unmatched-pattern", "--", *stripped],
        cwd=frontend_dir,
        allow_nonzero=True,  # eslint exits 1 when issues found; that's fine
    )
    if not out.strip():
        return []
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"failed to parse eslint JSON: {exc}\n{out[:500]}\n")
        sys.exit(2)


def _categorize_messages(
    eslint_results: list[dict],
    diff_lines: dict[str, set[int]],
    repo_root: Path,
) -> tuple[list[tuple[str, dict]], list[tuple[str, dict]], int, int]:
    """Cross-reference eslint diagnostics against the changed-line map.

    Returns ``(new_errors, new_warnings, legacy_error_count,
    legacy_warning_count)`` where each "new_*" entry is a ``(rel_path,
    message_dict)`` tuple ready for printing.
    """
    new_errors: list[tuple[str, dict]] = []
    new_warnings: list[tuple[str, dict]] = []
    legacy_errors = 0
    legacy_warnings = 0

    for result in eslint_results:
        try:
            rel = str(Path(result["filePath"]).resolve().relative_to(repo_root))
        except (KeyError, ValueError):
            continue

        changed = diff_lines.get(rel, set())
        for msg in result.get("messages", []):
            line = msg.get("line")
            severity = msg.get("severity")
            if line is None or severity is None:
                continue

            is_new = line in changed
            if severity == SEVERITY_ERROR:
                if is_new:
                    new_errors.append((rel, msg))
                else:
                    legacy_errors += 1
            elif severity == SEVERITY_WARNING:
                if is_new:
                    new_warnings.append((rel, msg))
                else:
                    legacy_warnings += 1

    return new_errors, new_warnings, legacy_errors, legacy_warnings


def _print_messages(
    label: str,
    items: list[tuple[str, dict]],
    *,
    stream: object,
) -> None:
    """Print a categorized message list with consistent formatting."""
    if not items:
        return
    stream.write(f"\n{label}:\n")
    for rel, msg in items:
        stream.write(
            f"  {rel}:{msg.get('line', '?')}:{msg.get('column', '?')}: "
            f"{msg.get('ruleId', '?')} -- {msg.get('message', '')}\n"
        )


def main() -> int:
    args = sys.argv[1:]
    warnings_fail = "--warnings-fail" in args
    args = [a for a in args if not a.startswith("--")]
    base_ref = args[0] if args else "origin/main"

    repo_root = Path.cwd().resolve()
    frontend_dir = repo_root / "frontend"
    if not frontend_dir.is_dir():
        sys.stderr.write(f"frontend/ directory not found at {frontend_dir}\n")
        return 2

    files = _changed_frontend_files(base_ref)
    if not files:
        print(f"No changed frontend files vs {base_ref} — nothing to check.")
        return 0

    diff_lines = _changed_lines(base_ref, files)
    eslint_results = _eslint_issues(files, frontend_dir)

    new_errors, new_warnings, legacy_errors, legacy_warnings = _categorize_messages(
        eslint_results, diff_lines, repo_root
    )

    legacy_summary = (
        f"({legacy_errors} legacy error(s) + {legacy_warnings} legacy warning(s) "
        f"on unchanged lines were ignored.)"
    )

    # Decide pass/fail.
    fail = bool(new_errors) or (warnings_fail and bool(new_warnings))

    if not fail:
        if new_warnings:
            # Warnings present but not blocking -- print them as advisory.
            _print_messages(
                f"⚠️  {len(new_warnings)} NEW ESLint warning(s) on changed lines",
                new_warnings,
                stream=sys.stdout,
            )
        print(
            f"✅ No NEW ESLint errors on changed lines "
            f"({len(files)} file(s) checked). {legacy_summary}"
        )
        return 0

    if new_errors:
        sys.stderr.write(
            f"❌ {len(new_errors)} NEW ESLint error(s) on lines added/changed in this PR"
        )
    if warnings_fail and new_warnings:
        sys.stderr.write(f" + {len(new_warnings)} NEW warning(s) (--warnings-fail in effect)")
    sys.stderr.write(":\n")
    _print_messages("Errors", new_errors, stream=sys.stderr)
    if warnings_fail:
        _print_messages(
            "Warnings (failing because --warnings-fail)", new_warnings, stream=sys.stderr
        )
    elif new_warnings:
        _print_messages("Warnings (advisory; not blocking)", new_warnings, stream=sys.stdout)

    sys.stderr.write(f"\n{legacy_summary}\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
