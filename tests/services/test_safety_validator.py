"""
Unit tests for SafetyValidator - ISO 26262-inspired safety validation patterns.

Tests cover state transitions, emergency stop conditions, and safety actions
for RV-C vehicle control systems.
"""

import pytest

from backend.services.feature_models import (
    FeatureState,
    SafeStateAction,
    SafetyClassification,
    SafetyValidator,
)


class TestSafetyValidator:
    """Test suite for SafetyValidator safety patterns."""

    def test_valid_state_transitions(self):
        """Test that valid state transitions are allowed."""
        # STOPPED -> INITIALIZING
        is_valid, reason = SafetyValidator.validate_state_transition(
            FeatureState.STOPPED,
            FeatureState.INITIALIZING,
            SafetyClassification.OPERATIONAL,
        )
        assert is_valid is True
        assert reason == "Valid transition"

        # INITIALIZING -> HEALTHY
        is_valid, reason = SafetyValidator.validate_state_transition(
            FeatureState.INITIALIZING,
            FeatureState.HEALTHY,
            SafetyClassification.OPERATIONAL,
        )
        assert is_valid is True

        # HEALTHY -> DEGRADED
        is_valid, reason = SafetyValidator.validate_state_transition(
            FeatureState.HEALTHY,
            FeatureState.DEGRADED,
            SafetyClassification.CRITICAL,
        )
        assert is_valid is True

        # DEGRADED -> FAILED
        is_valid, reason = SafetyValidator.validate_state_transition(
            FeatureState.DEGRADED,
            FeatureState.FAILED,
            SafetyClassification.CRITICAL,
        )
        assert is_valid is True

    def test_invalid_state_transitions(self):
        """Test that invalid state transitions are rejected."""
        # STOPPED -> HEALTHY (skipping INITIALIZING)
        is_valid, reason = SafetyValidator.validate_state_transition(
            FeatureState.STOPPED,
            FeatureState.HEALTHY,
            SafetyClassification.OPERATIONAL,
        )
        assert is_valid is False
        assert "Invalid transition" in reason

        # FAILED -> HEALTHY (must go through STOPPED/MAINTENANCE)
        is_valid, reason = SafetyValidator.validate_state_transition(
            FeatureState.FAILED,
            FeatureState.HEALTHY,
            SafetyClassification.OPERATIONAL,
        )
        assert is_valid is False

    def test_critical_feature_transition_rules(self):
        """Test special transition rules for critical features."""
        # Critical features cannot go directly from HEALTHY to FAILED
        is_valid, reason = SafetyValidator.validate_state_transition(
            FeatureState.HEALTHY,
            FeatureState.FAILED,
            SafetyClassification.CRITICAL,
            "critical_feature",
        )
        assert is_valid is False
        assert "must transition through DEGRADED" in reason

        # But INITIALIZING -> FAILED is allowed (startup failure)
        is_valid, reason = SafetyValidator.validate_state_transition(
            FeatureState.INITIALIZING,
            FeatureState.FAILED,
            SafetyClassification.CRITICAL,
        )
        assert is_valid is True

    def test_position_critical_transition_rules(self):
        """Test special transition rules for position-critical features."""
        # Position-critical features should use SAFE_SHUTDOWN instead of FAILED
        is_valid, reason = SafetyValidator.validate_state_transition(
            FeatureState.HEALTHY,
            FeatureState.FAILED,
            SafetyClassification.POSITION_CRITICAL,
            "slide_control",
        )
        assert is_valid is False
        assert "should use SAFE_SHUTDOWN" in reason

        # SAFE_SHUTDOWN should be allowed
        is_valid, reason = SafetyValidator.validate_state_transition(
            FeatureState.HEALTHY,
            FeatureState.SAFE_SHUTDOWN,
            SafetyClassification.POSITION_CRITICAL,
        )
        assert is_valid is True

    def test_same_state_transition(self):
        """Test that same-state transitions are allowed (no-op)."""
        is_valid, reason = SafetyValidator.validate_state_transition(
            FeatureState.HEALTHY,
            FeatureState.HEALTHY,
            SafetyClassification.CRITICAL,
        )
        assert is_valid is True
        assert reason == "No state change"

    def test_get_safe_transition(self):
        """Test getting safe intermediate states for invalid transitions."""
        # For critical features trying to fail, should get DEGRADED first
        safe_state = SafetyValidator.get_safe_transition(
            FeatureState.HEALTHY,
            FeatureState.FAILED,
            SafetyClassification.CRITICAL,
        )
        assert safe_state == FeatureState.DEGRADED

        # For position-critical features, the transition HEALTHY->FAILED is invalid
        # Since it's invalid and DEGRADED is available from HEALTHY, it returns DEGRADED
        safe_state = SafetyValidator.get_safe_transition(
            FeatureState.HEALTHY,
            FeatureState.FAILED,
            SafetyClassification.POSITION_CRITICAL,
        )
        assert safe_state == FeatureState.DEGRADED  # Not SAFE_SHUTDOWN because DEGRADED comes first

        # If direct transition is valid, return desired state
        safe_state = SafetyValidator.get_safe_transition(
            FeatureState.STOPPED,
            FeatureState.INITIALIZING,
            SafetyClassification.OPERATIONAL,
        )
        assert safe_state == FeatureState.INITIALIZING

    def test_emergency_stop_conditions(self):
        """Test conditions that trigger emergency stop."""
        # Critical feature failure triggers emergency stop
        should_stop = SafetyValidator.is_emergency_stop_required(
            FeatureState.FAILED,
            SafetyClassification.CRITICAL,
        )
        assert should_stop is True

        # Position-critical with failed dependencies
        should_stop = SafetyValidator.is_emergency_stop_required(
            FeatureState.DEGRADED,
            SafetyClassification.POSITION_CRITICAL,
            failed_dependencies={"can_interface"},
        )
        assert should_stop is True

        # Multiple safety-related failures
        should_stop = SafetyValidator.is_emergency_stop_required(
            FeatureState.FAILED,
            SafetyClassification.SAFETY_RELATED,
            failed_dependencies={"dep1", "dep2"},
        )
        assert should_stop is True

        # Operational feature failure doesn't trigger emergency
        should_stop = SafetyValidator.is_emergency_stop_required(
            FeatureState.FAILED,
            SafetyClassification.OPERATIONAL,
        )
        assert should_stop is False

    def test_required_safety_actions(self):
        """Test getting required safety actions for different scenarios."""
        # Critical feature failure actions
        actions = SafetyValidator.get_required_safety_actions(
            SafetyClassification.CRITICAL,
            FeatureState.FAILED,
            SafeStateAction.EMERGENCY_STOP,
        )
        assert "Notify system administrator immediately" in actions
        assert "Log all recent operations for forensic analysis" in actions

        # Position-critical with maintain position
        actions = SafetyValidator.get_required_safety_actions(
            SafetyClassification.POSITION_CRITICAL,
            FeatureState.SAFE_SHUTDOWN,
            SafeStateAction.MAINTAIN_POSITION,
        )
        assert "Maintain current physical positions" in actions
        assert "Disable all movement commands" in actions
        assert "Enable position monitoring only" in actions

        # Position-critical with emergency stop
        actions = SafetyValidator.get_required_safety_actions(
            SafetyClassification.POSITION_CRITICAL,
            FeatureState.FAILED,
            SafeStateAction.EMERGENCY_STOP,
        )
        assert "Execute immediate emergency stop" in actions
        assert "Require manual intervention to resume" in actions

        # Safety-related degraded state
        actions = SafetyValidator.get_required_safety_actions(
            SafetyClassification.SAFETY_RELATED,
            FeatureState.FAILED,
            SafeStateAction.CONTINUE_OPERATION,
        )
        assert "Continue monitoring system health" in actions
        assert "Disable non-essential functionality" in actions

        # Healthy state - no actions required
        actions = SafetyValidator.get_required_safety_actions(
            SafetyClassification.CRITICAL,
            FeatureState.HEALTHY,
            SafeStateAction.CONTINUE_OPERATION,
        )
        assert len(actions) == 0

    def test_maintenance_state_transitions(self):
        """Test maintenance state transitions."""
        # Check which states can go to MAINTENANCE based on VALID_TRANSITIONS
        expected_can_go_to_maintenance = {
            FeatureState.STOPPED,
            FeatureState.HEALTHY,
            FeatureState.DEGRADED,
            FeatureState.FAILED,
            FeatureState.SAFE_SHUTDOWN,
        }

        for from_state in FeatureState:
            if from_state == FeatureState.MAINTENANCE:
                continue
            is_valid, _ = SafetyValidator.validate_state_transition(
                from_state,
                FeatureState.MAINTENANCE,
                SafetyClassification.OPERATIONAL,
            )

            if from_state in expected_can_go_to_maintenance:
                assert is_valid is True, f"Expected {from_state} -> MAINTENANCE to be valid"
            else:
                # INITIALIZING cannot go to MAINTENANCE according to VALID_TRANSITIONS
                assert is_valid is False, f"Expected {from_state} -> MAINTENANCE to be invalid"

        # MAINTENANCE can go to STOPPED, INITIALIZING, or HEALTHY
        valid_from_maintenance = {
            FeatureState.STOPPED,
            FeatureState.INITIALIZING,
            FeatureState.HEALTHY,
        }
        for to_state in valid_from_maintenance:
            is_valid, _ = SafetyValidator.validate_state_transition(
                FeatureState.MAINTENANCE,
                to_state,
                SafetyClassification.OPERATIONAL,
            )
            assert is_valid is True, f"Failed for MAINTENANCE -> {to_state}"

    def test_edge_case_transitions(self):
        """Test edge cases in state transitions."""
        # Undefined from_state should handle gracefully
        is_valid, reason = SafetyValidator.validate_state_transition(
            FeatureState.SAFE_SHUTDOWN,
            FeatureState.HEALTHY,
            SafetyClassification.OPERATIONAL,
        )
        assert is_valid is False  # SAFE_SHUTDOWN cannot go directly to HEALTHY

        # Recovery path: FAILED -> STOPPED -> INITIALIZING -> HEALTHY
        is_valid, _ = SafetyValidator.validate_state_transition(
            FeatureState.FAILED,
            FeatureState.STOPPED,
            SafetyClassification.CRITICAL,
        )
        assert is_valid is True

    def test_safety_classification_specific_rules(self):
        """Test rules specific to each safety classification."""
        classifications = [
            SafetyClassification.CRITICAL,
            SafetyClassification.SAFETY_RELATED,
            SafetyClassification.POSITION_CRITICAL,
            SafetyClassification.OPERATIONAL,
            SafetyClassification.MAINTENANCE,
        ]

        # Test that all classifications handle basic transitions
        for classification in classifications:
            is_valid, _ = SafetyValidator.validate_state_transition(
                FeatureState.STOPPED,
                FeatureState.INITIALIZING,
                classification,
            )
            assert is_valid is True, f"Failed for {classification}"


