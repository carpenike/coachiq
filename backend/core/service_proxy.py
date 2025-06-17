"""
ServiceProxy Pattern Implementation for CoachIQ

Provides a clean abstraction layer for service access with:
- Lazy loading and caching
- Health checks and service validation
- Graceful fallbacks and error handling
- Circuit breaker pattern for resilience
- Performance monitoring and metrics

This pattern eliminates direct dependencies on FastAPI Request objects
and provides a more testable, maintainable service access layer.

Phase 2O: Service Proxy Pattern Implementation
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Generic, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar('T')


class CircuitState(Enum):
    """Circuit breaker states for service resilience."""
    CLOSED = "CLOSED"      # Normal operation
    OPEN = "OPEN"         # Service failing, requests blocked
    HALF_OPEN = "HALF_OPEN"  # Testing if service recovered


@dataclass
class ServiceMetrics:
    """Metrics for service access and performance."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    avg_response_time: float = 0.0
    last_success_time: Optional[float] = None
    last_failure_time: Optional[float] = None
    cache_hits: int = 0
    cache_misses: int = 0

    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage."""
        if self.total_requests == 0:
            return 100.0
        return (self.successful_requests / self.total_requests) * 100.0

    @property
    def failure_rate(self) -> float:
        """Calculate failure rate percentage."""
        return 100.0 - self.success_rate


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""
    failure_threshold: int = 5  # Failures before opening circuit
    recovery_timeout: float = 30.0  # Seconds before trying half-open
    success_threshold: int = 3  # Successes to close circuit from half-open
    timeout: float = 5.0  # Timeout for service calls


class ServiceProvider(ABC, Generic[T]):
    """Abstract base class for service providers."""

    @abstractmethod
    async def get_service(self) -> T:
        """Get the service instance."""
        pass

    @abstractmethod
    async def check_health(self) -> bool:
        """Check if the service is healthy."""
        pass

    @property
    @abstractmethod
    def service_name(self) -> str:
        """Get the service name for logging and metrics."""
        pass


class ServiceProxy(Generic[T]):
    """
    Service proxy with lazy loading, caching, health checks, and circuit breaker.

    Provides a clean abstraction layer that eliminates direct FastAPI Request
    dependencies and adds resilience patterns.
    """

    def __init__(
        self,
        provider: ServiceProvider[T],
        cache_ttl: float = 300.0,  # 5 minutes default cache
        circuit_config: Optional[CircuitBreakerConfig] = None,
    ):
        self.provider = provider
        self.cache_ttl = cache_ttl
        self.circuit_config = circuit_config or CircuitBreakerConfig()

        # Circuit breaker state
        self.circuit_state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.success_count = 0

        # Caching
        self._cached_service: Optional[T] = None
        self._cache_timestamp = 0.0

        # Metrics
        self.metrics = ServiceMetrics()

        # Lock for thread safety
        self._lock = asyncio.Lock()

    async def get(self) -> T:
        """
        Get the service with caching, health checks, and circuit breaker.

        Returns:
            The service instance

        Raises:
            ServiceUnavailableError: If service is unavailable
            CircuitOpenError: If circuit breaker is open
        """
        async with self._lock:
            start_time = time.time()
            self.metrics.total_requests += 1

            try:
                # Check circuit breaker
                await self._check_circuit_breaker()

                # Try cache first
                if self._is_cache_valid():
                    self.metrics.cache_hits += 1
                    logger.debug(f"ServiceProxy cache hit for {self.provider.service_name}")
                    # Type checker: we know this is not None because _is_cache_valid() checks it
                    assert self._cached_service is not None
                    return self._cached_service

                self.metrics.cache_misses += 1

                # Get fresh service instance
                service = await self._get_fresh_service()

                # Update cache
                self._cached_service = service
                self._cache_timestamp = time.time()

                # Record success
                self._record_success(time.time() - start_time)

                return service

            except Exception as e:
                self._record_failure(time.time() - start_time)
                logger.error(f"ServiceProxy failed to get {self.provider.service_name}: {e}")
                raise

    async def get_with_fallback(self, fallback: Callable[[], T]) -> T:
        """
        Get service with a fallback function if service is unavailable.

        Args:
            fallback: Function to call if service is unavailable

        Returns:
            Service instance or fallback result
        """
        try:
            return await self.get()
        except Exception as e:
            logger.warning(
                f"ServiceProxy fallback triggered for {self.provider.service_name}: {e}"
            )
            if asyncio.iscoroutinefunction(fallback):
                return await fallback()
            else:
                return fallback()

    async def check_health(self) -> bool:
        """
        Check if the proxied service is healthy.

        Returns:
            True if service is healthy, False otherwise
        """
        try:
            return await self.provider.check_health()
        except Exception as e:
            logger.warning(f"Health check failed for {self.provider.service_name}: {e}")
            return False

    def invalidate_cache(self) -> None:
        """Invalidate the cached service instance."""
        self._cached_service = None
        self._cache_timestamp = 0.0
        logger.debug(f"ServiceProxy cache invalidated for {self.provider.service_name}")

    def get_metrics(self) -> ServiceMetrics:
        """Get current metrics for the service proxy."""
        return self.metrics

    def reset_circuit_breaker(self) -> None:
        """Manually reset the circuit breaker to closed state."""
        self.circuit_state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        logger.info(f"Circuit breaker reset for {self.provider.service_name}")

    # Private methods

    def _is_cache_valid(self) -> bool:
        """Check if the cached service is still valid."""
        if self._cached_service is None:
            return False

        age = time.time() - self._cache_timestamp
        return age < self.cache_ttl

    async def _get_fresh_service(self) -> T:
        """Get a fresh service instance from the provider."""
        try:
            # Apply timeout
            service = await asyncio.wait_for(
                self.provider.get_service(),
                timeout=self.circuit_config.timeout
            )

            # Verify service health
            if not await self.provider.check_health():
                raise ServiceUnavailableError(
                    f"Service {self.provider.service_name} health check failed"
                )

            return service

        except asyncio.TimeoutError:
            raise ServiceUnavailableError(
                f"Service {self.provider.service_name} timed out after "
                f"{self.circuit_config.timeout}s"
            )

    async def _check_circuit_breaker(self) -> None:
        """Check and update circuit breaker state."""
        current_time = time.time()

        if self.circuit_state == CircuitState.OPEN:
            # Check if we should try half-open
            if current_time - self.last_failure_time >= self.circuit_config.recovery_timeout:
                self.circuit_state = CircuitState.HALF_OPEN
                self.success_count = 0
                logger.info(f"Circuit breaker half-open for {self.provider.service_name}")
            else:
                raise CircuitOpenError(
                    f"Circuit breaker open for {self.provider.service_name}"
                )

        elif self.circuit_state == CircuitState.HALF_OPEN:
            # In half-open, we allow limited requests to test recovery
            pass

    def _record_success(self, response_time: float) -> None:
        """Record a successful service call."""
        self.metrics.successful_requests += 1
        self.metrics.last_success_time = time.time()

        # Update average response time
        total_time = self.metrics.avg_response_time * (self.metrics.successful_requests - 1)
        self.metrics.avg_response_time = (total_time + response_time) / self.metrics.successful_requests

        # Handle circuit breaker state
        if self.circuit_state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.circuit_config.success_threshold:
                self.circuit_state = CircuitState.CLOSED
                self.failure_count = 0
                logger.info(f"Circuit breaker closed for {self.provider.service_name}")

        elif self.circuit_state == CircuitState.CLOSED:
            # Reset failure count on success
            self.failure_count = 0

    def _record_failure(self, response_time: float) -> None:
        """Record a failed service call."""
        self.metrics.failed_requests += 1
        self.metrics.last_failure_time = time.time()
        self.last_failure_time = time.time()

        # Handle circuit breaker state
        if self.circuit_state in (CircuitState.CLOSED, CircuitState.HALF_OPEN):
            self.failure_count += 1

            if self.failure_count >= self.circuit_config.failure_threshold:
                self.circuit_state = CircuitState.OPEN
                logger.warning(
                    f"Circuit breaker opened for {self.provider.service_name} "
                    f"after {self.failure_count} failures"
                )


class ServiceRegistry_Provider(ServiceProvider[Any]):
    """Service provider that uses ServiceRegistry for service resolution."""

    def __init__(self, service_name: str, service_registry_getter: Callable[[], Any]):
        self._service_name = service_name
        self._service_registry_getter = service_registry_getter

    async def get_service(self) -> Any:
        """Get service from ServiceRegistry."""
        registry = self._service_registry_getter()
        return registry.get_service(self._service_name)

    async def check_health(self) -> bool:
        """Check service health via ServiceRegistry."""
        try:
            registry = self._service_registry_getter()
            return registry.has_service(self._service_name)
        except Exception:
            return False

    @property
    def service_name(self) -> str:
        return self._service_name


class AppState_Provider(ServiceProvider[Any]):
    """Service provider that uses app.state for service resolution (legacy fallback)."""

    def __init__(self, service_name: str, app_state_getter: Callable[[], Any]):
        self._service_name = service_name
        self._app_state_getter = app_state_getter

    async def get_service(self) -> Any:
        """Get service from app.state."""
        app_state = self._app_state_getter()
        if hasattr(app_state, self._service_name):
            return getattr(app_state, self._service_name)
        raise ServiceUnavailableError(f"Service {self._service_name} not found in app.state")

    async def check_health(self) -> bool:
        """Check if service exists in app.state."""
        try:
            app_state = self._app_state_getter()
            return hasattr(app_state, self._service_name)
        except Exception:
            return False

    @property
    def service_name(self) -> str:
        return self._service_name


class CompositeServiceProvider(ServiceProvider[T]):
    """
    Composite provider that tries multiple providers in order.

    Useful for providing ServiceRegistry-first with app.state fallback.
    """

    def __init__(self, service_name: str, providers: list[ServiceProvider[T]]):
        self._service_name = service_name
        self.providers = providers

    async def get_service(self) -> T:
        """Try providers in order until one succeeds."""
        last_exception = None

        for provider in self.providers:
            try:
                return await provider.get_service()
            except Exception as e:
                last_exception = e
                continue

        # All providers failed
        raise ServiceUnavailableError(
            f"All providers failed for {self._service_name}. Last error: {last_exception}"
        )

    async def check_health(self) -> bool:
        """Return True if any provider is healthy."""
        for provider in self.providers:
            try:
                if await provider.check_health():
                    return True
            except Exception:
                continue
        return False

    @property
    def service_name(self) -> str:
        return self._service_name


class ServiceProxyManager:
    """
    Manages a collection of service proxies with shared configuration.

    Provides centralized management of service proxies and their lifecycles.
    """

    def __init__(self, default_cache_ttl: float = 300.0):
        self.default_cache_ttl = default_cache_ttl
        self._proxies: Dict[str, ServiceProxy] = {}
        self._metrics_cache: Dict[str, ServiceMetrics] = {}

    def create_proxy(
        self,
        service_name: str,
        provider: ServiceProvider,
        cache_ttl: Optional[float] = None,
        circuit_config: Optional[CircuitBreakerConfig] = None,
    ) -> ServiceProxy:
        """
        Create and register a service proxy.

        Args:
            service_name: Unique name for the service
            provider: Service provider implementation
            cache_ttl: Cache TTL override (uses default if not provided)
            circuit_config: Circuit breaker config override

        Returns:
            The created service proxy
        """
        if service_name in self._proxies:
            logger.warning(f"Service proxy for {service_name} already exists, replacing")

        proxy = ServiceProxy(
            provider=provider,
            cache_ttl=cache_ttl or self.default_cache_ttl,
            circuit_config=circuit_config,
        )

        self._proxies[service_name] = proxy
        logger.debug(f"Created service proxy for {service_name}")

        return proxy

    def get_proxy(self, service_name: str) -> Optional[ServiceProxy]:
        """Get a service proxy by name."""
        return self._proxies.get(service_name)

    def invalidate_all_caches(self) -> None:
        """Invalidate all service caches."""
        for proxy in self._proxies.values():
            proxy.invalidate_cache()
        logger.info("Invalidated all service proxy caches")

    def reset_all_circuit_breakers(self) -> None:
        """Reset all circuit breakers."""
        for proxy in self._proxies.values():
            proxy.reset_circuit_breaker()
        logger.info("Reset all circuit breakers")

    def get_all_metrics(self) -> Dict[str, ServiceMetrics]:
        """Get metrics for all registered proxies."""
        return {name: proxy.get_metrics() for name, proxy in self._proxies.items()}

    def get_health_status(self) -> Dict[str, bool]:
        """Get health status for all registered proxies."""
        health_results = {}
        for name, proxy in self._proxies.items():
            try:
                # Use asyncio.create_task for non-blocking health checks
                health_results[name] = asyncio.create_task(proxy.check_health())
            except Exception:
                health_results[name] = False
        return health_results


# Custom exceptions

class ServiceUnavailableError(Exception):
    """Raised when a service is unavailable."""
    pass


class CircuitOpenError(Exception):
    """Raised when a circuit breaker is open."""
    pass


# Global proxy manager instance
_proxy_manager: Optional[ServiceProxyManager] = None


def get_proxy_manager() -> ServiceProxyManager:
    """Get the global service proxy manager."""
    global _proxy_manager
    if _proxy_manager is None:
        _proxy_manager = ServiceProxyManager()
    return _proxy_manager


def create_service_proxy(
    service_name: str,
    service_registry_getter: Callable[[], Any],
    app_state_getter: Optional[Callable[[], Any]] = None,
    cache_ttl: float = 300.0,
    circuit_config: Optional[CircuitBreakerConfig] = None,
) -> ServiceProxy:
    """
    Convenience function to create a service proxy with ServiceRegistry-first pattern.

    Args:
        service_name: Name of the service
        service_registry_getter: Function to get ServiceRegistry
        app_state_getter: Optional function to get app.state (fallback)
        cache_ttl: Cache time-to-live in seconds
        circuit_config: Circuit breaker configuration

    Returns:
        Configured service proxy
    """
    # Create providers
    providers = [ServiceRegistry_Provider(service_name, service_registry_getter)]

    if app_state_getter:
        providers.append(AppState_Provider(service_name, app_state_getter))

    # Create composite provider
    provider = CompositeServiceProvider(service_name, providers)

    # Create and register proxy
    manager = get_proxy_manager()
    return manager.create_proxy(service_name, provider, cache_ttl, circuit_config)
