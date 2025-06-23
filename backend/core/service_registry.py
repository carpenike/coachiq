"""
Enhanced ServiceRegistry with Advanced Dependency Resolution

This module extends ServiceRegistry with the enhanced dependency resolver,
providing better error messages, dependency visualization, and runtime validation.

Part of Phase 2F: Service Dependency Resolution Enhancement
"""

import asyncio
import inspect
import logging
import time
from collections import defaultdict
from collections.abc import Callable
from enum import Enum
from graphlib import TopologicalSorter
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from backend.core.service_dependency_resolver import (
    DependencyError,
    DependencyType,
    ServiceDependency,
    ServiceDependencyResolver,
)
from backend.core.service_lifecycle import (
    IServiceLifecycleListener,
    ServiceFailureReason,
    ServiceLifecycleManager,
)


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
        self._services: dict[str, Any] = {}
        self._service_status: dict[str, ServiceStatus] = {}
        self._background_tasks: set[asyncio.Task] = set()
        self._startup_stages: list[list[tuple[str, Callable[[], Any], list[str]]]] = []
        self._startup_time: float | None = None
        self._shutdown_complete: bool = False

    def register_startup_stage(self, services: list[tuple[str, Callable[[], Any], list[str]]]):
        """
        Register a startup stage with services and their dependencies.

        Args:
            services: List of (service_name, init_function, dependencies) tuples
        """
        self._startup_stages.append(services)

    async def startup(self):
        """
        Execute orchestrated startup with dependency resolution and parallel execution.

        Raises:
            RuntimeError: If any service fails to initialize
        """
        start_time = time.perf_counter()

        try:
            total_services = sum(len(stage) for stage in self._startup_stages)

            for stage_num, services_in_stage in enumerate(self._startup_stages):
                await self._execute_startup_stage(stage_num, services_in_stage)

            self._startup_time = time.perf_counter() - start_time

        except Exception as e:
            # Attempt cleanup of partially initialized services
            await self._emergency_cleanup()
            raise

    async def _execute_startup_stage(
        self, stage_num: int, services_in_stage: list[tuple[str, Callable, list[str]]]
    ):
        """Execute a single startup stage with dependency resolution."""
        if not services_in_stage:
            return

        # Build dependency graph for this stage
        sorter = TopologicalSorter()
        stage_services = {}

        for name, init_func, deps in services_in_stage:
            # Validate dependencies are available
            for dep in deps:
                if (
                    dep not in self._services
                    or self._service_status.get(dep) != ServiceStatus.HEALTHY
                ):
                    raise RuntimeError(
                        f"Service '{name}' dependency '{dep}' not available or not healthy"
                    )

            sorter.add(name, *deps)
            stage_services[name] = init_func
            self._service_status[name] = ServiceStatus.PENDING

        # Execute in dependency order with parallelization
        sorter.prepare()
        while sorter.is_active():
            ready_services = sorter.get_ready()
            if ready_services:
                # Start ready services in parallel
                tasks = [self._start_service(name, stage_services[name]) for name in ready_services]
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
            self._service_status[name] = ServiceStatus.STARTING

            # Initialize the service
            if asyncio.iscoroutinefunction(init_func):
                service = await init_func()
            else:
                service = init_func()

            self._services[name] = service

            # Start background tasks if service supports them
            if hasattr(service, "start_background_tasks"):
                task = asyncio.create_task(
                    service.start_background_tasks(), name=f"{name}_background_tasks"
                )
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)

            self._service_status[name] = ServiceStatus.HEALTHY

        except Exception as e:
            self._service_status[name] = ServiceStatus.FAILED
            raise  # Fail-fast for startup errors

    async def shutdown(self):
        """
        Graceful shutdown in reverse order of startup.

        Cancels background tasks first, then shuts down services in reverse order.
        """
        if self._shutdown_complete:
            return

        shutdown_start = time.perf_counter()

        try:
            # Cancel background tasks first
            if self._background_tasks:
                for task in self._background_tasks:
                    if not task.done():
                        task.cancel()

                # Wait for tasks to complete/cancel with timeout
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*self._background_tasks, return_exceptions=True), timeout=5.0
                    )
                except TimeoutError:
                    pass

            # Shutdown services in reverse order of startup
            for stage in reversed(self._startup_stages):
                await self._shutdown_stage(stage)

            self._shutdown_complete = True

        except Exception as e:
            pass

    async def _shutdown_stage(self, services_in_stage: list[tuple[str, Callable, list[str]]]):
        """Shutdown services in a stage."""
        for service_name, _, _ in reversed(services_in_stage):
            await self._shutdown_service(service_name)

    async def _shutdown_service(self, name: str):
        """Shutdown individual service."""
        try:
            service = self._services.get(name)
            if service and hasattr(service, "shutdown"):
                if asyncio.iscoroutinefunction(service.shutdown):
                    await service.shutdown()
                else:
                    service.shutdown()
        except Exception:
            pass

    async def _emergency_cleanup(self):
        """Emergency cleanup of partially initialized services."""
        for name in list(self._services.keys()):
            try:
                await self._shutdown_service(name)
            except Exception:
                pass

    def has_service(self, service_name: str) -> bool:
        """Check if a service is registered and healthy."""
        return (
            service_name in self._services
            and self._service_status.get(service_name) == ServiceStatus.HEALTHY
        )

    def get_service(self, service_name: str) -> Any:
        """Get a service by name."""
        if not self.has_service(service_name):
            raise RuntimeError(f"Service '{service_name}' not available")
        return self._services[service_name]


