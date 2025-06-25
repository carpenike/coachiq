"""
API endpoints for CAN bus recording and replay functionality.
"""

from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.core.dependencies import VerifiedCANFacade, get_can_bus_recorder
from backend.integrations.can.can_bus_recorder import (
    CANBusRecorder,
    RecordingFormat,
    ReplayOptions,
)

router = APIRouter(prefix="/api/can-recorder", tags=["CAN Recorder"])


# Request/Response Models
class RecordingFilters(BaseModel):
    """Filters for recording CAN messages."""

    can_ids: list[int] | None = Field(None, description="List of CAN IDs to record")
    interfaces: list[str] | None = Field(None, description="List of interfaces to record from")
    pgns: list[int] | None = Field(None, description="List of J1939 PGNs to record")


class StartRecordingRequest(BaseModel):
    """Request to start a new recording."""

    name: str = Field(..., description="Name for the recording session")
    description: str = Field("", description="Description of the recording")
    format: RecordingFormat = Field(RecordingFormat.JSON, description="Output format")
    filters: RecordingFilters | None = Field(None, description="Recording filters")


class RecordingSessionResponse(BaseModel):
    """Response with recording session details."""

    session_id: str
    name: str
    description: str
    start_time: datetime
    end_time: datetime | None
    message_count: int
    interfaces: list[str]
    filters: dict[str, Any]
    format: str
    file_path: str | None


class RecorderStatusResponse(BaseModel):
    """Response with recorder status."""

    state: str
    current_session: RecordingSessionResponse | None
    buffer_size: int
    buffer_capacity: int
    messages_recorded: int
    messages_dropped: int
    bytes_recorded: int
    filters: dict[str, Any]


class RecordingListItem(BaseModel):
    """Information about a recorded file."""

    filename: str
    path: str
    size_bytes: int
    size_mb: float
    modified: str
    format: str


class ReplayOptionsRequest(BaseModel):
    """Options for replay operation."""

    speed_factor: float = Field(1.0, description="Playback speed multiplier")
    loop: bool = Field(False, description="Loop the replay")
    start_offset: float = Field(0.0, description="Start offset in seconds")
    end_offset: float | None = Field(None, description="End offset in seconds")
    interface_mapping: dict[str, str] | None = Field(
        None, description="Map recorded to replay interfaces"
    )
    filter_can_ids: list[int] | None = Field(None, description="Only replay specific CAN IDs")


class StartReplayRequest(BaseModel):
    """Request to start replay."""

    filename: str = Field(..., description="Recording filename to replay")
    options: ReplayOptionsRequest | None = Field(None, description="Replay options")


@router.get("/status", response_model=RecorderStatusResponse)
async def get_recorder_status(recorder: Annotated[CANBusRecorder, Depends(get_can_bus_recorder)]):
    """Get current recorder status."""
    status = recorder.get_status()

    # Convert current session if present
    current_session = None
    if status["current_session"]:
        session = status["current_session"]
        current_session = RecordingSessionResponse(
            session_id=session["session_id"],
            name=session["name"],
            description=session["description"],
            start_time=datetime.fromisoformat(session["start_time"]),
            end_time=datetime.fromisoformat(session["end_time"]) if session["end_time"] else None,
            message_count=session["message_count"],
            interfaces=session["interfaces"],
            filters=session["filters"],
            format=session["format"],
            file_path=session["file_path"],
        )

    return RecorderStatusResponse(
        state=status["state"],
        current_session=current_session,
        buffer_size=status["buffer_size"],
        buffer_capacity=status["buffer_capacity"],
        messages_recorded=status["messages_recorded"],
        messages_dropped=status["messages_dropped"],
        bytes_recorded=status["bytes_recorded"],
        filters=status["filters"],
    )


@router.post("/start", response_model=RecordingSessionResponse)
async def start_recording(
    request: StartRecordingRequest,
    recorder: Annotated[CANBusRecorder, Depends(get_can_bus_recorder)],
):
    """Start a new recording session."""
    try:
        # Set filters if provided
        if request.filters:
            recorder.set_filters(
                can_ids=set(request.filters.can_ids) if request.filters.can_ids else None,
                interfaces=set(request.filters.interfaces) if request.filters.interfaces else None,
                pgns=set(request.filters.pgns) if request.filters.pgns else None,
            )

        # Start recording
        session = await recorder.start_recording(
            name=request.name,
            description=request.description,
            format=request.format,
        )

        return RecordingSessionResponse(
            session_id=session.session_id,
            name=session.name,
            description=session.description,
            start_time=session.start_time,
            end_time=session.end_time,
            message_count=session.message_count,
            interfaces=session.interfaces,
            filters=session.filters,
            format=session.format.value,
            file_path=str(session.file_path) if session.file_path else None,
        )

    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start recording: {e}")


