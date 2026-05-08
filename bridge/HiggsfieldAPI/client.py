"""
Higgsfield API Client — Wrapper around official higgsfield-client SDK.

This provides a clean, simple interface for generating images and videos
without requiring the CLI to be installed.
"""

import logging
from typing import Dict, Any, Optional, List, Callable
from pathlib import Path

logger = logging.getLogger("bridge.higgsfield.api.client")


class HiggsfieldAPI:
    """
    Higgsfield API client using the official Python SDK.
    
    Usage:
        api = HiggsfieldAPI()
        result = api.generate(
            model="nano_banana_2",
            prompt="a quiet beach at sunrise",
            aspect_ratio="16:9"
        )
        print(result['images'][0]['url'])
    """
    
    def __init__(self):
        """Initialize the API client and set up authentication."""
        from .auth import set_env_credentials
        
        if not set_env_credentials():
            raise RuntimeError(
                "Higgsfield not authenticated. "
                "Please authenticate via Settings → Higgsfield in the dashboard."
            )
        
        # Import the SDK (will be installed as dependency)
        try:
            import higgsfield_client
            self._client = higgsfield_client
            logger.info("✓ Higgsfield SDK loaded successfully")
        except ImportError:
            raise RuntimeError(
                "higgsfield-client SDK not installed. "
                "Please install: pip install higgsfield-client"
            )
    
    def generate(
        self,
        model: str,
        prompt: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate an image or video and wait for completion.
        
        Args:
            model: Model name (e.g., "nano_banana_2", "gpt_image_2", "veo3_1")
            prompt: Text prompt describing what to generate
            **kwargs: Model-specific parameters (aspect_ratio, resolution, etc.)
        
        Returns:
            Result dict with 'images' or 'videos' key containing URLs
        
        Example:
            result = api.generate(
                model="nano_banana_2",
                prompt="modern architecture at golden hour",
                aspect_ratio="16:9",
                resolution="2k"
            )
        """
        logger.info(f"Generating with {model}: {prompt[:50]}...")
        
        try:
            result = self._client.subscribe(
                model,
                arguments={
                    'prompt': prompt,
                    **kwargs
                }
            )
            
            logger.info(f"✓ Generation complete: {model}")
            return result
            
        except Exception as e:
            logger.error(f"Generation failed: {e}", exc_info=True)
            raise
    
    async def generate_async(
        self,
        model: str,
        prompt: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Async version of generate().
        
        Use this in async contexts for better performance.
        """
        logger.info(f"Generating (async) with {model}: {prompt[:50]}...")
        
        try:
            result = await self._client.subscribe_async(
                model,
                arguments={
                    'prompt': prompt,
                    **kwargs
                }
            )
            
            logger.info(f"✓ Generation complete: {model}")
            return result
            
        except Exception as e:
            logger.error(f"Generation failed: {e}", exc_info=True)
            raise
    
    def submit(
        self,
        model: str,
        prompt: str,
        webhook_url: Optional[str] = None,
        **kwargs
    ):
        """
        Submit a generation request without waiting.
        
        Returns a RequestController for tracking progress.
        
        Args:
            model: Model name
            prompt: Text prompt
            webhook_url: Optional webhook to call on completion
            **kwargs: Model-specific parameters
        
        Returns:
            RequestController object with methods:
                - status() - Check current status
                - get() - Wait for completion and get result
                - cancel() - Cancel the request
                - poll_request_status() - Iterator for status updates
        
        Example:
            controller = api.submit("nano_banana_2", "sunset over mountains")
            
            # Option 1: Poll for status
            for status in controller.poll_request_status():
                print(f"Status: {status}")
            
            # Option 2: Just wait for result
            result = controller.get()
        """
        logger.info(f"Submitting job: {model}")
        
        try:
            controller = self._client.submit(
                model,
                arguments={
                    'prompt': prompt,
                    **kwargs
                },
                webhook_url=webhook_url
            )
            
            logger.info(f"✓ Job submitted: {model}")
            return controller
            
        except Exception as e:
            logger.error(f"Submit failed: {e}", exc_info=True)
            raise
    
    def upload_file(self, file_path: str) -> str:
        """
        Upload a file to Higgsfield.
        
        Args:
            file_path: Path to image/video/audio file
        
        Returns:
            URL of uploaded file (use in generation arguments)
        
        Example:
            url = api.upload_file("photo.jpg")
            result = api.generate(
                model="gpt_image_2",
                prompt="enhance this photo",
                image=url
            )
        """
        logger.info(f"Uploading file: {file_path}")
        
        try:
            url = self._client.upload_file(file_path)
            logger.info(f"✓ File uploaded: {url}")
            return url
            
        except Exception as e:
            logger.error(f"Upload failed: {e}", exc_info=True)
            raise
    
    def upload_image(self, image, format: str = "jpeg") -> str:
        """
        Upload a PIL Image.
        
        Args:
            image: PIL Image object
            format: Image format (jpeg, png, webp)
        
        Returns:
            URL of uploaded image
        """
        logger.info(f"Uploading PIL image (format: {format})")
        
        try:
            url = self._client.upload_image(image, format=format)
            logger.info(f"✓ Image uploaded: {url}")
            return url
            
        except Exception as e:
            logger.error(f"Upload failed: {e}", exc_info=True)
            raise
    
    def status(self, request_id: str) -> Any:
        """
        Check status of a request by ID.
        
        Args:
            request_id: Request ID from previous submission
        
        Returns:
            Status object (Queued, InProgress, Completed, Failed, etc.)
        """
        try:
            return self._client.status(request_id=request_id)
        except Exception as e:
            logger.error(f"Status check failed: {e}", exc_info=True)
            raise
    
    def result(self, request_id: str) -> Dict[str, Any]:
        """
        Wait for completion and get result by request ID.
        
        Args:
            request_id: Request ID from previous submission
        
        Returns:
            Result dict with images/videos
        """
        try:
            return self._client.result(request_id=request_id)
        except Exception as e:
            logger.error(f"Result fetch failed: {e}", exc_info=True)
            raise
    
    def cancel(self, request_id: str) -> None:
        """
        Cancel a queued request.
        
        Args:
            request_id: Request ID to cancel
        """
        try:
            self._client.cancel(request_id=request_id)
            logger.info(f"✓ Request cancelled: {request_id}")
        except Exception as e:
            logger.error(f"Cancel failed: {e}", exc_info=True)
            raise
