---
version: 1.2.0
name: fal-generate
description: Generate images using Fal.ai FLUX models
argument-hint: "[prompt]"
allowed-tools: Python
---

# Fal Generate

Generate images from text prompts via the bridge API.

## Endpoint

`POST /fal/generate`

## Parameters

- `prompt` (required)
- `model` ("fal-ai/flux/schnell" default, "fal-ai/flux/dev", "fal-ai/flux-pro")
- `num_images` (1-4, default: 1)
- `image_size` ("landscape_4_3", "square", "portrait_16_9")
- `num_inference_steps` (default: 4)
- `guidance_scale` (default: 3.5)
- `seed` (optional)

## Response

`{"images": [{"url": "..."}], "seed": 123}`

## Rules

- Use schnell for speed, dev for quality
- **Always display result as:** `![image](url)` — never as plain text URL
- No narration, just the image
