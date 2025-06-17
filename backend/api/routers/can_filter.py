"""
CAN Message Filter API endpoints.

Provides REST API for managing CAN message filters.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.core.dependencies_v2 import get_feature_manager
from backend.integrations.can.message_filter import (
    FilterAction,
    FilterCondition,
    FilterField,
    FilterOperator,
    FilterRule,
)
from backend.services.feature_manager import FeatureManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/can-filter", tags=["can-filter"])


# Pydantic models for API
class FilterConditionModel(BaseModel):
    """Filter condition model."""

    field: FilterField
    operator: FilterOperator
    value: Any
    case_sensitive: bool = True
    negate: bool = False


class FilterActionModel(BaseModel):
    """Filter action model."""

    action: FilterAction
    parameters: Optional[Dict[str, Any]] = None


class FilterRuleCreate(BaseModel):
    """Create filter rule request."""

    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = ""
    enabled: bool = True
    priority: int = Field(50, ge=0, le=100)
    conditions: List[FilterConditionModel]
    condition_logic: str = Field("AND", pattern="^(AND|OR)$")
    actions: List[Dict[str, Any]]


class FilterRuleUpdate(BaseModel):
    """Update filter rule request."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    enabled: Optional[bool] = None
    priority: Optional[int] = Field(None, ge=0, le=100)
    conditions: Optional[List[FilterConditionModel]] = None
    condition_logic: Optional[str] = Field(None, pattern="^(AND|OR)$")
    actions: Optional[List[Dict[str, Any]]] = None


class FilterRuleResponse(BaseModel):
    """Filter rule response."""

    id: str
    name: str
    description: str
    enabled: bool
    priority: int
    conditions: List[FilterConditionModel]
    condition_logic: str
    actions: List[Dict[str, Any]]
    statistics: Dict[str, Any]


class FilterStatisticsResponse(BaseModel):
    """Filter statistics response."""

    messages_processed: int
    messages_passed: int
    messages_blocked: int
    messages_captured: int
    alerts_sent: int
    processing_time_ms: float
    active_rules: int
    total_rules: int
    capture_buffer_size: int
    rules: List[Dict[str, Any]]


class CapturedMessageResponse(BaseModel):
    """Captured message response."""

    timestamp: float
    can_id: str
    data: str
    interface: str
    protocol: Optional[str] = "unknown"
    message_type: Optional[str] = ""
    decoded: Optional[Dict[str, Any]] = None


@router.get("/status", response_model=Dict[str, Any])
async def get_filter_status(
    feature_manager: FeatureManager = Depends(get_feature_manager),
):
    """Get message filter status."""
    filter_feature = feature_manager.get_feature("can_message_filter")
    if not filter_feature:
        raise HTTPException(status_code=404, detail="Message filter not available")

    return {
        "enabled": filter_feature.enabled,
        "healthy": filter_feature.health == "healthy",
        "total_rules": len(filter_feature.rules),
        "active_rules": len([r for r in filter_feature.rules.values() if r.enabled]),
        "statistics": filter_feature.get_statistics(),
    }


@router.get("/rules", response_model=List[FilterRuleResponse])
async def list_filter_rules(
    enabled_only: bool = Query(False, description="Only return enabled rules"),
    feature_manager: FeatureManager = Depends(get_feature_manager),
):
    """List all filter rules."""
    filter_feature = feature_manager.get_feature("can_message_filter")
    if not filter_feature:
        raise HTTPException(status_code=404, detail="Message filter not available")

    rules = filter_feature.get_all_rules()

    if enabled_only:
        rules = [r for r in rules if r.enabled]

    return [
        FilterRuleResponse(
            id=rule.id,
            name=rule.name,
            description=rule.description,
            enabled=rule.enabled,
            priority=rule.priority,
            conditions=[
                FilterConditionModel(
                    field=cond.field,
                    operator=cond.operator,
                    value=cond.value,
                    case_sensitive=cond.case_sensitive,
                    negate=cond.negate,
                )
                for cond in rule.conditions
            ],
            condition_logic=rule.condition_logic,
            actions=rule.actions,
            statistics=rule.statistics,
        )
        for rule in rules
    ]


