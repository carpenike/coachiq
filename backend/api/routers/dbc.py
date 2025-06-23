"""
DBC file import/export API endpoints.

Provides endpoints for working with industry-standard DBC (CAN Database) files,
enabling import/export of CAN message definitions.
"""

import logging
import tempfile
from pathlib import Path
from typing import Any

import cantools.database
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from backend.integrations.can.dbc_handler import get_dbc_manager
from backend.integrations.can.dbc_rvc_converter import RVCtoDBCConverter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dbc", tags=["dbc"])


class DBCUploadResponse(BaseModel):
    """Response for DBC file upload."""

    success: bool
    message: str
    messages_count: int
    nodes_count: int
    signals_count: int
    dbc_name: str


class DBCListResponse(BaseModel):
    """Response for listing loaded DBCs."""

    loaded_dbcs: list[str]
    active_dbc: str | None


class DBCMessageInfo(BaseModel):
    """Information about a CAN message in DBC."""

    id: int
    id_hex: str
    name: str
    length: int
    signals: list[dict[str, Any]]
    comment: str | None = None


class DBCExportRequest(BaseModel):
    """Request for exporting to DBC format."""

    dbc_name: str | None = None
    include_rvc_comments: bool = True


@router.post("/upload", response_model=DBCUploadResponse)
async def upload_dbc(file: UploadFile = File(...), name: str | None = None) -> DBCUploadResponse:
    """
    Upload and load a DBC file.

    Args:
        file: DBC file to upload
        name: Optional name for the DBC (defaults to filename)

    Returns:
        Upload response with DBC statistics
    """
    try:
        # Use filename as default name
        dbc_name = name or Path(file.filename).stem

        # Read file content
        content = await file.read()

        # Save to temporary file
        with tempfile.NamedTemporaryFile(suffix=f"_{file.filename}", delete=False) as temp_file:
            temp_file.write(content)
            temp_path = Path(temp_file.name)

        # Load into DBC manager
        manager = get_dbc_manager()
        await manager.load_dbc(dbc_name, temp_path)

        # Get statistics
        db = manager.get(dbc_name)
        if not db:
            raise HTTPException(status_code=500, detail="Failed to load DBC")

        messages = await db.get_message_list()
        signals_count = sum(len(msg["signals"]) for msg in messages)

        # Clean up temp file
        temp_path.unlink(missing_ok=True)

        return DBCUploadResponse(
            success=True,
            message=f"Successfully loaded DBC '{dbc_name}'",
            messages_count=len(messages),
            nodes_count=0,  # Would need to access db.db.nodes
            signals_count=signals_count,
            dbc_name=dbc_name,
        )

    except Exception as e:
        logger.error(f"Failed to upload DBC: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/list", response_model=DBCListResponse)
async def list_dbcs() -> DBCListResponse:
    """
    List all loaded DBC files.

    Returns:
        List of loaded DBCs and active DBC
    """
    manager = get_dbc_manager()
    return DBCListResponse(loaded_dbcs=list(manager.databases.keys()), active_dbc=manager.active_db)


@router.post("/active/{name}")
async def set_active_dbc(name: str) -> dict[str, str]:
    """
    Set the active DBC for decoding.

    Args:
        name: Name of DBC to make active

    Returns:
        Success message
    """
    try:
        manager = get_dbc_manager()
        manager.set_active(name)
        return {"message": f"Set active DBC to '{name}'"}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"DBC '{name}' not found")


@router.get("/messages/{name}", response_model=list[DBCMessageInfo])
async def get_dbc_messages(name: str) -> list[DBCMessageInfo]:
    """
    Get all messages from a specific DBC.

    Args:
        name: Name of the DBC

    Returns:
        List of messages with signals
    """
    manager = get_dbc_manager()
    db = manager.get(name)

    if not db:
        raise HTTPException(status_code=404, detail=f"DBC '{name}' not found")

    try:
        messages = await db.get_message_list()
        return [
            DBCMessageInfo(
                id=msg["id"],
                id_hex=msg["id_hex"],
                name=msg["name"],
                length=msg["length"],
                signals=msg["signals"],
                comment=msg.get("comment"),
            )
            for msg in messages
        ]
    except Exception as e:
        logger.error(f"Failed to get messages: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export/{name}")
