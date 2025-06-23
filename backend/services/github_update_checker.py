"""
GitHub Update Checker feature for the backend architecture.

Provides a background service to periodically check the latest release
version from GitHub and cache it for API use. This avoids client-side
rate limiting and centralizes update logic.
"""

import asyncio
import contextlib
import logging
import os
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_GITHUB_OWNER = "carpenike"
DEFAULT_GITHUB_REPO = "coachiq"
CHECK_INTERVAL = 3600  # seconds (1 hour)


def get_github_repo() -> tuple[str, str]:
    """Get the GitHub repo (owner, repo) from env or defaults."""
    owner = os.getenv("GITHUB_OWNER", DEFAULT_GITHUB_OWNER)
    repo = os.getenv("GITHUB_REPO", DEFAULT_GITHUB_REPO)
    return owner, repo


def build_github_api_url(owner: str, repo: str) -> str:
    """Build the GitHub API URL for latest release."""
    return f"https://api.github.com/repos/{owner}/{repo}/releases/latest"


class GitHubUpdateChecker:
    """
    Periodically checks the latest GitHub release and caches the result.

    Attributes:
        latest_version: The latest version string, or None if not fetched.
        last_checked: Timestamp of the last check attempt.
        last_success: Timestamp of the last successful check.
        error: Error message from the last failed check, if any.
        latest_release_info: Full metadata from the latest release, or None if not fetched.
    """

    def __init__(self) -> None:
        self.latest_version: str | None = None
        self.last_checked: float = 0
        self.last_success: float = 0
        self.error: str | None = None
        self.latest_release_info: dict[str, Any] | None = None
        self._task: asyncio.Task | None = None
        self._logger = logging.getLogger("github_update_checker")
        self.owner, self.repo = get_github_repo()
        self.api_url = build_github_api_url(self.owner, self.repo)

    async def start(self) -> None:
        """Start the background update checker task if not already running."""
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Stop the background update checker task."""
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _run(self) -> None:
        """Background loop: checks for updates every CHECK_INTERVAL seconds."""
        while True:
            await self.check_now()
            await asyncio.sleep(CHECK_INTERVAL)

    async def check_now(self) -> None:
        """Immediately check GitHub for the latest release version and update the cache."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(self.api_url)
                resp.raise_for_status()
                data = resp.json()
                tag = data.get("tag_name", "").lstrip("v")
                self.latest_version = tag
                self.last_success = time.time()
                self.error = None

                # Store useful metadata for the frontend
                self.latest_release_info = {
                    "tag_name": data.get("tag_name"),
                    "name": data.get("name"),
                    "body": data.get("body"),
                    "html_url": data.get("html_url"),
                    "published_at": data.get("published_at"),
                    "created_at": data.get("created_at"),
                    "assets": [
                        {
                            "name": a.get("name"),
                            "browser_download_url": a.get("browser_download_url"),
                            "size": a.get("size"),
                            "download_count": a.get("download_count"),
                        }
                        for a in data.get("assets", [])
                    ],
                    "tarball_url": data.get("tarball_url"),
                    "zipball_url": data.get("zipball_url"),
                    "prerelease": data.get("prerelease"),
                    "draft": data.get("draft"),
                    "author": (
                        {
                            "login": data.get("author", {}).get("login"),
                            "html_url": data.get("author", {}).get("html_url"),
                        }
                        if data.get("author")
                        else None
                    ),
                    "discussion_url": data.get("discussion_url"),
                }
                self._logger.info(f"Fetched latest GitHub version: {tag}")
        except Exception as e:
            self.error = str(e)
            self._logger.warning(f"Failed to fetch GitHub version: {e}")
        self.last_checked = time.time()

    async def force_check(self) -> None:
        """Force an immediate update check (for API use)."""
        await self.check_now()

    def get_status(self) -> dict[str, Any]:
        """
        Return the cached update check result and status, including release metadata.

        Returns:
            dict: Contains latest_version, last_checked, last_success, error,
            latest_release_info, repo, and api_url.
        """
        return {
            "latest_version": self.latest_version,
            "last_checked": self.last_checked,
            "last_success": self.last_success,
            "error": self.error,
            "latest_release_info": self.latest_release_info,
            "repo": f"{self.owner}/{self.repo}",
            "api_url": self.api_url,
        }


