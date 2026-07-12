"""Starlink gRPC reflection client for RouterOS sidecar verdicts."""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Lock
from typing import Any


@dataclass(frozen=True, slots=True)
class StarlinkSnapshot:
    """A cached Starlink status/history snapshot."""

    reachable: bool
    status: dict[str, Any] = field(default_factory=dict)
    history: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    device_info: dict[str, Any] = field(default_factory=dict)
    fetched_at: float | None = None
    error: str | None = None
    location: dict[str, Any] | None = None
    location_error: str | None = None


class _ReflectedHandleTransport:
    """Own reflected protobuf descriptors and one reusable gRPC channel."""

    def __init__(self, target: str, timeout_seconds: float) -> None:
        import grpc
        from google.protobuf import descriptor_pool, json_format, message_factory
        from grpc_reflection.v1alpha.proto_reflection_descriptor_database import (
            ProtoReflectionDescriptorDatabase,
        )

        self._timeout_seconds = timeout_seconds
        self._json_format = json_format
        self._channel = grpc.insecure_channel(target)
        self._reflection_db = ProtoReflectionDescriptorDatabase(self._channel)
        self._pool = descriptor_pool.DescriptorPool(self._reflection_db)
        request_descriptor = self._pool.FindMessageTypeByName("SpaceX.API.Device.Request")
        response_descriptor = self._pool.FindMessageTypeByName("SpaceX.API.Device.Response")
        self._request_class = message_factory.GetMessageClass(request_descriptor)
        self._response_class = message_factory.GetMessageClass(response_descriptor)
        self._handle = self._channel.unary_unary(
            "/SpaceX.API.Device.Device/Handle",
            request_serializer=self._request_class.SerializeToString,
            response_deserializer=self._response_class.FromString,
        )

    def call(self, request_field: str) -> dict[str, Any]:
        """Invoke one reflected Device/Handle request."""
        request = self._request_class()
        getattr(request, request_field).SetInParent()
        response = self._handle(request, timeout=self._timeout_seconds)
        return self._json_format.MessageToDict(
            response,
            always_print_fields_with_no_presence=True,
            preserving_proto_field_name=True,
            use_integers_for_enums=False,
        )

    def close(self) -> None:
        """Close the reusable gRPC channel."""
        self._channel.close()


class StarlinkGrpcClient:
    """Fetch Starlink dish status/history via reflected Device/Handle calls."""

    def __init__(
        self,
        host: str,
        port: int,
        timeout_seconds: float = 5.0,
        handle_call: Callable[[str], dict[str, Any]] | None = None,
    ) -> None:
        self._target = f"{host}:{port}"
        self._timeout_seconds = timeout_seconds
        self._handle_call = handle_call
        self._transport: _ReflectedHandleTransport | None = None
        self._transport_lock = Lock()

    def fetch_snapshot_blocking(self) -> StarlinkSnapshot:
        """Fetch a Starlink snapshot. Call from a worker thread."""
        with self._transport_lock:
            try:
                status_response = self._call_handle("get_status")
                history_response = self._call_handle("get_history")
                diagnostics_response = self._call_handle("get_diagnostics")
                device_info_response = self._call_handle("get_device_info")
                location, location_error = self._fetch_location_optional()
                return StarlinkSnapshot(
                    reachable=True,
                    status=status_response.get("dish_get_status", {}),
                    history=history_response.get("dish_get_history", {}),
                    diagnostics=diagnostics_response.get("dish_get_diagnostics", {}),
                    device_info=device_info_response.get("get_device_info", {}),
                    fetched_at=time.time(),
                    location=location,
                    location_error=location_error,
                )
            except Exception as exc:  # pragma: no cover - exercised through fake error paths
                return StarlinkSnapshot(reachable=False, error=f"{type(exc).__name__}: {exc}")

    def close(self) -> None:
        """Close reflected transport resources after any active snapshot completes."""
        with self._transport_lock:
            if self._transport is None:
                return
            self._transport.close()
            self._transport = None

    def _fetch_location_optional(self) -> tuple[dict[str, Any] | None, str | None]:
        try:
            response = self._call_handle("get_location")
        except Exception as exc:  # pragma: no cover - depends on dish policy
            return None, f"{type(exc).__name__}: {exc}"
        return response.get("dish_get_location"), None

    def _call_handle(self, request_field: str) -> dict[str, Any]:
        if self._handle_call is not None:
            return self._handle_call(request_field)
        return self._grpc_handle_call(request_field)

    def _grpc_handle_call(self, request_field: str) -> dict[str, Any]:
        if self._transport is None:
            self._transport = _ReflectedHandleTransport(self._target, self._timeout_seconds)
        return self._transport.call(request_field)
