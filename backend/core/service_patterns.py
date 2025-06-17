"""
Service Patterns for Long-Lived Services

This module provides base classes and patterns for WebSocket handlers and background
services that cannot use request-scoped dependency injection.

Key patterns:
1. Application-scoped singleton for WebSocket handlers
2. Service reference pattern for background services
3. Lazy initialization with fallback for resilience
4. Lifecycle hooks for startup/shutdown coordination
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Set, TypeVar, Generic

logger = logging.getLogger(__name__)

T = TypeVar('T')


class ServiceProxy(Generic[T]):
    """
    Proxy for lazy service access with fallback patterns.

    This allows background services to access other services without
    creating circular dependencies or timing issues during startup.
    """

    def __init__(self, service_name: str, getter_func=None):
        """
        Initialize service proxy.

        Args:
            service_name: Name of the service to proxy
            getter_func: Optional function to get the service
        """
        self.service_name = service_name
        self._getter_func = getter_func
        self._cached_service: Optional[T] = None

    def get(self) -> Optional[T]:
        """Get the proxied service with caching and fallback."""
        if self._cached_service is not None:
            return self._cached_service

        # Try custom getter first
        if self._getter_func:
            try:
                service = self._getter_func()
                if service:
                    self._cached_service = service
                    return service
            except Exception as e:
                logger.debug(f"Failed to get {self.service_name} via custom getter: {e}")

        # Try app.state (ServiceRegistry pattern)
        try:
            from backend.main import app as main_app

            service = getattr(main_app.state, self.service_name, None)
            if service:
                self._cached_service = service
                return service
        except Exception as e:
            logger.debug(f"Failed to get {self.service_name} from app.state: {e}")

        # Try feature manager
        try:
            from backend.services.feature_manager import get_feature_manager
            feature_manager = get_feature_manager()
            service = feature_manager.get_feature(self.service_name)
            if service:
                self._cached_service = service
                return service
        except Exception as e:
            logger.debug(f"Failed to get {self.service_name} from feature manager: {e}")

        return None

    def invalidate_cache(self):
        """Invalidate the cached service reference."""
        self._cached_service = None


class WebSocketHandlerBase(ABC):
    """
    Base class for WebSocket handlers that need service dependencies.

    This pattern ensures handlers are initialized at application startup
    with proper service references, avoiding the request-scoped DI limitations.
    """

    def __init__(self, service_dependencies: Dict[str, Any]):
        """
        Initialize with required service dependencies.

        Args:
            service_dependencies: Dict of service_name -> service_instance
        """
        self.services = service_dependencies
        self.clients: Set[Any] = set()
        self._lock = asyncio.Lock()
        self._is_initialized = False

    async def startup(self) -> None:
        """Initialize handler and register with services."""
        try:
            await self._register_listeners()
            self._is_initialized = True
            logger.info(f"{self.__class__.__name__} initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize {self.__class__.__name__}: {e}")
            raise

    async def shutdown(self) -> None:
        """Cleanup handler and disconnect clients."""
        try:
            await self._unregister_listeners()

            # Disconnect all clients
            async with self._lock:
                for client in list(self.clients):
                    await self._disconnect_client(client)

            logger.info(f"{self.__class__.__name__} shutdown complete")
        except Exception as e:
            logger.error(f"Error during {self.__class__.__name__} shutdown: {e}")

    @abstractmethod
    async def _register_listeners(self) -> None:
        """Register event listeners with services. Must be implemented by subclasses."""
        pass

    @abstractmethod
    async def _unregister_listeners(self) -> None:
        """Unregister event listeners from services. Must be implemented by subclasses."""
        pass

    @abstractmethod
    async def _disconnect_client(self, client: Any) -> None:
        """Disconnect a specific client. Must be implemented by subclasses."""
        pass


class BackgroundServiceBase(ABC):
    """
    Base class for background services that need service dependencies.

    Provides patterns for service access, lifecycle management, and
    graceful shutdown handling.
    """

    def __init__(self, service_proxies: Optional[Dict[str, ServiceProxy]] = None):
        """
        Initialize with optional service proxies.

        Args:
            service_proxies: Dict of service_name -> ServiceProxy
        """
        self.service_proxies = service_proxies or {}
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def get_service(self, service_name: str) -> Optional[Any]:
        """
        Get a service by name using proxy pattern.

        Args:
            service_name: Name of the service to retrieve

        Returns:
            Service instance or None if not available
        """
        if service_name in self.service_proxies:
            return self.service_proxies[service_name].get()

        # Create proxy on-demand
        proxy = ServiceProxy(service_name)
        self.service_proxies[service_name] = proxy
        return proxy.get()

    async def start(self) -> None:
        """Start the background service."""
        if self._running:
            logger.warning(f"{self.__class__.__name__} already running")
            return

        self._running = True

        # Initialize service connections
        await self._initialize_services()

        # Start background task
        self._task = asyncio.create_task(self._run())
        logger.info(f"{self.__class__.__name__} started")

    async def stop(self) -> None:
        """Stop the background service gracefully."""
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        await self._cleanup_services()
        logger.info(f"{self.__class__.__name__} stopped")

    @abstractmethod
    async def _initialize_services(self) -> None:
        """Initialize service connections. Must be implemented by subclasses."""
        pass

    @abstractmethod
    async def _cleanup_services(self) -> None:
        """Cleanup service connections. Must be implemented by subclasses."""
        pass

    @abstractmethod
    async def _run(self) -> None:
        """Main background task loop. Must be implemented by subclasses."""
        pass


class ServiceLifecycleManager:
    """
    Manages lifecycle of WebSocket handlers and background services.

    This provides a centralized way to start/stop all long-lived services
    with proper dependency ordering and error handling.
    """

    def __init__(self):
        """Initialize the lifecycle manager."""
        self.websocket_handlers: Dict[str, WebSocketHandlerBase] = {}
        self.background_services: Dict[str, BackgroundServiceBase] = {}
        self._startup_order: list[str] = []

    def register_websocket_handler(self, name: str, handler: WebSocketHandlerBase) -> None:
        """Register a WebSocket handler."""
        self.websocket_handlers[name] = handler
        if name not in self._startup_order:
            self._startup_order.append(name)

    def register_background_service(self, name: str, service: BackgroundServiceBase) -> None:
        """Register a background service."""
        self.background_services[name] = service
        if name not in self._startup_order:
            self._startup_order.append(name)

    async def startup_all(self) -> None:
        """Start all registered services in order."""
        logger.info("Starting long-lived services...")

        for name in self._startup_order:
            try:
                if name in self.websocket_handlers:
                    await self.websocket_handlers[name].startup()
                    logger.info(f"Started WebSocket handler: {name}")
                elif name in self.background_services:
                    await self.background_services[name].start()
                    logger.info(f"Started background service: {name}")
            except Exception as e:
                logger.error(f"Failed to start {name}: {e}")
                # Continue with other services

    async def shutdown_all(self) -> None:
        """Stop all registered services in reverse order."""
        logger.info("Stopping long-lived services...")

        for name in reversed(self._startup_order):
            try:
                if name in self.websocket_handlers:
                    await self.websocket_handlers[name].shutdown()
                    logger.info(f"Stopped WebSocket handler: {name}")
                elif name in self.background_services:
                    await self.background_services[name].stop()
                    logger.info(f"Stopped background service: {name}")
            except Exception as e:
                logger.error(f"Failed to stop {name}: {e}")
                # Continue with other services


# Global lifecycle manager instance (deprecated - use app.state)
_lifecycle_manager: Optional[ServiceLifecycleManager] = None


def get_lifecycle_manager() -> ServiceLifecycleManager:
    """Get the lifecycle manager instance.

    This should be stored in app.state.service_lifecycle_manager during
    application startup. The global instance is maintained for backward
    compatibility only.
    """
    # Try to get from app.state first
    try:
        from backend.main import app
        if hasattr(app.state, 'service_lifecycle_manager') and app.state.service_lifecycle_manager is not None:
            return app.state.service_lifecycle_manager
    except (ImportError, AttributeError, RuntimeError):
        pass

    # Fall back to global instance
    global _lifecycle_manager
    if _lifecycle_manager is None:
        _lifecycle_manager = ServiceLifecycleManager()
    return _lifecycle_manager
