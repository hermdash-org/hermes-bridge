"""
Fal.ai API client wrapper.

Based on official documentation:
https://fal.ai/docs/api-reference/client-libraries/python/fal_client
https://fal.ai/models/fal-ai/flux/schnell/api
https://fal.ai/models/fal-ai/flux-2-pro/edit/api
https://fal.ai/docs/documentation/model-apis/fal-cdn
"""

import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
import fal_client

logger = logging.getLogger("bridge.fal.client")


def _get_hermes_home() -> Path:
    """Get Hermes home directory."""
    return Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))


def _get_fal_key() -> Optional[str]:
    """
    Get FAL API key from environment.
    
    The fal_client library automatically reads from FAL_KEY environment variable,
    but we also check .env file for user convenience.
    """
    # Check environment variable first
    key = os.environ.get("FAL_KEY")
    if key:
        return key
    
    # Check .env file
    env_file = _get_hermes_home() / ".env"
    if env_file.exists():
        try:
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("FAL_KEY="):
                        key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if key:
                            # Set in environment so fal_client can read it
                            os.environ["FAL_KEY"] = key
                            return key
        except Exception as e:
            logger.error(f"Failed to read .env file: {e}")
    
    return None


def test_connection() -> Dict[str, Any]:
    """
    Test the FAL API key by making a simple request.
    
    Returns:
        {
            "success": bool,
            "message": str,
            "key_present": bool
        }
    """
    key = _get_fal_key()
    
    if not key:
        return {
            "success": False,
            "message": "FAL_KEY not found in environment or .env file",
            "key_present": False
        }
    
    try:
        # Make a minimal test request to verify the key works
        # Using flux/schnell with minimal parameters
        result = fal_client.subscribe(
            "fal-ai/flux/schnell",
            arguments={
                "prompt": "test",
                "num_images": 1,
                "image_size": "square",
                "num_inference_steps": 1
            }
        )
        
        return {
            "success": True,
            "message": "API key is valid",
            "key_present": True
        }
    except Exception as e:
        error_msg = str(e)
        logger.error(f"FAL API test failed: {error_msg}")
        
        # Check if it's an authentication error
        if "401" in error_msg or "unauthorized" in error_msg.lower():
            return {
                "success": False,
                "message": "Invalid API key",
                "key_present": True
            }
        
        return {
            "success": False,
            "message": f"API test failed: {error_msg}",
            "key_present": True
        }


def generate_image(
    prompt: str,
    model: str = "fal-ai/flux/schnell",
    num_images: int = 1,
    image_size: str = "landscape_4_3",
    num_inference_steps: int = 4,
    guidance_scale: float = 3.5,
    seed: Optional[int] = None,
    enable_safety_checker: bool = True
) -> Dict[str, Any]:
    """
    Generate images using Fal.ai models.
    
    Based on official API documentation:
    https://fal.ai/models/fal-ai/flux/schnell/api
    
    Args:
        prompt: The text prompt to generate images from
        model: Model ID (default: fal-ai/flux/schnell)
        num_images: Number of images to generate (1-4)
        image_size: Image size preset or custom {"width": int, "height": int}
        num_inference_steps: Number of inference steps (1-50)
        guidance_scale: CFG scale (0.0-20.0)
        seed: Random seed for reproducibility
        enable_safety_checker: Enable NSFW content filtering
    
    Returns:
        {
            "images": [{"url": str, "content_type": str}],
            "prompt": str,
            "seed": int,
            "has_nsfw_concepts": [bool],
            "timings": dict
        }
    """
    key = _get_fal_key()
    if not key:
        raise ValueError("FAL_KEY not configured. Please set your API key in settings.")
    
    # Build arguments according to official schema
    arguments = {
        "prompt": prompt,
        "num_images": num_images,
        "image_size": image_size,
        "num_inference_steps": num_inference_steps,
        "guidance_scale": guidance_scale,
        "enable_safety_checker": enable_safety_checker
    }
    
    # Add optional seed if provided
    if seed is not None:
        arguments["seed"] = seed
    
    logger.info(f"Generating {num_images} image(s) with model: {model}")
    logger.info(f"Prompt: {prompt[:100]}...")
    
    try:
        # Use subscribe() - it handles queue polling automatically
        # This is the recommended method from the documentation
        result = fal_client.subscribe(model, arguments=arguments)
        
        logger.info(f"Generation complete. Generated {len(result.get('images', []))} image(s)")
        return result
        
    except Exception as e:
        logger.error(f"Image generation failed: {e}", exc_info=True)
        raise