class TestSafetyValidatorIntegration:
    """Integration tests for SafetyValidator with real-world scenarios."""

    def test_rv_slide_deployment_safety(self):
        """Test safety scenarios for RV slide deployment."""
        # Slide control is position-critical
        classification = SafetyClassification.POSITION_CRITICAL

        # Normal operation: slides can initialize
        is_valid, _ = SafetyValidator.validate_state_transition(
            FeatureState.STOPPED,
            FeatureState.INITIALIZING,
            classification,
            "slide_control",
        )
        assert is_valid is True

        # If slides fail while deployed, must use SAFE_SHUTDOWN
        is_valid, reason = SafetyValidator.validate_state_transition(
            FeatureState.HEALTHY,
            FeatureState.FAILED,
            classification,
            "slide_control",
        )
        assert is_valid is False
        assert "SAFE_SHUTDOWN" in reason

        # Get required actions for safe shutdown
        actions = SafetyValidator.get_required_safety_actions(
            classification,
            FeatureState.SAFE_SHUTDOWN,
            SafeStateAction.MAINTAIN_POSITION,
        )
        assert "Maintain current physical positions" in actions

    def test_can_bus_failure_cascade(self):
        """Test cascading failures from CAN bus."""
        # CAN interface is critical
        can_classification = SafetyClassification.CRITICAL

        # CAN failure should trigger emergency procedures
        should_stop = SafetyValidator.is_emergency_stop_required(
            FeatureState.FAILED,
            can_classification,
        )
        assert should_stop is True

        # Features depending on CAN should also be affected
        should_stop = SafetyValidator.is_emergency_stop_required(
            FeatureState.DEGRADED,
            SafetyClassification.POSITION_CRITICAL,
            failed_dependencies={"can_interface"},
        )
        assert should_stop is True

    def test_recovery_workflow(self):
        """Test recovery workflow for failed features."""
        # Failed feature must go through proper recovery path
        classification = SafetyClassification.SAFETY_RELATED

        # FAILED -> STOPPED
        is_valid, _ = SafetyValidator.validate_state_transition(
            FeatureState.FAILED,
            FeatureState.STOPPED,
            classification,
        )
        assert is_valid is True

        # STOPPED -> INITIALIZING
        is_valid, _ = SafetyValidator.validate_state_transition(
            FeatureState.STOPPED,
            FeatureState.INITIALIZING,
            classification,
        )
        assert is_valid is True

        # INITIALIZING -> HEALTHY
        is_valid, _ = SafetyValidator.validate_state_transition(
            FeatureState.INITIALIZING,
            FeatureState.HEALTHY,
            classification,
        )
        assert is_valid is True

    def test_simultaneous_failures(self):
        """Test handling of multiple simultaneous failures."""
        # Single safety-related failure doesn't trigger emergency
        should_stop = SafetyValidator.is_emergency_stop_required(
            FeatureState.FAILED,
            SafetyClassification.SAFETY_RELATED,
            failed_dependencies={"dep1"},
        )
        assert should_stop is False

        # Multiple safety-related failures do trigger emergency
        should_stop = SafetyValidator.is_emergency_stop_required(
            FeatureState.FAILED,
            SafetyClassification.SAFETY_RELATED,
            failed_dependencies={"dep1", "dep2"},
        )
        assert should_stop is True
