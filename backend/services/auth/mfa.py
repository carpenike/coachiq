"""Multi-Factor Authentication operations.

Extracted from the historical ``backend/services/auth_services.py`` in
audit cycle 2026-05-13 PR A9. The :class:`MfaService` body is moved
verbatim; only the surrounding imports and module docstring are new.
"""

import logging
import secrets
from datetime import UTC, datetime
from typing import Any

import pyotp
from passlib.hash import bcrypt

from backend.core.performance import PerformanceMonitor
from backend.repositories.auth_repository import MfaRepository

logger = logging.getLogger(__name__)


class MfaService:
    """Service for Multi-Factor Authentication operations."""

    def __init__(
        self,
        mfa_repository: MfaRepository,
        performance_monitor: PerformanceMonitor,
        issuer_name: str = "RV-C System",
        backup_codes_count: int = 8,
    ):
        """Initialize the MFA service.

        Args:
            mfa_repository: Repository for MFA data
            performance_monitor: Performance monitoring instance
            issuer_name: TOTP issuer name
            backup_codes_count: Number of backup codes to generate
        """
        self._mfa_repo = mfa_repository
        self._monitor = performance_monitor
        self._issuer_name = issuer_name
        self._backup_codes_count = backup_codes_count

        # Apply performance monitoring
        self._apply_monitoring()

        logger.info("MfaService initialized")

    def _apply_monitoring(self) -> None:
        """Apply performance monitoring to service methods."""
        self.generate_mfa_setup = self._monitor.monitor_service_method(
            "MfaService", "generate_mfa_setup"
        )(self.generate_mfa_setup)

        self.enable_mfa = self._monitor.monitor_service_method("MfaService", "enable_mfa")(
            self.enable_mfa
        )

        self.verify_mfa_code = self._monitor.monitor_service_method(
            "MfaService", "verify_mfa_code"
        )(self.verify_mfa_code)

    async def generate_mfa_setup(self, user_id: str, username: str) -> dict[str, Any]:
        """Generate MFA setup data.

        Args:
            user_id: User identifier
            username: Username for TOTP

        Returns:
            MFA setup data with secret and QR code
        """
        # Generate TOTP secret
        secret = pyotp.random_base32()

        # Generate backup codes
        backup_codes = [secrets.token_hex(4).upper() for _ in range(self._backup_codes_count)]

        # Hash backup codes for storage
        backup_codes_hash = [bcrypt.hash(code) for code in backup_codes]

        # Create MFA config
        await self._mfa_repo.create_user_mfa(user_id, secret, backup_codes_hash)

        # Generate provisioning URI
        totp = pyotp.TOTP(secret)
        provisioning_uri = totp.provisioning_uri(name=username, issuer_name=self._issuer_name)

        logger.info(f"Generated MFA setup for user {user_id}")

        return {
            "secret": secret,
            "provisioning_uri": provisioning_uri,
            "backup_codes": backup_codes,
        }

    async def enable_mfa(self, user_id: str, code: str) -> bool:
        """Enable MFA after verifying initial code.

        Args:
            user_id: User identifier
            code: TOTP code to verify

        Returns:
            True if MFA enabled successfully
        """
        # Get MFA config
        config = await self._mfa_repo.get_user_mfa(user_id)
        if not config:
            logger.warning(f"MFA config not found for user {user_id}")
            return False

        # Verify code
        totp = pyotp.TOTP(config["secret"])
        if not totp.verify(code, valid_window=1):
            logger.warning(f"Invalid MFA code during enable for user {user_id}")
            return False

        # Enable MFA
        await self._mfa_repo.update_user_mfa(user_id, {"enabled": True})

        logger.info(f"MFA enabled for user {user_id}")
        return True

    async def verify_mfa_code(self, user_id: str, code: str) -> bool:
        """Verify an MFA code.

        Args:
            user_id: User identifier
            code: Code to verify (TOTP or backup)

        Returns:
            True if code is valid
        """
        # Get MFA config
        config = await self._mfa_repo.get_user_mfa(user_id)
        if not config or not config.get("enabled"):
            logger.warning(f"MFA not enabled for user {user_id}")
            return False

        # Try TOTP first
        totp = pyotp.TOTP(config["secret"])
        if totp.verify(code, valid_window=1):
            await self._mfa_repo.update_user_mfa(
                user_id, {"last_used": datetime.now(UTC).isoformat()}
            )
            logger.debug(f"Valid TOTP code for user {user_id}")
            return True

        # Try backup codes
        for code_hash in config.get("backup_codes_hash", []):
            if bcrypt.verify(code, code_hash):
                # Mark backup code as used
                if await self._mfa_repo.mark_backup_code_used(user_id, code_hash):
                    logger.info(f"Backup code used for user {user_id}")
                    return True

        logger.warning(f"Invalid MFA code for user {user_id}")
        return False

    async def disable_mfa(self, user_id: str) -> bool:
        """Disable MFA for a user.

        Args:
            user_id: User identifier

        Returns:
            True if disabled successfully
        """
        return await self._mfa_repo.delete_user_mfa(user_id)

    async def regenerate_backup_codes(self, user_id: str) -> list[str] | None:
        """Regenerate backup codes for a user.

        Args:
            user_id: User identifier

        Returns:
            New backup codes or None
        """
        # Get existing config
        config = await self._mfa_repo.get_user_mfa(user_id)
        if not config:
            return None

        # Generate new codes
        backup_codes = [secrets.token_hex(4).upper() for _ in range(self._backup_codes_count)]

        # Hash for storage
        backup_codes_hash = [bcrypt.hash(code) for code in backup_codes]

        # Create new config with same secret
        await self._mfa_repo.create_user_mfa(user_id, config["secret"], backup_codes_hash)

        # Re-enable if was enabled
        if config.get("enabled"):
            await self._mfa_repo.update_user_mfa(user_id, {"enabled": True})

        logger.info(f"Regenerated backup codes for user {user_id}")
        return backup_codes