logger = logging.getLogger(__name__)


class ServiceDefinition:
    """Enhanced service definition with dependency metadata."""

    def __init__(
        self,
        name: str,
        init_func: Callable[[], Any],
        dependencies: list[str | ServiceDependency] | None = None,
        tags: set[str] | None = None,
        description: str | None = None,
        health_check: Callable[[], bool] | None = None,
    ):
        self.name = name
        self.init_func = init_func
        self.tags = tags or set()
        self.description = description
        self.health_check = health_check

        # Convert simple string dependencies to ServiceDependency objects
        self.dependencies: list[ServiceDependency] = []
        if dependencies:
            for dep in dependencies:
                if isinstance(dep, str):
                    self.dependencies.append(ServiceDependency(name=dep))
                else:
                    self.dependencies.append(dep)


class EnhancedServiceRegistry(ServiceRegistry):
    """
    ServiceRegistry with enhanced dependency resolution capabilities.

    Improvements:
    - Advanced dependency resolver with circular detection
    - Better error messages with available services
    - Dependency visualization and reporting
    - Runtime dependency validation
    - Service tagging and categorization
    """

    def __init__(self):
        super().__init__()
        self._resolver = ServiceDependencyResolver()
        self._service_definitions: dict[str, ServiceDefinition] = {}
        self._startup_errors: dict[str, Exception] = {}
        self._dependency_report: str | None = None
        self._lifecycle_manager = ServiceLifecycleManager()
        self._service_timings: dict[str, float] = {}  # Track individual service startup times

    def register_service(
        self,
        name: str,
        init_func: Callable[[], Any],
        dependencies: list[str | ServiceDependency] | None = None,
        tags: set[str] | None = None,
        description: str | None = None,
        health_check: Callable[[], bool] | None = None,
    ) -> None:
        """
        Register a service with enhanced metadata.

        Args:
            name: Service name
            init_func: Service initialization function
            dependencies: Service dependencies (strings or ServiceDependency objects)
            tags: Service tags for categorization
            description: Human-readable service description
            health_check: Optional health check function
        """
        definition = ServiceDefinition(
            name=name,
            init_func=init_func,
            dependencies=dependencies,
            tags=tags,
            description=description,
            health_check=health_check,
        )

        self._service_definitions[name] = definition
        self._resolver.add_service(name, definition.dependencies)

        logger.debug(
            f"Registered service '{name}' with {len(definition.dependencies)} dependencies"
        )

    def register_services_batch(self, services: list[ServiceDefinition]) -> None:
        """
        Register multiple services at once.

        Args:
            services: List of ServiceDefinition objects
        """
        for service in services:
            self.register_service(
                name=service.name,
                init_func=service.init_func,
                dependencies=[d.name for d in service.dependencies],
                tags=service.tags,
                description=service.description,
                health_check=service.health_check,
            )

    async def startup_all(self) -> None:
        """
        Execute orchestrated startup with enhanced dependency resolution.

        Raises:
            DependencyError: If dependency resolution fails
            RuntimeError: If any service fails to initialize
        """
        start_time = time.perf_counter()
        logger.info("Enhanced ServiceRegistry: Starting initialization...")

        try:
            # Resolve dependencies and calculate stages
            stages = self._resolver.resolve_dependencies()
            self._dependency_report = self._resolver.get_dependency_report()

            # Log dependency report
            logger.info("Dependency Resolution Complete:")
            for line in self._dependency_report.split("\n"):
                if line.strip():
                    logger.info(f"  {line}")

            total_services = len(self._service_definitions)
            logger.info(f"Initializing {total_services} services across {len(stages)} stages")

            # Execute stages
            for stage_num in sorted(stages.keys()):
                await self._execute_enhanced_stage(stage_num, stages[stage_num])

            self._startup_time = time.perf_counter() - start_time
            logger.info(
                f"Enhanced ServiceRegistry: All services initialized successfully "
                f"in {self._startup_time:.2f}s"
            )

            # Validate runtime dependencies
            self._validate_runtime_dependencies()

        except DependencyError as e:
            logger.error(f"Dependency resolution failed: {e}")
            await self._emergency_cleanup()
            raise
        except Exception as e:
            logger.error(f"ServiceRegistry startup failed: {e}")
            await self._emergency_cleanup()
            raise

    async def _execute_enhanced_stage(self, stage_num: int, service_names: list[str]) -> None:
        """Execute a startup stage with enhanced error handling."""
        logger.info(f"--- Stage {stage_num}: {len(service_names)} services ---")
        logger.info(f"    Services: {', '.join(sorted(service_names))}")

        # Start services in parallel
        tasks = []
        for name in service_names:
            if name in self._service_definitions:
                definition = self._service_definitions[name]
                task = self._start_service_enhanced(name, definition)
                tasks.append(task)

        # Wait for all services in stage to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check for failures
        failures = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                service_name = service_names[i]
                self._startup_errors[service_name] = result
                failures.append((service_name, result))

        if failures:
            # Generate detailed error report
            error_lines = ["Service startup failures:"]
            for name, error in failures:
                error_lines.append(f"  • {name}: {error}")

                # Show impacted services
                impacted = self._resolver.get_impacted_services(name)
                if impacted:
                    error_lines.append(f"    Impacted services: {', '.join(sorted(impacted))}")

            error_message = "\n".join(error_lines)
            logger.error(error_message)
            raise RuntimeError(error_message)

    async def _start_service_enhanced(self, name: str, definition: ServiceDefinition) -> None:
        """Start a service with enhanced error context and performance monitoring."""
        service_start_time = time.time()

        try:
            logger.info(f"Initializing service: {name}")
            if definition.description:
                logger.info(f"  Description: {definition.description}")
            if definition.tags:
                logger.info(f"  Tags: {', '.join(sorted(definition.tags))}")

            self._service_status[name] = ServiceStatus.STARTING

            # Verify dependencies are available
            dep_check_start = time.time()
            for dep in definition.dependencies:
                if dep.type == DependencyType.REQUIRED:
                    if not self.has_service(dep.name):
                        raise RuntimeError(
                            f"Required dependency '{dep.name}' not available. "
                            f"Current services: {', '.join(self.list_services())}"
                        )
            dep_check_time = (time.time() - dep_check_start) * 1000

            # Collect dependency instances for injection
            dependency_kwargs = {}
            for dep in definition.dependencies:
                # Get the parameter name (use inject_as if specified, otherwise convert hyphen to underscore)
                param_name = dep.inject_as if dep.inject_as else dep.name.replace("-", "_")

                # Check if dependency is available
                if self.has_service(dep.name):
                    dependency_kwargs[param_name] = self.get_service(dep.name)
                elif dep.type == DependencyType.REQUIRED:
                    raise RuntimeError(
                        f"Required dependency '{dep.name}' not available for injection. "
                        f"Current services: {', '.join(self.list_services())}"
                    )
                # Optional dependencies are skipped if not available
                # The init function should handle their absence

            # Check if the init function can accept the dependencies
            # This provides backward compatibility for functions that don't accept kwargs
            try:
                sig = inspect.signature(definition.init_func)
                # Filter kwargs to only include parameters the function accepts
                accepted_params = set(sig.parameters.keys())
                filtered_kwargs = {
                    k: v for k, v in dependency_kwargs.items() if k in accepted_params
                }

                # Log dependency injection details
                if filtered_kwargs:
                    logger.debug(
                        f"  Injecting dependencies for {name}: {list(filtered_kwargs.keys())}"
                    )
                if dependency_kwargs and not filtered_kwargs:
                    logger.debug(
                        f"  No dependencies injected for {name} (function doesn't accept parameters)"
                    )
            except (ValueError, TypeError):
                # Can't inspect signature (e.g., built-ins), assume no DI
                filtered_kwargs = {}
                logger.debug(f"  Cannot inspect signature for {name}, skipping DI")

            # Initialize the service (measure initialization time)
            init_start_time = time.time()
            if asyncio.iscoroutinefunction(definition.init_func):
                service = await definition.init_func(**filtered_kwargs)
            else:
                service = definition.init_func(**filtered_kwargs)
            init_time = (time.time() - init_start_time) * 1000

            self._services[name] = service

            # Start background tasks if supported
            if hasattr(service, "start_background_tasks"):
                logger.debug(f"Starting background tasks for service: {name}")
                task = asyncio.create_task(
                    service.start_background_tasks(), name=f"{name}_background_tasks"
                )
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)

            # Call startup method if available
            if hasattr(service, "startup"):
                logger.debug(f"Calling startup method for service: {name}")
                if asyncio.iscoroutinefunction(service.startup):
                    await service.startup()
                else:
                    service.startup()

            self._service_status[name] = ServiceStatus.HEALTHY

            # Record timing metrics
            total_time = (time.time() - service_start_time) * 1000
            self._service_timings[name] = total_time

            logger.info(
                f"✅ Service '{name}' started successfully in {total_time:.1f}ms "
                f"(init: {init_time:.1f}ms, deps: {dep_check_time:.1f}ms)"
            )

            # Record timing with startup monitor if available
            try:
                from backend.middleware.startup_monitoring import get_startup_monitor

                monitor = get_startup_monitor()
                monitor.record_service_timing(name, total_time)
            except ImportError:
                pass  # Startup monitoring not available

            # Notify lifecycle listeners
            await self._lifecycle_manager.notify_service_started(
                service_name=name,
                metadata={
                    "tags": list(definition.tags) if definition.tags else [],
                    "startup_time_ms": total_time,
                    "init_time_ms": init_time,
                    "dep_check_time_ms": dep_check_time,
                },
            )

        except Exception as e:
            self._service_status[name] = ServiceStatus.FAILED
            logger.error(f"❌ Service '{name}' failed to initialize: {e}")

            # Add context about dependencies
            if definition.dependencies:
                dep_status = []
                for dep in definition.dependencies:
                    status = self._service_status.get(dep.name, "NOT_FOUND")
                    dep_status.append(f"{dep.name}={status}")
                logger.error(f"  Dependency status: {', '.join(dep_status)}")

            # Notify lifecycle listeners
            await self._handle_service_failure(name, e, ServiceFailureReason.INITIALIZATION_ERROR)

            raise

    def _validate_runtime_dependencies(self) -> None:
        """Validate runtime dependencies after startup."""
        available = set(self._services.keys())
        missing = self._resolver.validate_runtime_dependencies(available)

        if missing:
            logger.warning("Runtime dependency validation warnings:")
            for service, deps in missing.items():
                logger.warning(
                    f"  Service '{service}' missing runtime dependencies: {', '.join(deps)}"
                )

    def get_dependency_report(self) -> str:
        """
        Get the dependency resolution report.

        Returns:
            Human-readable dependency report
        """
        if self._dependency_report:
            return self._dependency_report

        # Generate report if not yet resolved
        try:
            self._resolver.resolve_dependencies()
            self._dependency_report = self._resolver.get_dependency_report()
            return self._dependency_report
        except DependencyError as e:
            return f"Dependency resolution failed: {e}"

    def get_startup_order(self) -> list[str]:
        """
        Get the calculated startup order.

        Returns:
            List of service names in startup order
        """
        try:
            self._resolver.resolve_dependencies()
            return self._resolver.get_startup_order()
        except DependencyError:
            return []

    def get_service_timings(self) -> dict[str, float]:
        """
        Get service startup timing metrics.

        Returns:
            Dictionary mapping service names to startup times in milliseconds
        """
        return self._service_timings.copy()

    def get_startup_metrics(self) -> dict[str, Any]:
        """
        Get comprehensive startup metrics and analysis.

        Returns:
            Dictionary containing startup performance metrics
        """
        total_time = sum(self._service_timings.values())
        service_count = len(self._service_timings)

        metrics = {
            "total_startup_time_ms": total_time,
            "service_count": service_count,
            "average_service_time_ms": total_time / service_count if service_count > 0 else 0,
            "slowest_services": sorted(
                self._service_timings.items(), key=lambda x: x[1], reverse=True
            )[:5],
            "service_timings": self._service_timings.copy(),
            "startup_errors": {name: str(error) for name, error in self._startup_errors.items()},
        }

        return metrics

    def export_dependency_diagram(self) -> str:
        """
        Export dependency graph as Mermaid diagram.

        Returns:
            Mermaid diagram markup
        """
        try:
            self._resolver.resolve_dependencies()
            return self._resolver.export_mermaid_diagram()
        except DependencyError as e:
            return f"// Dependency resolution failed: {e}"

    def get_services_by_tag(self, tag: str) -> list[str]:
        """
        Get all services with a specific tag.

        Args:
            tag: Tag to filter by

        Returns:
            List of service names with the tag
        """
        return [
            name for name, definition in self._service_definitions.items() if tag in definition.tags
        ]

    def get_service_info(self, name: str) -> dict[str, Any]:
        """
        Get detailed information about a service.

        Args:
            name: Service name

        Returns:
            Service information dictionary
        """
        if name not in self._service_definitions:
            return {"error": f"Service '{name}' not found"}

        definition = self._service_definitions[name]
        status = self._service_status.get(name, ServiceStatus.PENDING)

        # Get dependency status
        dep_info = []
        for dep in definition.dependencies:
            dep_status = self._service_status.get(dep.name, ServiceStatus.PENDING)
            dep_info.append(
                {
                    "name": dep.name,
                    "type": dep.type.value,
                    "status": dep_status.value,
                    "fallback": dep.fallback,
                }
            )

        # Get impacted services
        impacted = list(self._resolver.get_impacted_services(name))

        return {
            "name": name,
            "status": status.value,
            "description": definition.description,
            "tags": list(definition.tags),
            "dependencies": dep_info,
            "impacted_services": impacted,
            "has_health_check": definition.health_check is not None,
            "startup_error": str(self._startup_errors.get(name))
            if name in self._startup_errors
            else None,
        }

    async def check_service_health(self, name: str) -> ServiceStatus:
        """
        Check health of a specific service.

        Args:
            name: Service name

        Returns:
            Service health status
        """
        if name not in self._services:
            return ServiceStatus.PENDING

        definition = self._service_definitions.get(name)
        if definition and definition.health_check:
            try:
                if asyncio.iscoroutinefunction(definition.health_check):
                    is_healthy = await definition.health_check()
                else:
                    is_healthy = definition.health_check()

                return ServiceStatus.HEALTHY if is_healthy else ServiceStatus.DEGRADED
            except Exception as e:
                logger.warning(f"Health check failed for '{name}': {e}")
                return ServiceStatus.DEGRADED

        # Fall back to stored status
        return self._service_status.get(name, ServiceStatus.PENDING)

    def get_enhanced_metrics(self) -> dict[str, Any]:
        """Get enhanced startup and health metrics."""
        base_metrics = self.get_startup_metrics()

        # Add enhanced metrics
        base_metrics.update(
            {
                "total_stages": len(self._resolver._stages),
                "services_by_tag": {
                    tag: len(self.get_services_by_tag(tag))
                    for tag in ("core", "feature", "integration", "api")
                },
                "startup_errors": len(self._startup_errors),
                "dependency_resolution": {
                    "total_dependencies": sum(
                        len(d.dependencies) for d in self._service_definitions.values()
                    ),
                    "max_depth": max(
                        (node.depth for node in self._resolver._nodes.values()), default=0
                    ),
                },
            }
        )

        return base_metrics

    def add_lifecycle_listener(
        self, listener: IServiceLifecycleListener, priority: int = 0
    ) -> None:
        """
        Add a service lifecycle event listener.

        Args:
            listener: The listener to add
            priority: Higher priority listeners are notified first
        """
        self._lifecycle_manager.add_listener(listener, priority)

    def remove_lifecycle_listener(self, listener: IServiceLifecycleListener) -> None:
        """Remove a service lifecycle event listener."""
        self._lifecycle_manager.remove_listener(listener)

    async def _handle_service_failure(
        self,
        name: str,
        error: Exception,
        reason: ServiceFailureReason = ServiceFailureReason.RUNTIME_ERROR,
    ) -> None:
        """
        Handle service failure with lifecycle notifications.

        CRITICAL: This includes synchronous notification for safety transitions.
        """
        # Update status
        self._service_status[name] = ServiceStatus.FAILED

        # Notify listeners synchronously (blocking for safety)
        self._lifecycle_manager.notify_service_failed(
            service_name=name,
            reason=reason,
            error_message=str(error),
            metadata={
                "exception_type": type(error).__name__,
                "impacted_services": list(self._resolver.get_impacted_services(name)),
            },
        )

        # Log the failure
        logger.error(f"Service '{name}' failed: {error}", exc_info=True)

    async def stop_service(self, name: str) -> None:
        """
        Stop a service with lifecycle notifications.

        Args:
            name: Service name to stop
        """
        if name not in self._services:
            logger.warning(f"Cannot stop non-existent service: {name}")
            return

        try:
            # Notify pre-shutdown
            await self._lifecycle_manager.notify_pre_shutdown(
                service_name=name,
                metadata={"status": self._service_status.get(name, ServiceStatus.PENDING).value},
            )

            # Shutdown the service if it has a shutdown method
            service = self._services.get(name)
            if service and hasattr(service, "shutdown"):
                if asyncio.iscoroutinefunction(service.shutdown):
                    await service.shutdown()
                else:
                    service.shutdown()

            # Remove from registry
            del self._services[name]
            self._service_status[name] = ServiceStatus.PENDING

            # Notify stopped
            await self._lifecycle_manager.notify_service_stopped(service_name=name)

        except Exception as e:
            # Handle failure during shutdown
            await self._handle_service_failure(name, e, ServiceFailureReason.SHUTDOWN_ERROR)
            raise

    async def restart_service(self, name: str) -> None:
        """
        Restart a service with lifecycle notifications.

        Args:
            name: Service name to restart
        """
        if name not in self._service_definitions:
            raise ValueError(f"Unknown service: {name}")

        # Stop the service
        await self.stop_service(name)

        # Re-start the service
        definition = self._service_definitions[name]
        try:
            await self._start_service_enhanced(name, definition)

            # Notify started
            await self._lifecycle_manager.notify_service_started(
                service_name=name, metadata={"restart": True}
            )

        except Exception as e:
            await self._handle_service_failure(name, e, ServiceFailureReason.INITIALIZATION_ERROR)
            raise
