"""
Image Upload — Handle image attachments from the frontend.

Replicates gateway/run.py lines 6990-7055:
  _enrich_message_with_image_analysis() — saves images to disk,
  runs vision_analyze_tool on each, prepends text description
  to the user message.

The agent receives a plain text message with image descriptions,
NOT multimodal content. This works with ALL models (not just vision).

Single responsibility: file bytes → saved file → vision analysis → enriched text.
"""

import asyncio
import base64
import logging
import os
import uuid
from pathlib import Path

logger = logging.getLogger("bridge.image_upload")

# Directory where uploaded images are saved
_UPLOAD_DIR = Path.home() / ".hermes" / "uploads"


def _ensure_upload_dir() -> Path:
    """Create the upload directory if it doesn't exist."""
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return _UPLOAD_DIR


def save_uploaded_image(file_bytes: bytes, filename: str) -> Path:
    """Save uploaded image bytes to disk.

    Returns the absolute path to the saved file.
    """
    upload_dir = _ensure_upload_dir()

    # Generate unique filename to avoid collisions
    ext = Path(filename).suffix or ".png"
    safe_name = f"upload_{uuid.uuid4().hex[:10]}{ext}"
    file_path = upload_dir / safe_name

    file_path.write_bytes(file_bytes)
    logger.info("Saved uploaded image: %s (%d bytes)", file_path, len(file_bytes))
    return file_path


def enrich_message_with_images(user_text: str, image_paths: list[Path]) -> str:
    """Analyze uploaded images and prepend descriptions to the message.

    This is the exact pattern from gateway/run.py:6990-7055:
      _enrich_message_with_image_analysis()

    Runs vision_analyze_tool on each image, builds enriched text
    that the agent receives as a plain string message.

    Args:
        user_text: The user's original message text.
        image_paths: List of absolute paths to saved images.

    Returns:
        Enriched message string with vision descriptions prepended.
    """
    from tools.vision_tools import vision_analyze_tool
    import json

    analysis_prompt = (
        "Describe everything visible in this image in thorough detail. "
        "Include any text, code, data, objects, people, layout, colors, "
        "and any other notable visual information."
    )

    enriched_parts = []
    for path in image_paths:
        path_str = str(path)
        try:
            logger.debug("Auto-analyzing user image: %s", path_str)
            result_json = asyncio.run(
                vision_analyze_tool(
                    image_url=path_str,
                    user_prompt=analysis_prompt,
                )
            )
            result = json.loads(result_json) if isinstance(result_json, str) else {}
            if result.get("success"):
                description = result.get("analysis", "")
                enriched_parts.append(
                    f"[The user sent an image~ Here's what I can see:\n{description}]\n"
                    f"[If you need a closer look, use vision_analyze with "
                    f"image_url: {path_str} ~]"
                )
            else:
                enriched_parts.append(
                    "[The user sent an image but I couldn't quite see it "
                    "this time (>_<) You can try looking at it yourself "
                    f"with vision_analyze using image_url: {path_str}]"
                )
        except Exception as e:
            logger.error("Vision auto-analysis error: %s", e)
            enriched_parts.append(
                f"[The user sent an image but something went wrong when I "
                f"tried to look at it~ You can try examining it yourself "
                f"with vision_analyze using image_url: {path_str}]"
            )

    # Combine: vision descriptions first, then the user's original text
    if enriched_parts:
        prefix = "\n\n".join(enriched_parts)
        if user_text:
            return f"{prefix}\n\n{user_text}"
        return prefix
    return user_text


def save_base64_image(data_url: str) -> Path:
    """Save a base64 data URL image to disk.

    Accepts: data:image/png;base64,iVBOR...
    Returns: absolute path to saved file.
    """
    header, _, b64_data = data_url.partition(",")
    mime = "image/png"
    if header.startswith("data:"):
        mime_part = header[len("data:"):].split(";", 1)[0].strip()
        if mime_part.startswith("image/"):
            mime = mime_part

    ext = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/gif": ".gif",
        "image/webp": ".webp",
    }.get(mime, ".png")

    file_bytes = base64.b64decode(b64_data)
    return save_uploaded_image(file_bytes, f"image{ext}")
