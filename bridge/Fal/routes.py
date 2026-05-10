"""
FastAPI routes for Fal.ai integration.
"""

import os
import logging
from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from . import client

logger = logging.getLogger("bridge.fal.routes")

router = APIRouter(prefix="/fal", tags=["fal"])


# ─── Request/Response Models ────────────────────────────────────────────


class ApiKeyRequest(BaseModel):
    api_key: str


class GenerateRequest(BaseModel):
    prompt: str
    model: Optional[str] = "fal-ai/flux/schnell"
    num_images: Optional[int] = 1
    image_size: Optional[str] = "landscape_4_3"
    num_inference_steps: Optional[int] = 4
    guidance_scale: Optional[float] = 3.5
    seed: Optional[int] = None
    enable_safety_checker: Optional[bool] = True


class AsyncGenerateRequest(BaseModel):
    prompt: str
    model: Optional[str] = "fal-ai/flux/schnell"
    num_images: Optional[int] = 1
    image_size: Optional[str] = "landscape_4_3"
    num_inference_steps: Optional[int] = 4
    guidance_scale: Optional[float] = 3.5
    seed: Optional[int] = None


class StatusRequest(BaseModel):
    model: str
    request_id: str
    with_logs: Optional[bool] = False


class EditRequest(BaseModel):
    image_url: str
    prompt: str
    model: Optional[str] = "fal-ai/flux/dev/image-to-image"
    strength: Optional[float] = 0.95
    num_inference_steps: Optional[int] = 40
    guidance_scale: Optional[float] = 3.5
    seed: Optional[int] = None
    num_images: Optional[int] = 1
    enable_safety_checker: Optional[bool] = True
    output_format: Optional[str] = "jpeg"
    acceleration: Optional[str] = "none"


class ImageToVideoRequest(BaseModel):
    start_image_url: str
    prompt: Optional[str] = None
    model: Optional[str] = "fal-ai/kling-video/v3/standard/image-to-video"
    duration: Optional[str] = "5"
    generate_audio: Optional[bool] = True
    end_image_url: Optional[str] = None
    negative_prompt: Optional[str] = "blur, distort, and low quality"
    cfg_scale: Optional[float] = 0.5


class UploadUrlRequest(BaseModel):
    file_path: str


class CompositeRequest(BaseModel):
    image_urls: List[str]
    prompt: str
    image_size: Optional[str] = "auto"
    seed: Optional[int] = None
    output_format: Optional[str] = "jpeg"
    safety_tolerance: Optional[str] = "2"
    enable_safety_checker: Optional[bool] = True


# ─── Routes ─────────────────────────────────────────────────────────────


@router.get("/status")
async def get_status():
    """
    Check if Fal.ai is configured and working.
    
    Returns:
        {
            "configured": bool,
            "api_key_present": bool
        }
    """
    key = client._get_fal_key()
    return {
        "configured": key is not None,
        "api_key_present": key is not None
    }


@router.post("/save-key")
async def save_api_key(request: ApiKeyRequest):
    """
    Save FAL API key to .env file.
    
    Body:
        {
            "api_key": str
        }
    
    Returns:
        {
            "success": bool,
            "message": str
        }
    """
    try:
        hermes_home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
        env_file = hermes_home / ".env"
        
        # Read existing .env content
        env_lines = []
        if env_file.exists():
            with open(env_file, 'r') as f:
                env_lines = f.readlines()
        
        # Update or add FAL_KEY
        key_found = False
        for i, line in enumerate(env_lines):
            if line.strip().startswith("FAL_KEY="):
                env_lines[i] = f'FAL_KEY="{request.api_key}"\n'
                key_found = True
                break
        
        if not key_found:
            env_lines.append(f'FAL_KEY="{request.api_key}"\n')
        
        # Write back to file
        with open(env_file, 'w') as f:
            f.writelines(env_lines)
        
        # Update environment variable
        os.environ["FAL_KEY"] = request.api_key
        
        logger.info("FAL API key saved successfully")
        
        return {
            "success": True,
            "message": "API key saved successfully"
        }
        
    except Exception as e:
        logger.error(f"Failed to save API key: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test")
