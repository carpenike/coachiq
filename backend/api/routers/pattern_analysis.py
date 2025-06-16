"""
Pattern Analysis API endpoints.

Provides access to CAN message pattern recognition and analysis results,
including periodicity detection, bit change analysis, and message correlations.
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/pattern-analysis",
    tags=["pattern-analysis"]
)


class PatternAnalysisResponse(BaseModel):
    """Response for pattern analysis of a specific message."""
    arbitration_id: int
    arbitration_id_hex: str
    first_seen: float
    last_seen: float
    message_count: int
    classification: str | None
    periodicity_score: float | None
    timing_analysis: dict[str, Any]
    data_analysis: dict[str, Any]
    bit_analysis: dict[str, Any]
    correlations: list[tuple[int, float]]


class PatternSummaryResponse(BaseModel):
    """Response for overall pattern analysis summary."""
    total_tracked_messages: int
    classifications: dict[str, int]
    last_analysis_time: float
    engine_status: str


def get_pattern_engine():
    """Get the pattern recognition engine from the CAN feature."""
    try:
        from backend.services.feature_manager import get_feature_manager

        feature_manager = get_feature_manager()
        can_feature = feature_manager.get_feature("can_feature")

        if not can_feature or not hasattr(can_feature, 'pattern_engine'):
            return None

        return can_feature.pattern_engine
    except Exception as e:
        logger.error(f"Error getting pattern engine: {e}")
        return None


@router.get("/summary", response_model=PatternSummaryResponse)
async def get_pattern_summary() -> PatternSummaryResponse:
    """
    Get summary of all pattern analysis results.

    Returns:
        Summary statistics for all tracked messages
    """
    pattern_engine = get_pattern_engine()
    if not pattern_engine:
        raise HTTPException(status_code=503, detail="Pattern recognition engine not available")

    try:
        summary = pattern_engine.get_all_messages_summary()
        return PatternSummaryResponse(
            total_tracked_messages=summary["total_tracked_messages"],
            classifications=summary["classifications"],
            last_analysis_time=summary["last_analysis_time"],
            engine_status=summary["engine_status"]
        )
    except Exception as e:
        logger.error(f"Error getting pattern summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/message/{arbitration_id}", response_model=PatternAnalysisResponse)
async def get_message_analysis(arbitration_id: int) -> PatternAnalysisResponse:
    """
    Get detailed pattern analysis for a specific message ID.

    Args:
        arbitration_id: CAN message arbitration ID (decimal)

    Returns:
        Detailed analysis results for the message
    """
    pattern_engine = get_pattern_engine()
    if not pattern_engine:
        raise HTTPException(status_code=503, detail="Pattern recognition engine not available")

    try:
        analysis = pattern_engine.get_message_analysis(arbitration_id)
        if not analysis:
            raise HTTPException(
                status_code=404,
                detail=f"No pattern data found for message ID {arbitration_id}"
            )

        return PatternAnalysisResponse(
            arbitration_id=analysis["arbitration_id"],
            arbitration_id_hex=analysis["arbitration_id_hex"],
            first_seen=analysis["first_seen"],
            last_seen=analysis["last_seen"],
            message_count=analysis["message_count"],
            classification=analysis["classification"],
            periodicity_score=analysis["periodicity_score"],
            timing_analysis=analysis["timing_analysis"],
            data_analysis=analysis["data_analysis"],
            bit_analysis=analysis["bit_analysis"],
            correlations=analysis["correlations"]
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting message analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/message-hex/{arbitration_id_hex}", response_model=PatternAnalysisResponse)
async def get_message_analysis_hex(arbitration_id_hex: str) -> PatternAnalysisResponse:
    """
    Get detailed pattern analysis for a specific message ID (hex format).

    Args:
        arbitration_id_hex: CAN message arbitration ID in hex format (e.g., "1FFFFFFF")

    Returns:
        Detailed analysis results for the message
    """
    try:
        # Parse hex ID (with or without 0x prefix)
        if arbitration_id_hex.lower().startswith("0x"):
            arbitration_id = int(arbitration_id_hex, 16)
        else:
            arbitration_id = int(arbitration_id_hex, 16)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid hex arbitration ID: {arbitration_id_hex}"
        )

    return await get_message_analysis(arbitration_id)


@router.get("/messages")
async def list_analyzed_messages(
    classification: Optional[str] = Query(None, description="Filter by classification"),
    min_count: int = Query(1, description="Minimum message count"),
    limit: int = Query(100, description="Maximum number of results")
) -> dict[str, Any]:
    """
    List all messages with pattern analysis data.

    Args:
        classification: Filter by message classification (periodic, event, mixed)
        min_count: Minimum number of message observations
        limit: Maximum number of results to return

    Returns:
        List of messages with basic analysis info
    """
    pattern_engine = get_pattern_engine()
    if not pattern_engine:
        raise HTTPException(status_code=503, detail="Pattern recognition engine not available")

    try:
        messages = []
        count = 0

        for arbitration_id, stats in pattern_engine.message_stats.items():
            if count >= limit:
                break

            if stats.count < min_count:
                continue

            if classification and stats.classification != classification:
                continue

            messages.append({
                "arbitration_id": arbitration_id,
                "arbitration_id_hex": f"0x{arbitration_id:08X}",
                "message_count": stats.count,
                "classification": stats.classification,
                "periodicity_score": stats.periodicity_score,
                "first_seen": stats.first_seen,
                "last_seen": stats.last_seen,
                "unique_data_count": len(stats.unique_data_values)
            })
            count += 1

        return {
            "messages": messages,
            "total_returned": len(messages),
            "filters_applied": {
                "classification": classification,
                "min_count": min_count
            }
        }
    except Exception as e:
        logger.error(f"Error listing messages: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/correlations/{arbitration_id}")
async def get_message_correlations(
    arbitration_id: int,
    min_correlation: float = Query(0.3, description="Minimum correlation threshold")
) -> dict[str, Any]:
    """
    Get messages correlated with the specified message ID.

    Args:
        arbitration_id: Target message arbitration ID
        min_correlation: Minimum correlation score (0.0-1.0)

    Returns:
        List of correlated messages with correlation scores
    """
    pattern_engine = get_pattern_engine()
    if not pattern_engine:
        raise HTTPException(status_code=503, detail="Pattern recognition engine not available")

    try:
        correlations = pattern_engine.correlation_matrix.find_correlated_messages(
            arbitration_id, min_correlation
        )

        return {
            "target_message_id": arbitration_id,
            "target_message_id_hex": f"0x{arbitration_id:08X}",
            "min_correlation": min_correlation,
            "correlations": [
                {
                    "arbitration_id": corr_id,
                    "arbitration_id_hex": f"0x{corr_id:08X}",
                    "correlation_score": score
                }
                for corr_id, score in correlations
            ],
            "total_correlations": len(correlations)
        }
    except Exception as e:
        logger.error(f"Error getting correlations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export/provisional-dbc")
async def export_provisional_dbc() -> Response:
    """
    Export discovered message patterns as a provisional DBC file.

    Returns:
        DBC file content for download
    """
    pattern_engine = get_pattern_engine()
    if not pattern_engine:
        raise HTTPException(status_code=503, detail="Pattern recognition engine not available")

    try:
        dbc_content = pattern_engine.export_provisional_dbc()

        return Response(
            content=dbc_content,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": "attachment; filename=discovered_patterns.dbc"
            }
        )
    except Exception as e:
        logger.error(f"Error exporting provisional DBC: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bit-analysis/{arbitration_id}")
async def get_bit_analysis(
    arbitration_id: int,
    min_changes: int = Query(5, description="Minimum number of bit changes")
) -> dict[str, Any]:
    """
    Get detailed bit-level analysis for a specific message.

    Args:
        arbitration_id: Message arbitration ID
        min_changes: Minimum number of changes to include a bit

    Returns:
        Detailed bit change patterns
    """
    pattern_engine = get_pattern_engine()
    if not pattern_engine:
        raise HTTPException(status_code=503, detail="Pattern recognition engine not available")

    try:
        active_bits = pattern_engine.bit_change_detector.get_active_bits(
            arbitration_id, min_changes
        )

        if arbitration_id not in pattern_engine.message_stats:
            raise HTTPException(
                status_code=404,
                detail=f"No data found for message ID {arbitration_id}"
            )

        stats = pattern_engine.message_stats[arbitration_id]

        return {
            "arbitration_id": arbitration_id,
            "arbitration_id_hex": f"0x{arbitration_id:08X}",
            "message_count": stats.count,
            "min_changes_threshold": min_changes,
            "active_bits": [
                {
                    "byte_position": bit.byte_position,
                    "bit_position": bit.bit_position,
                    "bit_address": f"{bit.byte_position}.{bit.bit_position}",
                    "change_count": bit.change_count,
                    "change_rate": bit.change_count / stats.count if stats.count > 0 else 0.0,
                    "last_change_time": bit.change_timestamps[-1] if bit.change_timestamps else None,
                    "total_changes": len(bit.change_timestamps)
                }
                for bit in active_bits
            ],
            "total_active_bits": len(active_bits)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting bit analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset")
async def reset_pattern_analysis() -> dict[str, str]:
    """
    Reset all pattern analysis data.

    This clears all accumulated pattern data and starts fresh analysis.
    Use with caution as this will lose all historical pattern information.

    Returns:
        Confirmation message
    """
    pattern_engine = get_pattern_engine()
    if not pattern_engine:
        raise HTTPException(status_code=503, detail="Pattern recognition engine not available")

    try:
        # Clear all data structures
        pattern_engine.message_stats.clear()
        pattern_engine.bit_change_detector.bit_patterns.clear()
        pattern_engine.correlation_matrix.message_events.clear()
        pattern_engine.correlation_matrix.correlation_cache.clear()

        logger.info("Pattern analysis data reset")

        return {"message": "Pattern analysis data has been reset"}
    except Exception as e:
        logger.error(f"Error resetting pattern analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))
