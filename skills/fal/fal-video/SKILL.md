---
version: 1.2.0
name: fal-video
description: Generate videos from images using Fal.ai Kling Video
argument-hint: "[image_url]"
allowed-tools: Python
---

# Fal Video

Animate images into videos via the bridge API.

## Endpoint

`POST /fal/image-to-video`

## Parameters

- `start_image_url` (required) - image to animate
- `prompt` (optional) - describe the motion
- `duration` ("3"-"15", default: "5") - seconds
- `generate_audio` (bool, default: True)
- `end_image_url` (optional) - end frame
- `cfg_scale` (0.0-1.0, default: 0.5)

## Response

`{"video": {"url": "...", "content_type": "video/mp4"}}`

## Rules

- Videos take ~30-60s to generate
- **Always display result as:** `[Watch video](url)` with the mp4 URL
- No narration, just the link