@router.get("/rules/{rule_id}", response_model=FilterRuleResponse)
async def get_filter_rule(
    rule_id: str,
    feature_manager: FeatureManager = Depends(get_feature_manager),
):
    """Get a specific filter rule."""
    filter_feature = feature_manager.get_feature("can_message_filter")
    if not filter_feature:
        raise HTTPException(status_code=404, detail="Message filter not available")

    rule = filter_feature.get_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Filter rule not found")

    return FilterRuleResponse(
        id=rule.id,
        name=rule.name,
        description=rule.description,
        enabled=rule.enabled,
        priority=rule.priority,
        conditions=[
            FilterConditionModel(
                field=cond.field,
                operator=cond.operator,
                value=cond.value,
                case_sensitive=cond.case_sensitive,
                negate=cond.negate,
            )
            for cond in rule.conditions
        ],
        condition_logic=rule.condition_logic,
        actions=rule.actions,
        statistics=rule.statistics,
    )


@router.post("/rules", response_model=FilterRuleResponse)
async def create_filter_rule(
    rule_data: FilterRuleCreate,
    feature_manager: FeatureManager = Depends(get_feature_manager),
):
    """Create a new filter rule."""
    filter_feature = feature_manager.get_feature("can_message_filter")
    if not filter_feature:
        raise HTTPException(status_code=404, detail="Message filter not available")

    # Generate unique ID
    import uuid
    rule_id = f"user_{uuid.uuid4().hex[:8]}"

    # Create conditions
    conditions = []
    for cond_data in rule_data.conditions:
        conditions.append(FilterCondition(
            field=cond_data.field,
            operator=cond_data.operator,
            value=cond_data.value,
            case_sensitive=cond_data.case_sensitive,
            negate=cond_data.negate,
        ))

    # Create rule
    rule = FilterRule(
        id=rule_id,
        name=rule_data.name,
        description=rule_data.description,
        enabled=rule_data.enabled,
        priority=rule_data.priority,
        conditions=conditions,
        condition_logic=rule_data.condition_logic,
        actions=rule_data.actions,
    )

    # Add rule
    if not filter_feature.add_rule(rule):
        raise HTTPException(status_code=400, detail="Failed to add filter rule")

    return FilterRuleResponse(
        id=rule.id,
        name=rule.name,
        description=rule.description,
        enabled=rule.enabled,
        priority=rule.priority,
        conditions=[
            FilterConditionModel(
                field=cond.field,
                operator=cond.operator,
                value=cond.value,
                case_sensitive=cond.case_sensitive,
                negate=cond.negate,
            )
            for cond in rule.conditions
        ],
        condition_logic=rule.condition_logic,
        actions=rule.actions,
        statistics=rule.statistics,
    )


@router.put("/rules/{rule_id}", response_model=FilterRuleResponse)
async def update_filter_rule(
    rule_id: str,
    updates: FilterRuleUpdate,
    feature_manager: FeatureManager = Depends(get_feature_manager),
):
    """Update an existing filter rule."""
    filter_feature = feature_manager.get_feature("can_message_filter")
    if not filter_feature:
        raise HTTPException(status_code=404, detail="Message filter not available")

    # Check if rule exists
    rule = filter_feature.get_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Filter rule not found")

    # Don't allow updating system rules
    if rule_id.startswith("system_"):
        raise HTTPException(status_code=403, detail="Cannot update system rules")

    # Prepare updates
    update_dict = updates.dict(exclude_unset=True)

    # Convert conditions if provided
    if "conditions" in update_dict:
        conditions = []
        for cond_data in update_dict["conditions"]:
            conditions.append(FilterCondition(
                field=cond_data["field"],
                operator=cond_data["operator"],
                value=cond_data["value"],
                case_sensitive=cond_data.get("case_sensitive", True),
                negate=cond_data.get("negate", False),
            ))
        update_dict["conditions"] = conditions

    # Update rule
    if not filter_feature.update_rule(rule_id, update_dict):
        raise HTTPException(status_code=400, detail="Failed to update filter rule")

    # Get updated rule
    rule = filter_feature.get_rule(rule_id)

    return FilterRuleResponse(
        id=rule.id,
        name=rule.name,
        description=rule.description,
        enabled=rule.enabled,
        priority=rule.priority,
        conditions=[
            FilterConditionModel(
                field=cond.field,
                operator=cond.operator,
                value=cond.value,
                case_sensitive=cond.case_sensitive,
                negate=cond.negate,
            )
            for cond in rule.conditions
        ],
        condition_logic=rule.condition_logic,
        actions=rule.actions,
        statistics=rule.statistics,
    )


