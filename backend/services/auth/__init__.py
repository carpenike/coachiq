"""
Authentication services package (audit cycle 2026-05-13, PR A9).

This package consolidates the auth subsystem that was previously spread
across three top-level files in ``backend/services/``:

- ``auth_manager.py``  (~1800 LOC) -> :mod:`backend.services.auth.manager`
- ``auth_service.py``  (~270 LOC)  -> :mod:`backend.services.auth.service`
- ``auth_services.py`` (~680 LOC)  -> split into four modules:

  - :mod:`backend.services.auth.tokens`   -- ``TokenService``
  - :mod:`backend.services.auth.sessions` -- ``SessionService``
  - :mod:`backend.services.auth.mfa`      -- ``MfaService``
  - :mod:`backend.services.auth.lockout`  -- ``LockoutService``

The legacy ``AuthRepository`` (~1100 LOC) moved here too, as
:mod:`backend.services.auth.repository`. It's kept under that name for
backwards-compatibility with the rest of the system (see ADR-0007).

## Layered design (kept intentionally per ADR-0007)

The package preserves the two-layer split that exists in production:

- ``AuthManager`` (``manager``) is the policy/state engine. It owns the
  auth-mode (none/single-user/multi-user) decision, user lookup, password
  validation, magic-link issuance, MFA challenge orchestration, and the
  in-process state machine.
- ``AuthService`` (``service``) is the request-time facade that the rest
  of the application talks to via dependency injection. It wires the
  four sub-services (``TokenService``/``SessionService``/``MfaService``/
  ``LockoutService``) and the legacy ``AuthRepository`` into the
  ``AuthManager`` at startup, and exposes the manager to consumers.

They are deliberately NOT merged. The split makes ``AuthManager``
unit-testable without spinning up the FastAPI service layer, and lets
``AuthService`` stay thin (constructor wiring + lifecycle).

The follow-up cleanup -- collapsing the
``get_auth_manager().get_auth_manager()`` getter-of-getter charade and
the misleading registry key ``"auth_manager"`` -- is tracked separately
and intentionally out of scope for the file-relocation PR.
"""

from backend.services.auth.lockout import LockoutService
from backend.services.auth.manager import (
    AccountLockedError,
    AuthenticationError,
    AuthManager,
    AuthMode,
    InvalidTokenError,
    UserNotFoundError,
)
from backend.services.auth.mfa import MfaService
from backend.services.auth.repository import AuthRepository
from backend.services.auth.service import AuthService, create_auth_service
from backend.services.auth.sessions import SessionService
from backend.services.auth.tokens import TokenService

__all__ = [
    "AccountLockedError",
    "AuthManager",
    "AuthMode",
    "AuthRepository",
    "AuthService",
    "AuthenticationError",
    "InvalidTokenError",
    "LockoutService",
    "MfaService",
    "SessionService",
    "TokenService",
    "UserNotFoundError",
    "create_auth_service",
]
