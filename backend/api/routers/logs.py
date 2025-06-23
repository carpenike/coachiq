"""
API router for log history endpoints.

Provides REST API for querying historical logs from journald.
"""

import datetime
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.services import log_history

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/logs", tags=["logs"])


class LogEntry(BaseModel):
    timestamp: str = Field(..., description="UTC ISO8601 timestamp of the log entry")
    level: int | None = Field(None, description="Syslog priority (numeric)")
    message: str = Field(..., description="Log message")
    module: str | None = Field(None, description="Logger/module name")
    cursor: str = Field(..., description="Journald cursor for pagination")


class LogHistoryResponse(BaseModel):
    entries: list[LogEntry]
    next_cursor: str | None = Field(None, description="Cursor for next page of results")
    has_more: bool = Field(..., description="True if more results are available")


def parse_query_datetime(value: str | None) -> datetime.datetime | None:
    if value is None:
        return None
    try:
        return datetime.datetime.fromisoformat(value)
    except Exception:
        return None


@router.get(
    "/history",
    response_model=LogHistoryResponse,
    summary="Get historical logs",
    description="""
    Query historical logs from journald. Supports filtering by time, level, module, and pagination via cursor.\n
    Only available on systems with systemd/journald.
    """,
    response_model_exclude_none=True,
)
def get_log_history(
    since: datetime.datetime | None = None,
    until: datetime.datetime | None = None,
    level: str | None = None,
    module: str | None = None,
    cursor: str | None = None,
    limit: int = Query(100, ge=1, le=500, description="Max number of log entries to return"),
) -> LogHistoryResponse:
    """
    Get historical logs from journald with optional filters and pagination.
    """
    filters = []
    if since:
        filters.append(f"since={since.isoformat()}")
    if until:
        filters.append(f"until={until.isoformat()}")
    if level:
        filters.append(f"level={level}")
    if module:
        filters.append(f"module={module}")
    if cursor:
        filters.append(f"cursor={cursor[:10]}...")
    filter_str = f" with filters: {', '.join(filters)}" if filters else ""

    logger.debug(f"GET /logs/history - Retrieving log history (limit={limit}){filter_str}")

    if not log_history.is_journald_available():
        logger.warning(
            "Log history requested but journald is not available on this system (likely macOS development)"
        )
        raise HTTPException(
            status_code=501,
            detail="Historical logs require systemd/journald which is not available on this system. This is expected on macOS and Windows development environments.",
        )

    try:
        result = log_history.query_journald_logs(
            since=since,
            until=until,
            level=level,
            module=module,
            cursor=cursor,
            limit=limit,
        )

        response = LogHistoryResponse(**result)
        logger.info(
            f"Retrieved {len(response.entries)} log entries{filter_str}, has_more={response.has_more}"
        )
        return response
    except Exception as e:
        logger.error(f"Error retrieving log history{filter_str}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e