async def test_api_key():
    """
    Test the configured FAL API key.
    
    Returns:
        {
            "success": bool,
            "message": str,
            "key_present": bool
        }
    """
    try:
        result = client.test_connection()
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["message"])
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API test failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate")
async def generate_image(request: GenerateRequest):
    """
    Generate images using Fal.ai.
    
    Body:
        {
            "prompt": str (required),
            "model": str (optional, default: "fal-ai/flux/schnell"),
            "num_images": int (optional, default: 1),
            "image_size": str (optional, default: "landscape_4_3"),
            "num_inference_steps": int (optional, default: 4),
            "guidance_scale": float (optional, default: 3.5),
            "seed": int (optional),
            "enable_safety_checker": bool (optional, default: true)
        }
    
    Returns:
        {
            "images": [{"url": str, "content_type": str}],
            "prompt": str,
            "seed": int,
            "has_nsfw_concepts": [bool],
            "timings": dict
        }
    """
    try:
        result = client.generate_image(
            prompt=request.prompt,
            model=request.model,
            num_images=request.num_images,
            image_size=request.image_size,
            num_inference_steps=request.num_inference_steps,
            guidance_scale=request.guidance_scale,
            seed=request.seed,
            enable_safety_checker=request.enable_safety_checker
        )
        
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Image generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/submit")
async def submit_async_generation(request: AsyncGenerateRequest):
    """
    Submit an async generation request.
    
    Returns immediately with a request_id that can be used to poll status.
    
    Returns:
        {
            "request_id": str
        }
    """
    try:
        result = client.submit_async(
            prompt=request.prompt,
            model=request.model,
            num_images=request.num_images,
            image_size=request.image_size,
            num_inference_steps=request.num_inference_steps,
            guidance_scale=request.guidance_scale,
            seed=request.seed
        )
        
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Async submit failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/request-status")
async def check_request_status(request: StatusRequest):
    """
    Check the status of an async generation request.
    
    Body:
        {
            "model": str,
            "request_id": str,
            "with_logs": bool (optional)
        }
    
    Returns:
        {
            "status": "QUEUED" | "IN_PROGRESS" | "COMPLETED",
            "position": int (if queued),
            "logs": list (if with_logs=True)
        }
    """
    try:
        result = client.get_status(
            model=request.model,
            request_id=request.request_id,
            with_logs=request.with_logs
        )
        
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Status check failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/result")
async def get_generation_result(request: StatusRequest):
    """
    Get the result of a completed async generation.
    
    Body:
        {
            "model": str,
            "request_id": str
        }
    
    Returns same format as /generate endpoint.
    """
    try:
        result = client.get_result(
            model=request.model,
            request_id=request.request_id
        )
        
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Result fetch failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models")
async def list_models():
    """
    List available Fal.ai models.
    
    Returns:
        {
            "models": [
                {
                    "id": str,
                    "name": str,
                    "description": str,
                    "speed": str,
                    "quality": str
                }
            ]
        }
    """
    return client.list_models()


