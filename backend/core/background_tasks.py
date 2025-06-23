"""Background task management for long-running services.

This module provides a simple, robust manager for asyncio background tasks
that integrates with the FastAPI application lifecycle.
"""

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class BackgroundTaskManager:
    """Manages background tasks with proper lifecycle and error handling."""

    def __init__(self):
        """Initialize the background task manager."""
        self._tasks: list[asyncio.Task] = []
        self._running = True

    def schedule(self, coro: Coroutine, name: str | None = None) -> asyncio.Task:
        """Schedule a coroutine to run as a background task.

        Args:
            coro: Coroutine to run
            name: Optional name for the task

        Returns:
            The created task
        """
        task = asyncio.create_task(coro)
        if name:
            task.set_name(name)

        self._tasks.append(task)
        task.add_done_callback(self._handle_task_completion)
        logger.info(f"Scheduled background task: {task.get_name()}")

        return task

    def _handle_task_completion(self, task: asyncio.Task) -> None:
        """Log exceptions from completed tasks."""
        try:
            task.result()  # This will re-raise any exception caught in the task
            logger.info(f"Background task {task.get_name()} finished successfully.")
        except asyncio.CancelledError:
            logger.warning(f"Background task {task.get_name()} was cancelled.")
        except Exception:
            logger.exception(f"Background task {task.get_name()} failed with an exception.")

        # Remove from tracked tasks
        if task in self._tasks:
            self._tasks.remove(task)

    async def shutdown(self) -> None:
        """Cancel all running background tasks during application shutdown."""
        self._running = False

        if not self._tasks:
            logger.info("No background tasks to shut down.")
            return

        logger.info(f"Shutting down {len(self._tasks)} background tasks...")

        # Cancel all tasks
        for task in self._tasks:
            task.cancel()

        # Wait for all to complete (or be cancelled)
        await asyncio.gather(*self._tasks, return_exceptions=True)

        self._tasks.clear()
        logger.info("Background tasks shut down complete.")

    @property
    def is_running(self) -> bool:
        """Check if the manager is still running."""
        return self._running

    @property
    def active_tasks(self) -> int:
        """Get count of active tasks."""
        return len(self._tasks)

    def get_task_status(self) -> list[dict[str, Any]]:
        """Get status of all managed tasks."""
        return [
            {
                "name": task.get_name(),
                "done": task.done(),
                "cancelled": task.cancelled(),
            }
            for task in self._tasks
        ]
