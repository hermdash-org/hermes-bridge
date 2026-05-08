"""
FastAPI routes for Higgsfield API (SDK-based, no CLI required).

These endpoints allow the frontend and skills to use Higgsfield
without requiring the CLI to be installed.
"""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional

logger = logging.getLogger("bridge.higgsfield.api.routes")

router = APIRouter(prefix="/higgsfield-api", tags=["higgsfield-api"])


class GenerateRequest(BaseModel):
    """Request model for image/video generation."""
    model: str
    prompt: str
    arguments: Optional[Dict[str, Any]] = {}


@router.get("/status")
async def api_status():
    """
    Check if Higgsfield API is available and authenticated.
    
    Returns:
        {
            "available": bool,
            "authenticated": bool,
            "sdk_version": str or null
        }
    """
    try:
        from .auth import has_credentials
        
        authenticated = has_credentials()
        
        # Check if SDK is installed
        sdk_version = None
        try:
            import higgsfield_client
            sdk_version = getattr(higgsfield_client, "__version__", "unknown")
        except ImportError:
            pass
        
        return {
            "available": sdk_version is not None,
            "authenticated": authenticated,
            "sdk_version": sdk_version,
        }
        
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate")
async def generate(request: GenerateRequest):
    """
    Generate an image or video using Higgsfield API.
    
    Body:
        {
            "model": "nano_banana_2",
            "prompt": "a quiet beach at sunrise",
            "arguments": {
                "aspect_ratio": "16:9",
                "resolution": "2k"
            }
        }
    
    Returns:
        {
            "success": bool,
            "result": {...},  # Contains images/videos with URLs
            "request_id": str
        }
    """
    try:
        from .client import HiggsfieldAPI
        
        api = HiggsfieldAPI()
        
        # Merge prompt and arguments
        result = api.generate(
            model=request.model,
            prompt=request.prompt,
            **request.arguments
        )
        
        return {
            "success": True,
            "result": result,
            "request_id": result.get("request_id"),
        }
        
    except RuntimeError as e:
        # Authentication or SDK not installed
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.error(f"Generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/submit")
async def submit(request: GenerateRequest):
    """
    Submit a generation request without waiting.
    
    Returns immediately with a request_id for tracking.
    
    Body: Same as /generate
    
    Returns:
        {
            "success": bool,
            "request_id": str,
            "message": str
        }
    """
    try:
        from .client import HiggsfieldAPI
        
        api = HiggsfieldAPI()
        
        controller = api.submit(
            model=request.model,
            prompt=request.prompt,
            **request.arguments
        )
        
        # Get request ID from controller
        # The controller should have a request_id attribute
        request_id = getattr(controller, 'request_id', None)
        
        return {
            "success": True,
            "request_id": request_id,
            "message": "Request submitted. Use /result/{request_id} to check status.",
        }
        
    except RuntimeError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.error(f"Submit failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/result/{request_id}")
async def get_result(request_id: str):
    """
    Get result of a submitted request.
    
    Waits for completion if still processing.
    
    Returns:
        {
            "success": bool,
            "result": {...},
            "status": str
        }
    """
    try:
        from .client import HiggsfieldAPI
        
        api = HiggsfieldAPI()
        result = api.result(request_id=request_id)
        
        return {
            "success": True,
            "result": result,
            "status": "completed",
        }
        
    except RuntimeError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.error(f"Result fetch failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/check/{request_id}")
async def check_status(request_id: str):
    """
    Check status of a request without waiting.
    
    Returns:
        {
            "request_id": str,
            "status": str,  # "queued", "in_progress", "completed", "failed"
            "completed": bool
        }
    """
    try:
        from .client import HiggsfieldAPI
        import higgsfield_client
        
        api = HiggsfieldAPI()
        status = api.status(request_id=request_id)
        
        # Determine status string
        status_str = "unknown"
        completed = False
        
        if isinstance(status, higgsfield_client.Queued):
            status_str = "queued"
        elif isinstance(status, higgsfield_client.InProgress):
            status_str = "in_progress"
        elif isinstance(status, higgsfield_client.Completed):
            status_str = "completed"
            completed = True
        elif isinstance(status, (higgsfield_client.Failed, higgsfield_client.NSFW, higgsfield_client.Cancelled)):
            status_str = "failed"
            completed = True
        
        return {
            "request_id": request_id,
            "status": status_str,
            "completed": completed,
        }
        
    except RuntimeError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.error(f"Status check failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