@router.post("/edit")
async def edit_image(request: EditRequest):
    """
    Edit an existing image using Fal.ai image-to-image models.
    
    Based on official documentation:
    https://fal.ai/models/fal-ai/flux/dev/image-to-image/api
    
    Body:
        {
            "image_url": str (required) - URL of the image to edit,
            "prompt": str (required) - Description of desired changes,
            "model": str (optional, default: "fal-ai/flux/dev/image-to-image"),
            "strength": float (optional, default: 0.95) - Transformation strength (0.0-1.0),
            "num_inference_steps": int (optional, default: 40),
            "guidance_scale": float (optional, default: 3.5),
            "seed": int (optional),
            "num_images": int (optional, default: 1),
            "enable_safety_checker": bool (optional, default: true),
            "output_format": str (optional, default: "jpeg") - "jpeg" or "png",
            "acceleration": str (optional, default: "none") - "none", "regular", or "high"
        }
    
    Returns:
        {
            "images": [{"url": str, "content_type": str}],
            "prompt": str,
            "seed": int,
            "has_nsfw_concepts": [bool],
            "timings": dict
        }
    """
    try:
        result = client.edit_image(
            image_url=request.image_url,
            prompt=request.prompt,
            model=request.model,
            strength=request.strength,
            num_inference_steps=request.num_inference_steps,
            guidance_scale=request.guidance_scale,
            seed=request.seed,
            num_images=request.num_images,
            enable_safety_checker=request.enable_safety_checker,
            output_format=request.output_format,
            acceleration=request.acceleration
        )
        
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Image editing failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/image-to-video")
async def generate_video_from_image(request: ImageToVideoRequest):
    """
    Generate video from an image using Fal.ai image-to-video models.
    
    Based on official documentation:
    https://fal.ai/models/fal-ai/kling-video/v3/standard/image-to-video/api
    
    Body:
        {
            "start_image_url": str (required) - URL of the image to animate,
            "prompt": str (optional) - Text prompt for video generation,
            "model": str (optional, default: "fal-ai/kling-video/v3/standard/image-to-video"),
            "duration": str (optional, default: "5") - Duration in seconds ("3"-"15"),
            "generate_audio": bool (optional, default: true) - Generate native audio,
            "end_image_url": str (optional) - URL of the end frame,
            "negative_prompt": str (optional, default: "blur, distort, and low quality"),
            "cfg_scale": float (optional, default: 0.5) - CFG scale (0.0-1.0)
        }
    
    Returns:
        {
            "video": {
                "url": str,
                "content_type": "video/mp4",
                "file_name": str,
                "file_size": int
            }
        }
    """
    try:
        result = client.image_to_video(
            start_image_url=request.start_image_url,
            prompt=request.prompt,
            model=request.model,
            duration=request.duration,
            generate_audio=request.generate_audio,
            end_image_url=request.end_image_url,
            negative_prompt=request.negative_prompt,
            cfg_scale=request.cfg_scale
        )
        
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Video generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload-file")
async def upload_file(file: UploadFile = File(...)):
    """
    Upload a user's local image file to Fal CDN.

    Based on official SDK documentation:
    https://fal.ai/docs/api-reference/client-libraries/python/fal_client
    https://fal.ai/docs/documentation/model-apis/fal-cdn

    SDK method used: fal_client.upload(data, content_type)
    - Uploads raw bytes to CDN
    - Returns publicly accessible CDN URL

    Accepts: multipart/form-data with file field
    Supported: image/jpeg, image/png, image/webp, image/gif

    Returns:
        {
            "url": str  — CDN URL (https://v3.fal.media/files/...)
        }
    """
    try:
        data = await file.read()
        content_type = file.content_type or "image/jpeg"

        result = client.upload_bytes(
            data=data,
            content_type=content_type,
            file_name=file.filename
        )

        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"File upload failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload-path")
async def upload_from_path(request: UploadUrlRequest):
    """
    Upload a file from a local filesystem path to Fal CDN.

    Based on official SDK documentation:
    https://fal.ai/docs/api-reference/client-libraries/python/fal_client

    SDK method used: fal_client.upload_file(path)
    - Uploads file from local filesystem
    - Returns publicly accessible CDN URL

    Body:
        {
            "file_path": str  — absolute path to local file
        }

    Returns:
        {
            "url": str  — CDN URL (https://v3.fal.media/files/...)
        }
    """
    try:
        result = client.upload_file(request.file_path)
        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Path upload failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/composite")
async def composite_images(request: CompositeRequest):
    """
    Composite multiple images into one using FLUX.2 [pro] Edit.

    Based on official API documentation:
    https://fal.ai/models/fal-ai/flux-2-pro/edit/api

    Model: fal-ai/flux-2-pro/edit
    - Accepts up to 9 reference images via image_urls
    - Reference images in prompt using @image1, @image2, @image3
    - No masks needed — pure natural language compositing

    Body:
        {
            "image_urls": list[str] (required, up to 9 CDN/public URLs),
            "prompt": str (required) — describe the composition,
                      Use @image1, @image2 to reference specific images.
                      Example: "@image1 person centered, @image2 logo top-right, YouTube thumbnail",
            "image_size": str (optional, default: "auto"),
            "seed": int (optional),
            "output_format": str (optional, default: "jpeg"),
            "safety_tolerance": str (optional, default: "2"),
            "enable_safety_checker": bool (optional, default: true)
        }

    Returns:
        {
            "images": [{"url": str, "content_type": str, "file_name": str, "file_size": int}],
            "seed": int
        }
    """
    try:
        result = client.composite_images(
            image_urls=request.image_urls,
            prompt=request.prompt,
            image_size=request.image_size,
            seed=request.seed,
            output_format=request.output_format,
            safety_tolerance=request.safety_tolerance,
            enable_safety_checker=request.enable_safety_checker
        )

        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Image compositing failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
