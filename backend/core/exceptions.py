"""
Core exceptions for the backend application.

This module contains custom exceptions used throughout the application
for proper error handling and API responses.
"""


class ServiceNotAvailableError(Exception):
    """
    Raised when a requested service is not registered in ServiceRegistry.

    This exception is used to indicate that a service required by an endpoint
    is not available in the current deployment configuration. It results in
    a 503 Service Unavailable response.
    """

    def __init__(self, service_name: str):
        self.service_name = service_name
        super().__init__(f"Service '{service_name}' is not available in this deployment")


class ServiceInitializationError(Exception):
    """
    Raised when a service fails to initialize during startup.

    This exception is used to indicate that a service could not be properly
    initialized, but the application can continue running without it.
    """

    def __init__(self, service_name: str, reason: str):
        self.service_name = service_name
        self.reason = reason
        super().__init__(f"Service '{service_name}' failed to initialize: {reason}")
