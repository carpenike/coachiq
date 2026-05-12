#!/usr/bin/env python3
"""
Tests for RVC Service.

This module is intentionally a skip stub.

The previous test body asserted against an obsolete RVCService constructor
signature (``RVCService(app_state)``). The current constructor is
``RVCService(rvc_config_repository, can_tracking_repository=None)`` — see
``backend/services/rvc_service.py``. The old tests passed only because
``MagicMock(spec=AppState)`` silently absorbs any positional argument, so
they were testing nothing.

Issue #105 (test-restoration sweep #2) tracks the rewrite of this module
against the current repository-based constructor.
"""

import pytest

pytest.skip(
    "RVCService no longer takes AppState; tests need rewriting against "
    "the (rvc_config_repository, can_tracking_repository) constructor — "
    "see issue #105.",
    allow_module_level=True,
)