@router.post("/stop", response_model=Optional[RecordingSessionResponse])
async def stop_recording(recorder: Annotated[CANBusRecorder, Depends(get_can_bus_recorder)]):
    """Stop the current recording session."""
    session = await recorder.stop_recording()

    if not session:
        return None

    return RecordingSessionResponse(
        session_id=session.session_id,
        name=session.name,
        description=session.description,
        start_time=session.start_time,
        end_time=session.end_time,
        message_count=session.message_count,
        interfaces=session.interfaces,
        filters=session.filters,
        format=session.format.value,
        file_path=str(session.file_path) if session.file_path else None,
    )


@router.post("/pause")
async def pause_recording(recorder: Annotated[CANBusRecorder, Depends(get_can_bus_recorder)]):
    """Pause the current recording."""
    await recorder.pause_recording()
    return {"status": "paused"}


@router.post("/resume")
async def resume_recording(recorder: Annotated[CANBusRecorder, Depends(get_can_bus_recorder)]):
    """Resume a paused recording."""
    await recorder.resume_recording()
    return {"status": "recording"}


@router.get("/list", response_model=list[RecordingListItem])
async def list_recordings(recorder: Annotated[CANBusRecorder, Depends(get_can_bus_recorder)]):
    """List all available recordings."""
    recordings = await recorder.list_recordings()

    return [
        RecordingListItem(
            filename=rec["filename"],
            path=rec["path"],
            size_bytes=rec["size_bytes"],
            size_mb=rec["size_mb"],
            modified=rec["modified"],
            format=rec["format"],
        )
        for rec in recordings
    ]


@router.delete("/{filename}")
async def delete_recording(
    filename: str,
    recorder: Annotated[CANBusRecorder, Depends(get_can_bus_recorder)],
):
    """Delete a recording file."""
    success = await recorder.delete_recording(filename)

    if not success:
        raise HTTPException(status_code=404, detail="Recording not found")

    return {"status": "deleted", "filename": filename}


@router.post("/replay/start")
async def start_replay(
    request: StartReplayRequest,
    recorder: Annotated[CANBusRecorder, Depends(get_can_bus_recorder)],
    can_service: VerifiedCANFacade,
):
    """Start replaying a recorded session."""
    try:
        # Create CAN sender callback
        async def can_sender(can_id: int, data: bytes, interface: str):
            await can_service.send_message(can_id, data, interface)

        # Configure replay options
        options = None
        if request.options:
            options = ReplayOptions(
                speed_factor=request.options.speed_factor,
                loop=request.options.loop,
                start_offset=request.options.start_offset,
                end_offset=request.options.end_offset,
                interface_mapping=request.options.interface_mapping,
                filter_can_ids=set(request.options.filter_can_ids)
                if request.options.filter_can_ids
                else None,
            )

        # Start replay
        file_path = Path(recorder.storage_path) / request.filename
        await recorder.start_replay(file_path, options, can_sender)

        return {"status": "replaying", "filename": request.filename}

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Recording file not found")
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start replay: {e}")


@router.post("/replay/stop")
async def stop_replay(recorder: Annotated[CANBusRecorder, Depends(get_can_bus_recorder)]):
    """Stop the current replay."""
    await recorder.stop_replay()
    return {"status": "stopped"}

    # @router.post("/upload")
    # async def upload_recording(
    #     file: UploadFile = File(...),
    #     recorder: CANBusRecorder = Depends(get_can_bus_recorder),
    # ):
    #     """Upload a recording file."""
    #     # Validate file extension
    #     valid_extensions = [f".{fmt.value}" for fmt in RecordingFormat]
    file_ext = Path(file.filename).suffix.lower()

    if file_ext not in valid_extensions:
        raise HTTPException(
            status_code=400, detail=f"Invalid file format. Supported: {valid_extensions}"
        )

    # Save uploaded file
    file_path = recorder.storage_path / file.filename

    try:
        contents = await file.read()
        file_path.write_bytes(contents)

        return {
            "status": "uploaded",
            "filename": file.filename,
            "size_bytes": len(contents),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")


@router.get("/download/{filename}")
async def download_recording(
    filename: str,
    recorder: Annotated[CANBusRecorder, Depends(get_can_bus_recorder)],
):
    """Download a recording file."""
    from fastapi.responses import FileResponse

    file_path = recorder.storage_path / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Recording not found")

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/octet-stream",
    )