def edit_image(
    image_url: str,
    prompt: str,
    model: str = "fal-ai/flux/dev/image-to-image",
    strength: float = 0.95,
    num_inference_steps: int = 40,
    guidance_scale: float = 3.5,
    seed: Optional[int] = None,
    num_images: int = 1,
    enable_safety_checker: bool = True,
    output_format: str = "jpeg",
    acceleration: str = "none"
) -> Dict[str, Any]:
    """
    Edit an existing image using Fal.ai image-to-image models.
    
    Based on official API documentation:
    https://fal.ai/models/fal-ai/flux/dev/image-to-image/api
    
    Args:
        image_url: The URL of the image to edit (required)
        prompt: The prompt describing the desired changes (required)
        model: Model ID (default: fal-ai/flux/dev/image-to-image)
        strength: Strength of the transformation (0.0-1.0, default: 0.95)
                 Higher values = more change, lower = preserve more of original
        num_inference_steps: Number of inference steps (default: 40)
        guidance_scale: CFG scale (default: 3.5)
        seed: Random seed for reproducibility
        num_images: Number of edited images to generate (default: 1)
        enable_safety_checker: Enable NSFW content filtering (default: True)
        output_format: Output format "jpeg" or "png" (default: "jpeg")
        acceleration: Speed mode "none", "regular", or "high" (default: "none")
    
    Returns:
        {
            "images": [{"url": str, "content_type": str}],
            "prompt": str,
            "seed": int,
            "has_nsfw_concepts": [bool],
            "timings": dict
        }
    """
    key = _get_fal_key()
    if not key:
        raise ValueError("FAL_KEY not configured. Please set your API key in settings.")
    
    # Build arguments according to official schema
    arguments = {
        "image_url": image_url,
        "prompt": prompt,
        "strength": strength,
        "num_inference_steps": num_inference_steps,
        "guidance_scale": guidance_scale,
        "num_images": num_images,
        "enable_safety_checker": enable_safety_checker,
        "output_format": output_format,
        "acceleration": acceleration
    }
    
    # Add optional seed if provided
    if seed is not None:
        arguments["seed"] = seed
    
    logger.info(f"Editing image with model: {model}")
    logger.info(f"Source image: {image_url[:100]}...")
    logger.info(f"Edit prompt: {prompt[:100]}...")
    
    try:
        # Use subscribe() - it handles queue polling automatically
        result = fal_client.subscribe(model, arguments=arguments)
        
        logger.info(f"Edit complete. Generated {len(result.get('images', []))} image(s)")
        return result
        
    except Exception as e:
        logger.error(f"Image editing failed: {e}", exc_info=True)
        raise


