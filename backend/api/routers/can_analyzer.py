"""
API endpoints for CAN protocol analyzer functionality.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from backend.core.dependencies import get_feature_manager_from_request
from backend.integrations.can.protocol_analyzer import (
    ProtocolAnalyzer,
    CANProtocol,
    MessageType,
    DecodedField,
    AnalyzedMessage,
    CommunicationPattern,
)


router = APIRouter()


# Response Models
class DecodedFieldResponse(BaseModel):
    """Decoded message field."""
    name: str
    value: Any
    unit: Optional[str] = None
    raw_value: Optional[int] = None
    scale: float = 1.0
    offset: float = 0.0
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    valid: bool = True


class AnalyzedMessageResponse(BaseModel):
    """Analyzed CAN message."""
    timestamp: float
    can_id: str  # Hex string
    data: str  # Hex string
    interface: str
    protocol: str
    message_type: str
    source_address: Optional[int] = None
    destination_address: Optional[int] = None
    pgn: Optional[str] = None  # Hex string
    function_code: Optional[int] = None
    decoded_fields: List[DecodedFieldResponse] = []
    description: Optional[str] = None
    warnings: List[str] = []


class CommunicationPatternResponse(BaseModel):
    """Communication pattern."""
    pattern_type: str
    participants: List[str]  # Hex CAN IDs
    interval_ms: Optional[float] = None
    confidence: float = 0.0


class ProtocolStatisticsResponse(BaseModel):
    """Protocol statistics."""
    runtime_seconds: float
    total_messages: int
    total_bytes: int
    overall_message_rate: float
    bus_utilization_percent: float
    protocols: Dict[str, Dict[str, Any]]
    detected_patterns: int
    buffer_usage: int
    buffer_capacity: int


class ProtocolReportResponse(BaseModel):
    """Protocol analysis report."""
    detected_protocols: Dict[str, Dict[str, Any]]
    communication_patterns: List[Dict[str, Any]]
    protocol_compliance: Dict[str, Dict[str, Any]]
    recommendations: List[str]


class LiveAnalysisResponse(BaseModel):
    """Live analysis data."""
    messages: List[AnalyzedMessageResponse]
    patterns: List[CommunicationPatternResponse]
    statistics: ProtocolStatisticsResponse


async def get_analyzer(request: Request) -> ProtocolAnalyzer:
    """Get protocol analyzer instance."""
    feature_manager = get_feature_manager_from_request(request)
    analyzer = feature_manager.get_feature("can_protocol_analyzer")

    if not analyzer:
        raise HTTPException(status_code=503, detail="CAN protocol analyzer not available")

    return analyzer


@router.get("/statistics", response_model=ProtocolStatisticsResponse)
async def get_statistics(analyzer: ProtocolAnalyzer = Depends(get_analyzer)):
    """Get current analyzer statistics."""
    stats = analyzer.get_statistics()
    return ProtocolStatisticsResponse(**stats)


@router.get("/report", response_model=ProtocolReportResponse)
async def get_protocol_report(analyzer: ProtocolAnalyzer = Depends(get_analyzer)):
    """Get detailed protocol analysis report."""
    report = analyzer.get_protocol_report()
    return ProtocolReportResponse(**report)


@router.get("/messages", response_model=List[AnalyzedMessageResponse])
async def get_recent_messages(
    limit: int = Query(100, ge=1, le=1000),
    protocol: Optional[CANProtocol] = None,
    message_type: Optional[MessageType] = None,
    can_id: Optional[str] = None,
    analyzer: ProtocolAnalyzer = Depends(get_analyzer),
):
    """Get recent analyzed messages with optional filtering."""
    messages = list(analyzer.message_buffer)

    # Apply filters
    if protocol:
        messages = [msg for msg in messages if msg.protocol == protocol]

    if message_type:
        messages = [msg for msg in messages if msg.message_type == message_type]

    if can_id:
        try:
            can_id_int = int(can_id, 16) if can_id.startswith("0x") else int(can_id)
            messages = [msg for msg in messages if msg.can_id == can_id_int]
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid CAN ID format")

    # Sort by timestamp descending and limit
    messages.sort(key=lambda x: x.timestamp, reverse=True)
    messages = messages[:limit]

    # Convert to response format
    response_messages = []
    for msg in messages:
        response_messages.append(
            AnalyzedMessageResponse(
                timestamp=msg.timestamp,
                can_id=f"0x{msg.can_id:08X}",
                data=msg.data.hex().upper(),
                interface=msg.interface,
                protocol=msg.protocol.value,
                message_type=msg.message_type.value,
                source_address=msg.source_address,
                destination_address=msg.destination_address,
                pgn=f"0x{msg.pgn:05X}" if msg.pgn is not None else None,
                function_code=msg.function_code,
                decoded_fields=[
                    DecodedFieldResponse(
                        name=field.name,
                        value=field.value,
                        unit=field.unit,
                        raw_value=field.raw_value,
                        scale=field.scale,
                        offset=field.offset,
                        min_value=field.min_value,
                        max_value=field.max_value,
                        valid=field.valid,
                    )
                    for field in msg.decoded_fields
                ],
                description=msg.description,
                warnings=msg.warnings,
            )
        )

    return response_messages


@router.get("/patterns", response_model=List[CommunicationPatternResponse])
async def get_communication_patterns(
    pattern_type: Optional[str] = None,
    analyzer: ProtocolAnalyzer = Depends(get_analyzer),
):
    """Get detected communication patterns."""
    patterns = analyzer.detected_patterns

    # Filter by type if specified
    if pattern_type:
        patterns = [p for p in patterns if p.pattern_type == pattern_type]

    # Convert to response format
    response_patterns = []
    for pattern in patterns[-50:]:  # Last 50 patterns
        response_patterns.append(
            CommunicationPatternResponse(
                pattern_type=pattern.pattern_type,
                participants=[f"0x{pid:08X}" for pid in pattern.participants],
                interval_ms=pattern.interval_ms,
                confidence=pattern.confidence,
            )
        )

    return response_patterns


@router.get("/protocols", response_model=Dict[str, List[str]])
async def get_detected_protocols(analyzer: ProtocolAnalyzer = Depends(get_analyzer)):
    """Get detected protocols by CAN ID."""
    result = {}

    for can_id, protocol in analyzer.detected_protocols.items():
        if protocol.value not in result:
            result[protocol.value] = []
        result[protocol.value].append(f"0x{can_id:08X}")

    return result


@router.post("/analyze")
async def analyze_message(
    can_id: str = Query(..., description="CAN ID in hex format (e.g., 0x18FEEE00)"),
    data: str = Query(..., description="Message data in hex format"),
    interface: str = Query("can0", description="CAN interface"),
    analyzer: ProtocolAnalyzer = Depends(get_analyzer),
) -> AnalyzedMessageResponse:
    """Manually analyze a specific CAN message."""
    try:
        # Parse CAN ID
        can_id_int = int(can_id, 16) if can_id.startswith("0x") else int(can_id)

        # Parse data
        data_bytes = bytes.fromhex(data.replace(" ", ""))

        # Analyze message
        analyzed = await analyzer.analyze_message(
            can_id=can_id_int,
            data=data_bytes,
            interface=interface,
        )

        # Convert to response
        return AnalyzedMessageResponse(
            timestamp=analyzed.timestamp,
            can_id=f"0x{analyzed.can_id:08X}",
            data=analyzed.data.hex().upper(),
            interface=analyzed.interface,
            protocol=analyzed.protocol.value,
            message_type=analyzed.message_type.value,
            source_address=analyzed.source_address,
            destination_address=analyzed.destination_address,
            pgn=f"0x{analyzed.pgn:05X}" if analyzed.pgn is not None else None,
            function_code=analyzed.function_code,
            decoded_fields=[
                DecodedFieldResponse(
                    name=field.name,
                    value=field.value,
                    unit=field.unit,
                    raw_value=field.raw_value,
                    scale=field.scale,
                    offset=field.offset,
                    min_value=field.min_value,
                    max_value=field.max_value,
                    valid=field.valid,
                )
                for field in analyzed.decoded_fields
            ],
            description=analyzed.description,
            warnings=analyzed.warnings,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")


@router.get("/live", response_model=LiveAnalysisResponse)
async def get_live_analysis(
    duration_seconds: int = Query(5, ge=1, le=60),
    analyzer: ProtocolAnalyzer = Depends(get_analyzer),
):
    """Get live analysis data for the specified duration."""
    # Get messages from the last N seconds
    current_time = analyzer.message_buffer[-1].timestamp if analyzer.message_buffer else 0
    start_time = current_time - duration_seconds

    recent_messages = [
        msg for msg in analyzer.message_buffer
        if msg.timestamp >= start_time
    ]

    # Get recent patterns
    recent_patterns = analyzer.detected_patterns[-10:]

    # Get current statistics
    stats = analyzer.get_statistics()

    # Convert messages
    response_messages = []
    for msg in recent_messages[-100:]:  # Limit to 100 messages
        response_messages.append(
            AnalyzedMessageResponse(
                timestamp=msg.timestamp,
                can_id=f"0x{msg.can_id:08X}",
                data=msg.data.hex().upper(),
                interface=msg.interface,
                protocol=msg.protocol.value,
                message_type=msg.message_type.value,
                source_address=msg.source_address,
                destination_address=msg.destination_address,
                pgn=f"0x{msg.pgn:05X}" if msg.pgn is not None else None,
                function_code=msg.function_code,
                decoded_fields=[
                    DecodedFieldResponse(
                        name=field.name,
                        value=field.value,
                        unit=field.unit,
                        raw_value=field.raw_value,
                        scale=field.scale,
                        offset=field.offset,
                        min_value=field.min_value,
                        max_value=field.max_value,
                        valid=field.valid,
                    )
                    for field in msg.decoded_fields
                ],
                description=msg.description,
                warnings=msg.warnings,
            )
        )

    # Convert patterns
    response_patterns = []
    for pattern in recent_patterns:
        response_patterns.append(
            CommunicationPatternResponse(
                pattern_type=pattern.pattern_type,
                participants=[f"0x{pid:08X}" for pid in pattern.participants],
                interval_ms=pattern.interval_ms,
                confidence=pattern.confidence,
            )
        )

    return LiveAnalysisResponse(
        messages=response_messages,
        patterns=response_patterns,
        statistics=ProtocolStatisticsResponse(**stats),
    )


@router.delete("/clear")
async def clear_analyzer(analyzer: ProtocolAnalyzer = Depends(get_analyzer)):
    """Clear analyzer buffers and reset statistics."""
    # Clear buffers
    analyzer.message_buffer.clear()
    analyzer.detected_patterns.clear()
    analyzer.protocol_hints.clear()
    analyzer.detected_protocols.clear()
    analyzer.sequence_tracker.clear()

    # Reset statistics
    analyzer.start_time = datetime.now().timestamp()
    analyzer.total_messages = 0
    analyzer.total_bytes = 0

    # Clear metrics
    for metrics in analyzer.protocol_metrics.values():
        metrics.message_count = 0
        metrics.byte_count = 0
        metrics.error_count = 0
        metrics.unique_ids.clear()
        metrics.message_types.clear()

    return {"status": "cleared", "timestamp": datetime.now().isoformat()}
