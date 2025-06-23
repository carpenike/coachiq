"""
Pattern Analysis API endpoints.

Provides access to CAN message pattern recognition and analysis results,
including periodicity detection, bit change analysis, and message correlations.
"""

import logging
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from backend.core.dependencies import create_service_dependency

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/pattern-analysis", tags=["pattern-analysis"])

# Create service dependency
get_pattern_analysis_service = create_service_dependency("pattern_analysis_service")


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


@router.get("/summary", response_model=PatternSummaryResponse)
async def get_pattern_summary(
    pattern_service: Annotated[Any | None, Depends(get_pattern_analysis_service)],
) -> PatternSummaryResponse:
    """
    Get summary of all pattern analysis results.

    Returns:
        Summary statistics for all tracked messages
    """
    if not pattern_service:
        raise HTTPException(status_code=503, detail="Pattern analysis service not available")

    try:
        summary = await pattern_service.get_all_messages_summary()
        return PatternSummaryResponse(
            total_tracked_messages=summary["total_tracked_messages"],
            classifications=summary["classifications"],
            last_analysis_time=summary["last_analysis_time"],
            engine_status=summary["engine_status"],
        )
    except Exception as e:
        logger.error(f"Error getting pattern summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/message/{arbitration_id}", response_model=PatternAnalysisResponse)
async def get_message_analysis(
    arbitration_id: int,
    pattern_service: Annotated[Any | None, Depends(get_pattern_analysis_service)],
) -> PatternAnalysisResponse:
    """
    Get detailed pattern analysis for a specific message ID.

    Args:
        arbitration_id: CAN message arbitration ID (decimal)

    Returns:
        Detailed analysis results for the message
    """
    if not pattern_service:
        raise HTTPException(status_code=503, detail="Pattern analysis service not available")

    try:
        analysis = await pattern_service.get_message_analysis(arbitration_id)
        if not analysis:
            raise HTTPException(
                status_code=404, detail=f"No pattern data found for message ID {arbitration_id}"
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
            correlations=analysis["correlations"],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting message analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/message-hex/{arbitration_id_hex}", response_model=PatternAnalysisResponse)
async def get_message_analysis_hex(
    arbitration_id_hex: str,
    pattern_service: Annotated[Any | None, Depends(get_pattern_analysis_service)],
) -> PatternAnalysisResponse:
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
            status_code=400, detail=f"Invalid hex arbitration ID: {arbitration_id_hex}"
        )

    return await get_message_analysis(arbitration_id, pattern_service)


@router.get("/messages")
async def list_analyzed_messages(
    pattern_service: Annotated[Any | None, Depends(get_pattern_analysis_service)],
    classification: str | None = Query(None, description="Filter by classification"),
    min_count: int = Query(1, description="Minimum message count"),
    limit: int = Query(100, description="Maximum number of results"),
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
    if not pattern_service:
        raise HTTPException(status_code=503, detail="Pattern analysis service not available")

    try:
        result = await pattern_service.list_analyzed_messages(
            classification=classification, min_count=min_count, limit=limit
        )
        return result
    except Exception as e:
        logger.error(f"Error listing messages: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/correlations/{arbitration_id}")
async def get_message_correlations(
    arbitration_id: int,
    pattern_service: Annotated[Any | None, Depends(get_pattern_analysis_service)],
    min_correlation: float = Query(0.3, description="Minimum correlation threshold"),
) -> dict[str, Any]:
    """
    Get messages correlated with the specified message ID.

    Args:
        arbitration_id: Target message arbitration ID
        min_correlation: Minimum correlation score (0.0-1.0)

    Returns:
        List of correlated messages with correlation scores
    """
    if not pattern_service:
        raise HTTPException(status_code=503, detail="Pattern analysis service not available")

    try:
        result = await pattern_service.get_message_correlations(
            arbitration_id=arbitration_id, min_correlation=min_correlation
        )
        return result
    except Exception as e:
        logger.error(f"Error getting correlations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export/provisional-dbc")
async def export_provisional_dbc(
    pattern_service: Annotated[Any | None, Depends(get_pattern_analysis_service)],
) -> Response:
    """
    Export discovered message patterns as a provisional DBC file.

    Returns:
        DBC file content for download
    """
    if not pattern_service:
        raise HTTPException(status_code=503, detail="Pattern analysis service not available")

    try:
        dbc_content = await pattern_service.export_provisional_dbc()

        return Response(
            content=dbc_content,
            media_type="application/octet-stream",
            headers={"Content-Disposition": "attachment; filename=discovered_patterns.dbc"},
        )
    except Exception as e:
        logger.error(f"Error exporting provisional DBC: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bit-analysis/{arbitration_id}")
async def get_bit_analysis(
    arbitration_id: int,
    pattern_service: Annotated[Any | None, Depends(get_pattern_analysis_service)],
    min_changes: int = Query(5, description="Minimum number of bit changes"),
) -> dict[str, Any]:
    """
    Get detailed bit-level analysis for a specific message.

    Args:
        arbitration_id: Message arbitration ID
        min_changes: Minimum number of changes to include a bit

    Returns:
        Detailed bit change patterns
    """
    if not pattern_service:
        raise HTTPException(status_code=503, detail="Pattern analysis service not available")

    try:
        result = await pattern_service.get_bit_analysis(
            arbitration_id=arbitration_id, min_changes=min_changes
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting bit analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset")
async def reset_pattern_analysis(
    pattern_service: Annotated[Any | None, Depends(get_pattern_analysis_service)],
) -> dict[str, str]:
    """
    Reset all pattern analysis data.

    This clears all accumulated pattern data and starts fresh analysis.
    Use with caution as this will lose all historical pattern information.

    Returns:
        Confirmation message
    """
    if not pattern_service:
        raise HTTPException(status_code=503, detail="Pattern analysis service not available")

    try:
        await pattern_service.reset_analysis()
        logger.info("Pattern analysis data reset")
        return {"message": "Pattern analysis data has been reset"}
    except Exception as e:
        logger.error(f"Error resetting pattern analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))
