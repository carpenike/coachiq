"""
ServiceRegistry for CoachIQ - Orchestrated Service Lifecycle Management

This module provides a centralized service registry that manages application-level
service dependencies, startup/shutdown orchestration, and health monitoring.
Designed to replace the service locator anti-pattern in main.py.

Key Features:
- Explicit dependency resolution using topological sorting
- Staged startup with parallel execution within stages
- Graceful shutdown in reverse order
- Runtime health monitoring
- Background task management
- Fail-fast initialization for safety-critical systems
"""

import asyncio
import logging
from collections import defaultdict
from enum import Enum
from graphlib import TopologicalSorter
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class ServiceStatus(Enum):
    """Service lifecycle status."""
    PENDING = "PENDING"
    STARTING = "STARTING"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


class ServiceRegistry:
    """
    Centralized service registry with dependency management and lifecycle orchestration.

    Replaces the service locator pattern with explicit dependency injection
    and provides structured startup/shutdown for safety-critical systems.
    """

    def __init__(self):
        self._services: Dict[str, Any] = {}
        self._service_status: Dict[str, ServiceStatus] = {}
        self._background_tasks: Set[asyncio.Task] = set()
        self._startup_stages: List[List[Tuple[str, Callable[[], Any], List[str]]]] = []
        self._startup_time: Optional[float] = None
        self._shutdown_complete: bool = False

    def register_startup_stage(self, services: List[Tuple[str, Callable[[], Any], List[str]]]):
        """
        Register a startup stage with services and their dependencies.

        Args:
            services: List of (service_name, init_function, dependencies) tuples
        """
        self._startup_stages.append(services)
        logger.debug(f"Registered startup stage with {len(services)} services")

    async def startup(self):
        """
        Execute orchestrated startup with dependency resolution and parallel execution.

        Raises:
            RuntimeError: If any service fails to initialize
        """
        start_time = asyncio.get_event_loop().time()
        logger.info("ServiceRegistry: Starting initialization...")

        try:
            total_services = sum(len(stage) for stage in self._startup_stages)
            logger.info(f"Initializing {total_services} services across {len(self._startup_stages)} stages")

            for stage_num, services_in_stage in enumerate(self._startup_stages):
                await self._execute_startup_stage(stage_num, services_in_stage)

            self._startup_time = asyncio.get_event_loop().time() - start_time
            logger.info(f"ServiceRegistry: All services initialized successfully in {self._startup_time:.2f}s")

        except Exception as e:
            logger.error(f"ServiceRegistry: Startup failed - {e}")
            # Attempt cleanup of partially initialized services
            await self._emergency_cleanup()
            raise

    async def _execute_startup_stage(self, stage_num: int, services_in_stage: List[Tuple[str, Callable, List[str]]]):
        """Execute a single startup stage with dependency resolution."""
        logger.info(f"--- Stage {stage_num}: {len(services_in_stage)} services ---")

        if not services_in_stage:
            return

        # Build dependency graph for this stage
        sorter = TopologicalSorter()
        stage_services = {}

        for name, init_func, deps in services_in_stage:
            # Validate dependencies are available
            for dep in deps:
                if dep not in self._services or self._service_status.get(dep) != ServiceStatus.HEALTHY:
                    raise RuntimeError(f"Service '{name}' dependency '{dep}' not available or not healthy")

            sorter.add(name, *deps)
            stage_services[name] = init_func
            self._service_status[name] = ServiceStatus.PENDING

        # Execute in dependency order with parallelization
        sorter.prepare()
        while sorter.is_active():
            ready_services = sorter.get_ready()
            if ready_services:
                logger.debug(f"Starting {len(ready_services)} services in parallel: {list(ready_services)}")

                # Start ready services in parallel
                tasks = [
                    self._start_service(name, stage_services[name])
                    for name in ready_services
                ]
                await asyncio.gather(*tasks)
                sorter.done(*ready_services)

    async def _start_service(self, name: str, init_func: Callable[[], Any]):
        """
        Start individual service with proper error handling and background task management.

        Args:
            name: Service name
            init_func: Service initialization function

        Raises:
            Exception: Re-raises any initialization errors for fail-fast behavior
        """
        try:
            logger.info(f"Initializing service: {name}...")
            self._service_status[name] = ServiceStatus.STARTING

            # Initialize the service
            if asyncio.iscoroutinefunction(init_func):
                service = await init_func()
            else:
                service = init_func()

            self._services[name] = service

            # Start background tasks if service supports them
            if hasattr(service, 'start_background_tasks'):
                logger.debug(f"Starting background tasks for service: {name}")
                task = asyncio.create_task(
                    service.start_background_tasks(),
                    name=f"{name}_background_tasks"
                )
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)

            self._service_status[name] = ServiceStatus.HEALTHY
            logger.info(f"✅ Service '{name}' started successfully")

        except Exception as e:
            self._service_status[name] = ServiceStatus.FAILED
            logger.error(f"❌ Service '{name}' failed to initialize: {e}")
            raise  # Fail-fast for startup errors

    async def shutdown(self):
        """
        Graceful shutdown in reverse order of startup.

        Cancels background tasks first, then shuts down services in reverse order.
        """
        if self._shutdown_complete:
            logger.warning("ServiceRegistry: Shutdown already completed")
            return

        logger.info("ServiceRegistry: Initiating graceful shutdown...")
        shutdown_start = asyncio.get_event_loop().time()

        try:
            # Cancel background tasks first
            if self._background_tasks:
                logger.info(f"Cancelling {len(self._background_tasks)} background tasks...")
                for task in self._background_tasks:
                    if not task.done():
                        task.cancel()

                # Wait for tasks to complete/cancel with timeout
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*self._background_tasks, return_exceptions=True),
                        timeout=5.0
                    )
                except asyncio.TimeoutError:
                    logger.warning("Some background tasks did not shutdown within timeout")

            # Shutdown services in reverse order of startup
            for stage in reversed(self._startup_stages):
                await self._shutdown_stage(stage)

            shutdown_time = asyncio.get_event_loop().time() - shutdown_start
            self._shutdown_complete = True
            logger.info(f"ServiceRegistry: Shutdown complete in {shutdown_time:.2f}s")

        except Exception as e:
            logger.error(f"ServiceRegistry: Error during shutdown - {e}")
            raise

    async def _shutdown_stage(self, stage: List[Tuple[str, Callable, List[str]]]):
        """Shutdown all services in a stage concurrently."""
        shutdown_tasks = []

        for name, _, _ in stage:
            service = self._services.get(name)
            if service and hasattr(service, 'shutdown'):
                logger.debug(f"Shutting down service: {name}")
                shutdown_tasks.append(self._shutdown_service(name, service))

        if shutdown_tasks:
            await asyncio.gather(*shutdown_tasks, return_exceptions=True)

    async def _shutdown_service(self, name: str, service: Any):
        """Shutdown individual service with error handling."""
        try:
            if asyncio.iscoroutinefunction(service.shutdown):
                await service.shutdown()
            else:
                service.shutdown()
            logger.debug(f"Service '{name}' shutdown successfully")
        except Exception as e:
            logger.warning(f"Service '{name}' shutdown error: {e}")

    async def _emergency_cleanup(self):
        """Emergency cleanup for failed startup."""
        logger.warning("ServiceRegistry: Performing emergency cleanup...")

        # Cancel any background tasks
        for task in self._background_tasks:
            if not task.done():
                task.cancel()

        # Attempt to shutdown any successfully started services
        for name, service in self._services.items():
            if self._service_status.get(name) == ServiceStatus.HEALTHY and hasattr(service, 'shutdown'):
                try:
                    if asyncio.iscoroutinefunction(service.shutdown):
                        await service.shutdown()
                    else:
                        service.shutdown()
                except Exception as e:
                    logger.warning(f"Emergency cleanup of '{name}' failed: {e}")

    def get_service(self, name: str) -> Any:
        """
        Retrieve a healthy service by name.

        Args:
            name: Service name

        Returns:
            The service instance

        Raises:
            LookupError: If service not found
            RuntimeError: If service not healthy
        """
        if name not in self._services:
            raise LookupError(f"Service '{name}' not found in registry")

        if self._service_status.get(name) != ServiceStatus.HEALTHY:
            current_status = self._service_status.get(name, ServiceStatus.PENDING)
            raise RuntimeError(f"Service '{name}' is not healthy: {current_status}")

        return self._services[name]

    def has_service(self, name: str) -> bool:
        """Check if a service is registered and healthy."""
        return (name in self._services and
                self._service_status.get(name) == ServiceStatus.HEALTHY)

    async def get_health_status(self) -> Dict[str, ServiceStatus]:
        """
        Get current health status of all services.

        Returns:
            Dictionary mapping service names to their current status
        """
        health = {}

        for name, service in self._services.items():
            if hasattr(service, 'check_health'):
                try:
                    status = await service.check_health()
                    health[name] = status
                except Exception as e:
                    logger.warning(f"Health check failed for '{name}': {e}")
                    health[name] = ServiceStatus.DEGRADED
            else:
                health[name] = self._service_status.get(name, ServiceStatus.PENDING)

        return health

    def get_service_count_by_status(self) -> Dict[ServiceStatus, int]:
        """Get count of services by status for monitoring."""
        counts = {status: 0 for status in ServiceStatus}
        for status in self._service_status.values():
            counts[status] += 1
        return counts

    def get_startup_metrics(self) -> Dict[str, Any]:
        """Get startup performance metrics."""
        return {
            "startup_time_seconds": self._startup_time,
            "total_services": len(self._services),
            "total_stages": len(self._startup_stages),
            "background_tasks": len(self._background_tasks),
            "service_counts": self.get_service_count_by_status()
        }

    def list_services(self) -> List[str]:
        """Get list of all registered service names."""
        return list(self._services.keys())

    def __repr__(self) -> str:
        """String representation for debugging."""
        healthy_count = sum(1 for status in self._service_status.values()
                          if status == ServiceStatus.HEALTHY)
        return (f"ServiceRegistry(services={len(self._services)}, "
                f"healthy={healthy_count}, "
                f"stages={len(self._startup_stages)})")
