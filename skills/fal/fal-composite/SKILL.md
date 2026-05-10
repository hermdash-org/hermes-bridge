---
version: 1.2.0
name: fal-composite
description: Upload your own photos and composite multiple images into one
argument-hint: "[image_paths] [prompt]"
allowed-tools: Python
---

# Fal Composite

Upload your own photos then combine up to 9 images into one via the bridge API.

## Step 1 — Upload Your Photo

`POST /fal/upload-file` — multipart form upload

- Field: `file` (image/jpeg, image/png, image/webp)
- Response: `{"url": "..."}`

Or from a local path:

`POST /fal/upload-path`

- Body: `{"file_path": "/absolute/path/to/image.jpg"}`
- Response: `{"url": "..."}`

## Step 2 — Composite Into One Image

`POST /fal/composite`

## Parameters

- `image_urls` (required, list of up to 9 URLs from Step 1)
- `prompt` (required) - use `@image1`, `@image2` to reference specific images
- `image_size` (default: "auto")
- `output_format` ("jpeg" or "png", default: "jpeg")
- `safety_tolerance` ("1"-"5", default: "2")

## Response

`{"images": [{"url": "..."}], "seed": 123}`

## Thumbnail Example

Upload selfie → url1, logo → url2, background → url3

Prompt: `"@image1 person centered, @image2 logo top-right, @image3 background, YouTube thumbnail"`

## Rules

- Max 9 images per composite call
- Use @image1, @image2 in prompt for precise placement
- **Always display result as:** `![composite](url)` — never as plain text URL
- No narration, just the image