@router.delete("/rules/{rule_id}")
async def delete_filter_rule(
    rule_id: str,
    feature_manager: FeatureManager = Depends(get_feature_manager),
):
    """Delete a filter rule."""
    filter_feature = feature_manager.get_feature("can_message_filter")
    if not filter_feature:
        raise HTTPException(status_code=404, detail="Message filter not available")

    if not filter_feature.remove_rule(rule_id):
        raise HTTPException(status_code=404, detail="Filter rule not found")

    return {"status": "success", "rule_id": rule_id}


@router.get("/statistics", response_model=FilterStatisticsResponse)
async def get_filter_statistics(
    feature_manager: FeatureManager = Depends(get_feature_manager),
):
    """Get filter statistics."""
    filter_feature = feature_manager.get_feature("can_message_filter")
    if not filter_feature:
        raise HTTPException(status_code=404, detail="Message filter not available")

    stats = filter_feature.get_statistics()
    return FilterStatisticsResponse(**stats)


@router.post("/statistics/reset")
async def reset_filter_statistics(
    feature_manager: FeatureManager = Depends(get_feature_manager),
):
    """Reset filter statistics."""
    filter_feature = feature_manager.get_feature("can_message_filter")
    if not filter_feature:
        raise HTTPException(status_code=404, detail="Message filter not available")

    filter_feature.reset_statistics()
    return {"status": "success"}


@router.get("/capture", response_model=List[CapturedMessageResponse])
async def get_captured_messages(
    limit: Optional[int] = Query(100, ge=1, le=1000),
    since_timestamp: Optional[float] = Query(None),
    feature_manager: FeatureManager = Depends(get_feature_manager),
):
    """Get captured messages."""
    filter_feature = feature_manager.get_feature("can_message_filter")
    if not filter_feature:
        raise HTTPException(status_code=404, detail="Message filter not available")

    messages = filter_feature.get_captured_messages(
        limit=limit,
        since_timestamp=since_timestamp,
    )

    return [
        CapturedMessageResponse(
            timestamp=msg.get("timestamp", 0),
            can_id=hex(msg.get("can_id", msg.get("arbitration_id", 0))),
            data=msg.get("data", ""),
            interface=msg.get("interface", ""),
            protocol=msg.get("protocol", "unknown"),
            message_type=msg.get("message_type", ""),
            decoded=msg.get("decoded"),
        )
        for msg in messages
    ]


@router.delete("/capture")
async def clear_capture_buffer(
    feature_manager: FeatureManager = Depends(get_feature_manager),
):
    """Clear the capture buffer."""
    filter_feature = feature_manager.get_feature("can_message_filter")
    if not filter_feature:
        raise HTTPException(status_code=404, detail="Message filter not available")

    filter_feature.clear_capture_buffer()
    return {"status": "success"}


@router.get("/export")
async def export_filter_rules(
    feature_manager: FeatureManager = Depends(get_feature_manager),
):
    """Export filter rules as JSON."""
    filter_feature = feature_manager.get_feature("can_message_filter")
    if not filter_feature:
        raise HTTPException(status_code=404, detail="Message filter not available")

    rules_json = filter_feature.export_rules()
    return {
        "rules": rules_json,
        "count": len(filter_feature.rules),
    }


@router.post("/import")
async def import_filter_rules(
    rules_data: Dict[str, Any],
    feature_manager: FeatureManager = Depends(get_feature_manager),
):
    """Import filter rules from JSON."""
    filter_feature = feature_manager.get_feature("can_message_filter")
    if not filter_feature:
        raise HTTPException(status_code=404, detail="Message filter not available")

    if "rules" not in rules_data:
        raise HTTPException(status_code=400, detail="Missing 'rules' field")

    imported = filter_feature.import_rules(rules_data["rules"])
    return {
        "status": "success",
        "imported": imported,
    }
