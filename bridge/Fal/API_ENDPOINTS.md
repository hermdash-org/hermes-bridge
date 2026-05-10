# Fal.ai API Endpoints - Frontend Integration Guide

## Base URL
`http://localhost:8000/fal`

---

## 1. Setup & Configuration

### GET `/fal/status`
Check if Fal.ai is configured.

**Response:**
```json
{
  "configured": true,
  "api_key_present": true
}
```

---

### POST `/fal/save-key`
Save FAL API key to `~/.hermes/.env`

**Request:**
```json
{
  "api_key": "your-fal-api-key"
}
```

**Response:**
```json
{
  "success": true,
  "message": "API key saved successfully"
}
```

---

### POST `/fal/test`
Test if the configured API key works.

**Response:**
```json
{
  "success": true,
  "message": "API key is valid",
  "key_present": true
}
```

---

## 2. Image Generation

### POST `/fal/generate`
Generate images from text prompts.

**Request:**
```json
{
  "prompt": "a cute cat wearing sunglasses",
  "model": "fal-ai/flux/schnell",
  "num_images": 1,
  "image_size": "landscape_4_3",
  "num_inference_steps": 4,
  "guidance_scale": 3.5,
  "seed": 12345,
  "enable_safety_checker": true
}
```

**Response:**
```json
{
  "images": [
    {
      "url": "https://fal.media/files/...",
      "content_type": "image/jpeg"
    }
  ],
  "prompt": "a cute cat wearing sunglasses",
  "seed": 12345,
  "has_nsfw_concepts": [false],
  "timings": {}
}
```

**Models:**
- `fal-ai/flux/schnell` - Fast (1-4 steps)
- `fal-ai/flux/dev` - High quality
- `fal-ai/flux-pro` - Professional

---

## 3. Image Editing

### POST `/fal/edit`
Edit existing images with text instructions.

**Request:**
```json
{
  "image_url": "https://fal.media/files/...",
  "prompt": "change car to blue, add fog",
  "model": "fal-ai/flux/dev/image-to-image",
  "strength": 0.95,
  "num_inference_steps": 40,
  "guidance_scale": 3.5,
  "num_images": 1,
  "output_format": "jpeg",
  "acceleration": "none"
}
```

**Response:**
```json
{
  "images": [
    {
      "url": "https://fal.media/files/...",
      "content_type": "image/jpeg"
    }
  ],
  "prompt": "change car to blue, add fog",
  "seed": 67890,
  "has_nsfw_concepts": [false],
  "timings": {}
}
```

**Parameters:**
- `strength`: 0.0-1.0 (higher = more change)
- `acceleration`: "none", "regular", "high"
- `output_format`: "jpeg", "png"

---

## 4. Video Generation

### POST `/fal/image-to-video`
Generate video from an image.

**Request:**
```json
{
  "start_image_url": "https://fal.media/files/...",
  "prompt": "camera slowly orbits around the object",
  "model": "fal-ai/kling-video/v3/standard/image-to-video",
  "duration": "5",
  "generate_audio": true,
  "negative_prompt": "blur, distort, and low quality",
  "cfg_scale": 0.5
}
```

**Response:**
```json
{
  "video": {
    "url": "https://storage.googleapis.com/...",
    "content_type": "video/mp4",
    "file_name": "out.mp4",
    "file_size": 3149129
  }
}
```

**Parameters:**
- `duration`: "3" to "15" (seconds)
- `generate_audio`: true/false (native audio generation)
- `end_image_url`: Optional end frame

---

## 5. Async Operations (Optional)

### POST `/fal/submit`
Submit async generation (returns immediately).

**Request:**
```json
{
  "prompt": "a cute cat",
  "model": "fal-ai/flux/schnell"
}
```

**Response:**
```json
{
  "request_id": "764cabcf-b745-4b3e-ae38-1200304cf45b"
}
```

---

### POST `/fal/request-status`
Check status of async request.

**Request:**
```json
{
  "model": "fal-ai/flux/schnell",
  "request_id": "764cabcf-b745-4b3e-ae38-1200304cf45b",
  "with_logs": false
}
```

**Response:**
```json
{
  "status": "COMPLETED",
  "position": 0
}
```

---

### POST `/fal/result`
Get result of completed async request.

**Request:**
```json
{
  "model": "fal-ai/flux/schnell",
  "request_id": "764cabcf-b745-4b3e-ae38-1200304cf45b"
}
```

**Response:** Same as `/fal/generate`

---

## 6. Utilities

### GET `/fal/models`
List available models.

**Response:**
```json
{
  "models": [
    {
      "id": "fal-ai/flux/schnell",
      "name": "FLUX.1 [schnell]",
      "description": "Ultra-fast text-to-image generation (1-4 steps)",
      "speed": "fastest",
      "quality": "high"
    }
  ]
}
```

---

## Frontend Workflow Examples

### 1. Generate Image
```javascript
// 1. Check status
const status = await fetch('/fal/status').then(r => r.json());

// 2. If not configured, save key
if (!status.configured) {
  await fetch('/fal/save-key', {
    method: 'POST',
    body: JSON.stringify({ api_key: userKey })
  });
}

// 3. Generate
const result = await fetch('/fal/generate', {
  method: 'POST',
  body: JSON.stringify({
    prompt: "a cute cat",
    model: "fal-ai/flux/schnell"
  })
});

const { images } = await result.json();
console.log(images[0].url);
```

---

### 2. Generate → Edit → Video
```javascript
// Step 1: Generate
const gen = await fetch('/fal/generate', {
  method: 'POST',
  body: JSON.stringify({ prompt: "red car on street" })
}).then(r => r.json());

const imageUrl = gen.images[0].url;

// Step 2: Edit
const edit = await fetch('/fal/edit', {
  method: 'POST',
  body: JSON.stringify({
    image_url: imageUrl,
    prompt: "change car to blue"
  })
}).then(r => r.json());

const editedUrl = edit.images[0].url;

// Step 3: Animate
const video = await fetch('/fal/image-to-video', {
  method: 'POST',
  body: JSON.stringify({
    start_image_url: editedUrl,
    prompt: "camera orbits around car",
    duration: "5"
  })
}).then(r => r.json());

console.log(video.video.url);
```

---

## Error Handling

All endpoints return standard HTTP status codes:
- `200` - Success
- `400` - Bad request (invalid parameters)
- `500` - Server error

**Error Response:**
```json
{
  "detail": "FAL_KEY not configured. Please set your API key in settings."
}
```

---

## Notes for Frontend

1. **API Key Setup**: User enters key once, saved to `~/.hermes/.env`
2. **No OAuth**: Simple API key authentication
3. **Image URLs**: All image/video URLs are publicly accessible
4. **Async Optional**: Use `/generate` for simple sync, `/submit` for async
5. **Video Takes Time**: Image-to-video ~30-60 seconds
6. **Skills Auto-loaded**: Agent knows how to use these endpoints via skills

---

## Backend Status: ✅ READY FOR FRONTEND

All endpoints implemented, tested, and registered in `app.py`.
