---
version: 1.2.0
name: fal-edit
description: Edit existing images with text instructions
argument-hint: "[image_url] [prompt]"
allowed-tools: Python
---

# Fal Edit

Edit existing images with text instructions via the bridge API.

## Endpoint

`POST /fal/edit`

## Parameters

- `image_url` (required) - URL of image to edit
- `prompt` (required) - describe the changes
- `model` ("fal-ai/flux/dev/image-to-image" default)
- `strength` (0.0-1.0, default: 0.95) - higher = more change
- `num_inference_steps` (default: 40)
- `output_format` ("jpeg" or "png")
- `acceleration` ("none", "regular", "high")

## Response

`{"images": [{"url": "..."}], "seed": 123}`

## Workflow

Generate → get URL → edit that URL → iterative refinement

## Rules

- Keep prompts focused on changes only
- Show edited URL only, no narration
