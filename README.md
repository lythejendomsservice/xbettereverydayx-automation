# xBetterEverydayx – content system

Three posts a day on @xbettereverydayx (since 27/11-2026; the followers are ~1/3 US, ~1/3 Asia/Australia):

| | Early (07:00) | Midday (13:00) | Evening (20:00) |
|---|---|---|---|
| Format | Single image | Carousel, exactly 3 slides | Single image |
| Structure | One punchy quote | Hook → Message → Action | One original quote |
| Audience | Europe morning, Asia midday | US morning, India evening | US afternoon, Europe evening |

## How it works (v2, 26/11-2026)

1. **Two scheduled Claude tasks** (claude.ai) write the day's text, caption and hashtags. The prompts are
   built from `prompts/task_template.md` with `python prompts/build_prompts.py <commit>`.
2. In the Composio workbench the task loads `prompts/renderer_inline.py` and `scripts/xbe_pipeline.py` from
   this repo **at a pinned commit, checked by SHA-256**, and calls two functions:
   - `prepare(slot)` - double-post guard + the last 30 posts (short form) for theme and performance choices;
   - `publish(content, slot)` - guard again, render + quality control, upload, Instagram, verify, Facebook.
3. The safety rules are code, not the model's judgement: publish only in the slot window (three posts a day
   since 27/11-2026: early 07:00, midday 13:00, evening 20:00 - each window 2 h, Copenhagen time), never if the slot already has a post today or anything
   went out in the last 3 hours, never if QC fails, exactly one publish call with a checked retry, Facebook
   only after a verified Instagram post, and `dry_run=True` never writes to Instagram or Facebook.

v1 (until 25/11-2026) copied the whole renderer into every run and drove ~18 tool calls; it is kept in
`prompts/archive/` for rollback.

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
margins, too-small text, low contrast. The double-post guard is in
`scripts/xbe_pipeline.py` (see "How it works").

## Testing

```
pip install -r requirements.txt
python scripts/render_test_week.py previews   # brand renderer + QC
python scripts/test_pipeline.py               # pipeline with fake Instagram/Facebook - nothing is posted
```

The GitHub workflow `render_check.yml` runs both on every change. It never publishes.

`legacy/` holds the old GitHub Actions poster (it never managed to post) for reference.
