"""
Tests for ``backend.core.exception_handlers.create_error_response``.

Validates ADR-0005: every error response includes both the FastAPI-default
``detail`` field and the structured ``error.{code,message,details?,request_id?}``
envelope.
"""

from __future__ import annotations

import json

import pytest

from backend.core.exception_handlers import create_error_response


@pytest.mark.unit
class TestErrorResponseEnvelope:
    """ADR-0005: ``detail`` and ``error.*`` are both present."""

    def _payload(self, **kwargs) -> dict:
        response = create_error_response(**kwargs)
        return json.loads(response.body.decode())

    def test_detail_field_present_at_top_level(self):
        """``detail`` is the FastAPI-default field (read by the React UI)."""
        body = self._payload(
            status_code=404,
            error_code="HTTP_404",
            message="Account not found",
        )
        assert body["detail"] == "Account not found"

    def test_structured_error_envelope_present(self):
        """``error.{code,message}`` is the structured envelope."""
        body = self._payload(
            status_code=404,
            error_code="HTTP_404",
            message="Account not found",
        )
        assert body["error"]["code"] == "HTTP_404"
        assert body["error"]["message"] == "Account not found"

    def test_detail_and_error_message_stay_in_sync(self):
        """The two human-readable strings are always equal."""
        body = self._payload(
            status_code=400,
            error_code="VALIDATION_ERROR",
            message="Field 'email' is required",
        )
        assert body["detail"] == body["error"]["message"]

    def test_optional_details_only_in_envelope(self):
        """``details`` lives only inside ``error``; ``detail`` stays a string."""
        body = self._payload(
            status_code=422,
            error_code="VALIDATION_ERROR",
            message="Validation failed",
            details={"errors": [{"field": "email", "message": "required"}]},
        )
        assert body["error"]["details"] == {"errors": [{"field": "email", "message": "required"}]}
        # detail must NOT be turned into a dict; FastAPI clients expect a string.
        assert isinstance(body["detail"], str)
        assert body["detail"] == "Validation failed"

    def test_optional_request_id_only_in_envelope(self):
        """``request_id`` is metadata; lives only inside ``error``."""
        body = self._payload(
            status_code=500,
            error_code="INTERNAL_ERROR",
            message="Something failed",
            request_id="req-abc-123",
        )
        assert body["error"]["request_id"] == "req-abc-123"
        assert "request_id" not in body  # not at top level

    def test_no_optional_fields_when_unset(self):
        """``details`` and ``request_id`` are only present when supplied."""
        body = self._payload(
            status_code=404,
            error_code="HTTP_404",
            message="Account not found",
        )
        assert "details" not in body["error"]
        assert "request_id" not in body["error"]

    def test_status_code_propagates_to_response(self):
        """The ``status_code`` argument becomes the HTTP status code."""
        response = create_error_response(
            status_code=418,
            error_code="HTTP_418",
            message="I'm a teapot",
        )
        assert response.status_code == 418
