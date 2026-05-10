---
version: 1.0.0
name: fal-agency-prompts
description: Agency-standard prompt formulas for professional AI image generation. Use when generating product shots, ads, luxury goods, food/beverage, tech hardware, or any commercial photography.
argument-hint: "[product] [industry]"
allowed-tools: Python
---

# Professional Agency Prompts

Use these formulas with `fal-generate` for commercial-quality results.

## Golden Formula

```
[Shot Type] of [Product/Brand] resting on [Surface], featuring [Material Textures].
Lit by [Lighting Style], shot on [Camera/Lens]. [Negative Constraints].
```

## Lighting Keywords

- `Volumetric lighting` — rays of light through air
- `Rim lighting` — sharp outline around product, makes it pop
- `Softbox/diffused lighting` — soft shadows, best for skincare/beauty
- `High-contrast chiaroscuro` — dramatic luxury (watches, liquor)
- `Golden hour` — warm natural sunlight

## Camera Keywords

- `85mm or 100mm macro` — extreme close-up, sharp detail
- `35mm film` — raw authentic lifestyle look
- `Hasselblad H6D` — forces ultra-high resolution textures
- `Shallow depth of field f/1.4` — blurred background, product pops

## Texture Keywords

- `Brushed titanium`, `matte-finish`, `porous limestone`
- `Cold condensation`, `visible fabric weave`
- `Subtle dust particles in light`, `natural reflections`

## Industry Templates

**Tech/Hardware:**
```
Minimalist commercial photography of [Product] on brushed aluminum.
Harsh top-down studio lighting. Sharp focus on metallic edges.
Shot on Sony A7R IV, 100mm macro. No glowing lines, clean corporate aesthetic.
```

**Food/Beverage:**
```
High-speed splash photography of [Product] with hyper-realistic water droplets
and ice shards. 8k resolution, cinematic lighting. Shot on 1/8000 shutter speed.
Razor-sharp focus on liquid texture.
```

**Luxury/Jewelry:**
```
Editorial beauty shot of [Product] on dark velvet background.
Dramatic side-lighting, deep shadows, elegant highlights.
Shot on Hasselblad H6D. Hyper-realistic reflections.
```

## Always Add This Negative Prompt

```
gibberish text, malformed letters, neon glow, sci-fi, cyberpunk, hologram,
3D render, cartoon, plastic texture, over-saturated, glowing edges, watermark
```

## Rules

- Always combine with `fal-generate` skill
- Use `fal-ai/flux/dev` or `fal-ai/flux-pro` for commercial quality (not schnell)
- **Always display result as:** `![image](url)`
