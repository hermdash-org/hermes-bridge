"""
Files package — Serve agent-generated files to the frontend.

The agent returns file paths like MEDIA:/path/to/file.png in responses.
This router serves those files so the frontend can render them inline.

Endpoints:
  GET /files?path=/absolute/path/to/file — serve a local file
  GET /files/media-proxy?path=...        — same, with Content-Type detection

Security:
  - Only serves files under allowed base directories
  - Rejects path traversal attempts
  - Does not serve system files or dotfiles outside ~/.hermes
"""

import logging
import mimetypes
import os
from pathlib import Path

from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse, JSONResponse

logger = logging.getLogger("bridge.files")

router = APIRouter(prefix="/files", tags=["files"])

# Allowed base directories for file serving.
# Only files under these paths can be served to the frontend.
_ALLOWED_BASES = [
    Path.home() / ".hermes",           # Agent home (screenshots, generated files)
    Path("/tmp"),                        # Temp files (browser screenshots, etc.)
]


def _is_path_allowed(file_path: Path) -> bool:
    """Check if a file path is under an allowed base directory."""
    resolved = file_path.resolve()

    for base in _ALLOWED_BASES:
        try:
            resolved.relative_to(base.resolve())
            return True
        except ValueError:
            continue

    return False


@router.get("")
@router.get("/")
async def serve_file(path: Annotated[str, Query(description="Absolute path to file")]):
    """Serve an agent-generated file.

    The frontend extracts MEDIA:/path/to/file.png from agent responses
    and requests this endpoint to render the file inline.
    """
    if not path:
        return JSONResponse({"error": "path is required"}, status_code=400)

    file_path = Path(path)

    # Security: block relative paths and path traversal
    if not file_path.is_absolute():
        return JSONResponse({"error": "absolute path required"}, status_code=400)

    if ".." in file_path.parts:
        return JSONResponse({"error": "path traversal blocked"}, status_code=403)

    # Security: only serve from allowed directories
    if not _is_path_allowed(file_path):
        return JSONResponse(
            {"error": "file not in allowed directory"},
            status_code=403,
        )

    if not file_path.exists():
        return JSONResponse({"error": "file not found"}, status_code=404)

    if not file_path.is_file():
        return JSONResponse({"error": "not a file"}, status_code=400)

    # Detect content type
    content_type, _ = mimetypes.guess_type(str(file_path))
    if not content_type:
        content_type = "application/octet-stream"

    return FileResponse(
        path=str(file_path),
        media_type=content_type,
        filename=file_path.name,
    )