class GitHubUpdateCheckerFeature:
    """Feature wrapper for the GitHub update checker background service."""

    def __init__(
        self,
        name: str = "github_update_checker",
        enabled: bool = True,
        core: bool = False,
        config: dict[str, Any] | None = None,
        dependencies: list[str] | None = None,
        friendly_name: str | None = None,
        safety_classification: Any | None = None,
        log_state_transitions: bool = True,
    ) -> None:
        self.name = name
        self.enabled = enabled
        self.core = core
        self.config = config or {}
        self.dependencies = dependencies or []
        self.friendly_name = friendly_name or "GitHub Update Checker"
        self.log_state_transitions = log_state_transitions
        self._update_checker: GitHubUpdateChecker | None = None

    async def startup(self) -> None:
        """Start the GitHub update checker feature."""
        logger.info("Starting GitHub update checker feature")
        self._update_checker = GitHubUpdateChecker()
        await self._update_checker.start()

    async def shutdown(self) -> None:
        """Stop the GitHub update checker feature."""
        logger.info("Stopping GitHub update checker feature")
        if self._update_checker is not None:
            await self._update_checker.stop()
            self._update_checker = None

    @property
    def health(self) -> str:
        """
        Return the health status of the feature.

        Returns:
            - "healthy": Feature is functioning correctly
            - "degraded": Feature has non-critical issues
            - "failed": Feature has errors
        """
        if not self.enabled:
            return "healthy"  # Disabled is considered healthy

        if self._update_checker is None:
            return "degraded"  # Not initialized but not failing

        status = self._update_checker.get_status()
        if status["error"]:
            return "failed"
        if status["last_success"] and (status["last_checked"] - status["last_success"] < 7200):
            return "healthy"
        return "degraded"  # Outdated but not failing

    def get_update_checker(self) -> GitHubUpdateChecker | None:
        """Get the update checker instance."""
        return self._update_checker

    def get_status(self) -> dict[str, Any]:
        """Get the current status from the update checker."""
        if self._update_checker is None:
            return {"error": "Update checker not initialized"}
        return self._update_checker.get_status()

    async def force_check(self) -> None:
        """Force an immediate update check."""
        if self._update_checker is not None:
            await self._update_checker.force_check()


# Global instance for dependency injection
_github_update_checker_feature: GitHubUpdateCheckerFeature | None = None


def initialize_github_update_checker_feature(
    config: dict[str, Any] | None = None,
) -> GitHubUpdateCheckerFeature:
    """Initialize the global GitHub update checker feature instance."""
    global _github_update_checker_feature
    _github_update_checker_feature = GitHubUpdateCheckerFeature(config=config)
    return _github_update_checker_feature


def get_github_update_checker_feature() -> GitHubUpdateCheckerFeature:
    """Get the global GitHub update checker feature instance."""
    if _github_update_checker_feature is None:
        msg = "GitHub update checker feature not initialized"
        raise RuntimeError(msg)
    return _github_update_checker_feature


def register_github_update_checker_feature(
    name: str,
    enabled: bool,
    core: bool,
    config: dict[str, Any],
    dependencies: list[str],
    friendly_name: str | None = None,
    safety_classification: Any | None = None,
    log_state_transitions: bool = True,
) -> GitHubUpdateCheckerFeature:
    """
    Factory function for creating GitHub update checker feature instances.

    This function is called by the feature manager when loading features from YAML.

    Args:
        name: Feature name
        enabled: Whether the feature is enabled
        core: Whether this is a core feature
        config: Feature configuration from YAML
        dependencies: List of feature dependencies
        friendly_name: Human-readable name for the feature
        safety_classification: Safety classification for state validation
        log_state_transitions: Whether to log state transitions for audit

    Returns:
        Initialized GitHubUpdateCheckerFeature instance
    """
    feature = GitHubUpdateCheckerFeature(
        name=name,
        enabled=enabled,
        core=core,
        config=config,
        dependencies=dependencies,
        friendly_name=friendly_name,
        safety_classification=safety_classification,
        log_state_transitions=log_state_transitions,
    )

    # Store as global instance for dependency injection
    global _github_update_checker_feature
    _github_update_checker_feature = feature

    return feature
