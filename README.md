# xBetterEverydayx – content system

Two posts a day on @xbettereverydayx:

| | Morning (06:00) | Evening (19:30) |
|---|---|---|
| Format | Carousel, exactly 3 slides | Single image |
| Structure | Hook → Message → Action | One original quote |
| Goal | Action | Reflection |

## How it works

1. **Two scheduled Claude tasks** (in claude.ai) write the day's text, caption and hashtags.
   They are the only thing that publishes.
2. They download this repo inside the Composio workbench and call
   `scripts/xbe_render.py`, which renders 1080×1350 JPEGs from the approved brand
   assets and runs quality control.
3. Only if QC passes are the images uploaded and published via Composio.
   Nothing is published if any step fails.

## Brand rules enforced in code (`scripts/xbe_render.py`)

- 1080×1350 (4:5) JPEG, safe margins, minimum readable font sizes.
- Original X mark from `assets/brand/x_mark.png` (cropped from the approved logo,
  never redrawn): 48 % of canvas width, 14 % opacity (11 % on the light variant).
- Original wordmark from `assets/brand/wordmark.png` as bottom signature.
- Colors: black #000000, white #FFFFFF, red #E10600, grey #777777, off-white #F1EEE9.
- Fonts: Montserrat (bold sans – discipline/action) and Playfair Display
  (serif – reflection). Both SIL Open Font License, bundled in `assets/fonts`.
- `*words*` in the text are drawn in brand red.

## Quality control

Rejects: wrong slide count, word counts outside the spec, non-English characters,
repeated words, slides repeating each other, 5–10 hashtag rule, caption limits,
text too similar to anything already published on the profile or to well-known
quotes, watermark size/opacity/proportions outside spec, text outside safe
margins, too-small text, low contrast. The tasks also stop if anything was
published in the last 3 hours (double-post guard).

## Testing

```
pip install -r requirements.txt
python scripts/render_test_week.py previews
```

The GitHub workflow `render_check.yml` does the same on every change. It never publishes.

`legacy/` holds the old GitHub Actions poster (it never managed to post) for reference.