def image_to_video(
    start_image_url: str,
    prompt: Optional[str] = None,
    model: str = "fal-ai/kling-video/v3/standard/image-to-video",
    duration: str = "5",
    generate_audio: bool = True,
    end_image_url: Optional[str] = None,
    negative_prompt: str = "blur, distort, and low quality",
    cfg_scale: float = 0.5
) -> Dict[str, Any]:
    """
    Generate video from an image using Fal.ai image-to-video models.
    
    Based on official API documentation:
    https://fal.ai/models/fal-ai/kling-video/v3/standard/image-to-video/api
    
    Args:
        start_image_url: URL of the image to animate (required)
        prompt: Text prompt for video generation (optional)
        model: Model ID (default: fal-ai/kling-video/v3/standard/image-to-video)
        duration: Video duration in seconds: "3"-"15" (default: "5")
        generate_audio: Generate native audio for the video (default: True)
        end_image_url: URL of the end frame image (optional)
        negative_prompt: What to avoid (default: "blur, distort, and low quality")
        cfg_scale: CFG scale 0.0-1.0 (default: 0.5)
    
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
    key = _get_fal_key()
    if not key:
        raise ValueError("FAL_KEY not configured. Please set your API key in settings.")
    
    # Build arguments according to official schema
    arguments = {
        "start_image_url": start_image_url,
        "duration": duration,
        "generate_audio": generate_audio,
        "negative_prompt": negative_prompt,
        "cfg_scale": cfg_scale
    }
    
    # Add optional parameters if provided
    if prompt is not None:
        arguments["prompt"] = prompt
    
    if end_image_url is not None:
        arguments["end_image_url"] = end_image_url
    
    logger.info(f"Generating video with model: {model}")
    logger.info(f"Source image: {start_image_url[:100]}...")
    if prompt:
        logger.info(f"Prompt: {prompt[:100]}...")
    
    try:
        # Use subscribe() - it handles queue polling automatically
        result = fal_client.subscribe(model, arguments=arguments)
        
        logger.info(f"Video generation complete. Video URL: {result.get('video', {}).get('url', 'N/A')}")
        return result
        
    except Exception as e:
        logger.error(f"Video generation failed: {e}", exc_info=True)
        raise


def upload_file(file_path: str) -> Dict[str, Any]:
    """
    Upload a local file to Fal CDN and return its public URL.

    Based on official SDK documentation:
    https://fal.ai/docs/api-reference/client-libraries/python/fal_client
    https://fal.ai/docs/documentation/model-apis/fal-cdn

    Method used: fal_client.upload_file(path)
    - Uploads file from local filesystem to CDN
    - Returns publicly accessible CDN URL
    - Handles large files automatically with multipart upload

    Args:
        file_path: Absolute or relative path to the local file

    Returns:
        {
            "url": str  — CDN URL (https://v3.fal.media/files/...)
        }
    """
    key = _get_fal_key()
    if not key:
        raise ValueError("FAL_KEY not configured. Please set your API key in settings.")

    path = Path(file_path)
    if not path.exists():
        raise ValueError(f"File not found: {file_path}")

    logger.info(f"Uploading file to Fal CDN: {path.name}")

    try:
        # fal_client.upload_file(path) — from SDK docs
        # Returns: str (CDN URL)
        url = fal_client.upload_file(path)

        logger.info(f"Upload complete. CDN URL: {url}")
        return {"url": url}

    except Exception as e:
        logger.error(f"File upload failed: {e}", exc_info=True)
        raise


def upload_bytes(data: bytes, content_type: str, file_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Upload raw bytes to Fal CDN and return its public URL.

    Based on official SDK documentation:
    https://fal.ai/docs/api-reference/client-libraries/python/fal_client

    Method used: fal_client.upload(data, content_type, file_name)
    - Uploads raw bytes blob to CDN
    - content_type must be a valid MIME type e.g. "image/jpeg", "image/png"

    Args:
        data: Raw file bytes
        content_type: MIME type e.g. "image/jpeg", "image/png", "image/webp"
        file_name: Optional filename hint

    Returns:
        {
            "url": str  — CDN URL (https://v3.fal.media/files/...)
        }
    """
    key = _get_fal_key()
    if not key:
        raise ValueError("FAL_KEY not configured. Please set your API key in settings.")

    logger.info(f"Uploading {len(data)} bytes ({content_type}) to Fal CDN")

    try:
        # fal_client.upload(data, content_type, file_name) — from SDK docs
        # Returns: str (CDN URL)
        url = fal_client.upload(data, content_type, file_name)

        logger.info(f"Upload complete. CDN URL: {url}")
        return {"url": url}

    except Exception as e:
        logger.error(f"Bytes upload failed: {e}", exc_info=True)
        raise


def composite_images(
    image_urls: List[str],
    prompt: str,
    image_size: str = "auto",
    seed: Optional[int] = None,
    output_format: str = "jpeg",
    safety_tolerance: str = "2",
    enable_safety_checker: bool = True
) -> Dict[str, Any]:
    """
    Composite multiple images into one using FLUX.2 [pro] Edit.

    Based on official API documentation:
    https://fal.ai/models/fal-ai/flux-2-pro/edit/api

    Model: fal-ai/flux-2-pro/edit
    - Accepts up to 9 reference images via image_urls (list of URLs)
    - Reference images in prompt using @image1, @image2, @image3 syntax
      OR natural language: "the person from image 1 with logo from image 2"
    - No masks, no inference steps to configure — pure prompt-to-edit
    - Cost: $0.03 per megapixel of output

    Input schema (from docs):
        prompt: str (required)
        image_urls: list[str] (required, up to 9 URLs)
        image_size: str | object (default: "auto")
        seed: int (optional)
        output_format: "jpeg" | "png" (default: "jpeg")
        safety_tolerance: "1"-"5" (default: "2")
        enable_safety_checker: bool (default: true)

    Output schema (from docs):
        images: [{"url": str, "content_type": str, "file_name": str, "file_size": int}]
        seed: int

    Args:
        image_urls: List of CDN/public URLs (up to 9). Use your own uploaded images.
        prompt: Describe the composition. Use @image1, @image2 to reference specific images.
                Example: "@image1 person centered, @image2 logo top-right corner, YouTube thumbnail"
        image_size: Output size preset or {"width": int, "height": int} (default: "auto")
        seed: Random seed for reproducibility
        output_format: "jpeg" or "png" (default: "jpeg")
        safety_tolerance: "1" (strictest) to "5" (most permissive) (default: "2")
        enable_safety_checker: Enable NSFW filtering (default: True)

    Returns:
        {
            "images": [{"url": str, "content_type": str, "file_name": str, "file_size": int}],
            "seed": int
        }
    """
    key = _get_fal_key()
    if not key:
        raise ValueError("FAL_KEY not configured. Please set your API key in settings.")

    if not image_urls:
        raise ValueError("At least one image URL is required.")

    if len(image_urls) > 9:
        raise ValueError("Maximum 9 images allowed per request (FLUX.2 pro limit).")

    # Build arguments from official schema
    arguments = {
        "prompt": prompt,
        "image_urls": image_urls,
        "image_size": image_size,
        "output_format": output_format,
        "safety_tolerance": safety_tolerance,
        "enable_safety_checker": enable_safety_checker
    }

    if seed is not None:
        arguments["seed"] = seed

    logger.info(f"Compositing {len(image_urls)} image(s) with FLUX.2 pro edit")
    logger.info(f"Prompt: {prompt[:100]}...")

    try:
        # fal_client.subscribe() — recommended method from SDK docs
        result = fal_client.subscribe("fal-ai/flux-2-pro/edit", arguments=arguments)

        logger.info(f"Composite complete. Output: {result.get('images', [{}])[0].get('url', 'N/A')}")
        return result

    except Exception as e:
        logger.error(f"Image compositing failed: {e}", exc_info=True)
        raise


def submit_async(
    prompt: str,
    model: str = "fal-ai/flux/schnell",
    **kwargs
) -> Dict[str, str]:
    """
    Submit an async generation request and return immediately with request_id.
    
    Use this for long-running generations where you want to poll status separately.
    
    Returns:
        {
            "request_id": str
        }
    """
    key = _get_fal_key()
    if not key:
        raise ValueError("FAL_KEY not configured")
    
    arguments = {
        "prompt": prompt,
        **kwargs
    }
    
    handle = fal_client.submit(model, arguments=arguments)
    
    return {
        "request_id": handle.request_id
    }


def get_status(model: str, request_id: str, with_logs: bool = False) -> Dict[str, Any]:
    """
    Check the status of an async generation request.
    
    Returns:
        {
            "status": "QUEUED" | "IN_PROGRESS" | "COMPLETED",
            "position": int (if queued),
            "logs": list (if with_logs=True and in progress/completed)
        }
    """
    key = _get_fal_key()
    if not key:
        raise ValueError("FAL_KEY not configured")
    
    status = fal_client.status(model, request_id, with_logs=with_logs)
    
    # Convert status object to dict
    result = {"status": status.__class__.__name__.upper()}
    
    if hasattr(status, 'position'):
        result["position"] = status.position
    
    if hasattr(status, 'logs') and status.logs:
        result["logs"] = status.logs
    
    return result


def get_result(model: str, request_id: str) -> Dict[str, Any]:
    """
    Get the result of a completed async generation request.
    
    Returns the same format as generate_image().
    """
    key = _get_fal_key()
    if not key:
        raise ValueError("FAL_KEY not configured")
    
    return fal_client.result(model, request_id)


# Available models (from documentation)
AVAILABLE_MODELS = {
    "flux-schnell": {
        "id": "fal-ai/flux/schnell",
        "name": "FLUX.1 [schnell]",
        "description": "Ultra-fast text-to-image generation (1-4 steps)",
        "speed": "fastest",
        "quality": "high"
    },
    "flux-dev": {
        "id": "fal-ai/flux/dev",
        "name": "FLUX.1 [dev]",
        "description": "High-quality text-to-image generation",
        "speed": "fast",
        "quality": "highest"
    },
    "flux-pro": {
        "id": "fal-ai/flux-pro",
        "name": "FLUX.1 [pro]",
        "description": "Professional-grade image generation",
        "speed": "medium",
        "quality": "professional"
    }
}


def list_models() -> Dict[str, Any]:
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
    return {"models": list(AVAILABLE_MODELS.values())}