async def export_dbc(name: str) -> FileResponse:
    """
    Export a loaded DBC to file.

    Args:
        name: Name of the DBC to export

    Returns:
        DBC file download
    """
    manager = get_dbc_manager()
    db = manager.get(name)

    if not db:
        raise HTTPException(status_code=404, detail=f"DBC '{name}' not found")

    if not db.db:
        raise HTTPException(status_code=500, detail="DBC not properly loaded")

    try:
        # Export to temporary file
        with tempfile.NamedTemporaryFile(suffix=f"_{name}.dbc", delete=False) as temp_file:
            temp_path = Path(temp_file.name)
        cantools.database.dump_file(db.db, str(temp_path))

        return FileResponse(
            path=temp_path, filename=f"{name}.dbc", media_type="application/octet-stream"
        )
    except Exception as e:
        logger.error(f"Failed to export DBC: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/convert/rvc-to-dbc")
async def convert_rvc_to_dbc() -> Response:
    """
    Convert current RV-C configuration to DBC format.

    Returns:
        DBC file download
    """
    try:
        # Load current RV-C configuration
        from backend.integrations.rvc import load_config_data_v2

        rvc_config_obj = load_config_data_v2()
        decoder_map = rvc_config_obj.dgn_dict

        # Create converter
        converter = RVCtoDBCConverter()

        # Convert to DBC
        rvc_config = {"decoders": decoder_map}
        db = converter.rvc_to_dbc(rvc_config)

        # Save to temporary file
        with tempfile.NamedTemporaryFile(suffix="_rvc_export.dbc", delete=False) as temp_file:
            temp_path = Path(temp_file.name)
        cantools.database.dump_file(db, str(temp_path))

        # Read and return file
        with open(temp_path, "rb") as f:
            content = f.read()

        temp_path.unlink(missing_ok=True)

        return Response(
            content=content,
            media_type="application/octet-stream",
            headers={"Content-Disposition": "attachment; filename=rvc_export.dbc"},
        )

    except Exception as e:
        logger.error(f"Failed to convert RV-C to DBC: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/convert/dbc-to-rvc")
async def convert_dbc_to_rvc(file: UploadFile = File(...)) -> dict[str, Any]:
    """
    Convert uploaded DBC file to RV-C JSON format.

    Args:
        file: DBC file to convert

    Returns:
        RV-C configuration JSON
    """
    try:
        # Read file content
        content = await file.read()

        # Save to temporary file
        with tempfile.NamedTemporaryFile(suffix=f"_{file.filename}", delete=False) as temp_file:
            temp_file.write(content)
            temp_path = Path(temp_file.name)

        # Load DBC
        db = cantools.database.load_file(str(temp_path))

        # Convert to RV-C
        converter = RVCtoDBCConverter()
        rvc_config = converter.dbc_to_rvc(db)

        # Clean up
        temp_path.unlink(missing_ok=True)

        return rvc_config

    except Exception as e:
        logger.error(f"Failed to convert DBC to RV-C: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/search/{signal_name}")
async def search_signal(signal_name: str) -> list[dict[str, Any]]:
    """
    Search for a signal across all loaded DBCs.

    Args:
        signal_name: Name of signal to search for

    Returns:
        List of matches with DBC and message info
    """
    manager = get_dbc_manager()
    results = []

    for dbc_name, db in manager.databases.items():
        try:
            signal_info = await db.find_signal(signal_name)
            if signal_info:
                results.append({"dbc_name": dbc_name, **signal_info})
        except Exception as e:
            logger.warning(f"Error searching in DBC '{dbc_name}': {e}")

    return results
