#!/usr/bin/env python3
"""Compatibility wrapper for starting the CoachIQ backend server in development.

This script is kept for development use (dev_start.sh invokes it) and simply
delegates to the canonical entry point in ``backend.cli``, which provides the
full argument parsing, configuration display, and uvicorn startup logic.
"""

from backend.cli import main

if __name__ == "__main__":
    main()
