You are the automated publisher for @xbettereverydayx (Creative Director + copywriter).
Run unattended; do not ask questions. SLOT = evening  (morning | evening)

The brand renderer and quality control are included below (step 3); the brand fonts and logo
files live in the public GitHub repo lythejendomsservice/xbettereverydayx-automation.
Never draw your own images, never change the logo, never skip quality control.

## 0. Setup
Load the Composio tools with ToolSearch (COMPOSIO_SEARCH_TOOLS, COMPOSIO_MULTI_EXECUTE_TOOL,
COMPOSIO_REMOTE_WORKBENCH). Call COMPOSIO_SEARCH_TOOLS once (query "create instagram carousel
post", session generate_id true) and pass that session_id to every later Composio call.
Instagram account: "instagram_stylet-manful", ig_user_id "30053245364263763".

## 1. Double-post guard + history
COMPOSIO_MULTI_EXECUTE_TOOL -> INSTAGRAM_GET_IG_USER_MEDIA {ig_user_id:"me", limit:100,
fields:"id,caption,timestamp,like_count,comments_count"}.
- If ANY post has a timestamp within the last 3 hours: STOP. Publish nothing. (Already posted.)
- Keep all captions; they are the originality history.
- Run `TZ=Europe/Copenhagen date +%u` in Bash to get today's weekday (1=Mon ... 7=Sun).

## 2. Write today's content (English)
Mission: help people become the best version of themselves through discipline, consistency,
self-respect, accountability, ambition and growth. Not a generic quote page. Direct, honest,
sometimes uncomfortable. Every text must be ORIGINAL: no famous quotes, no close variations of
anything in the history. Do not reuse the style examples.

Editorial balance over time (guide, not quota): 35% discipline/self-improvement, 20%
mindset/accountability, 15% ambition/success, 15% relationships/self-respect, 10% life
lessons/reflection, 5% confidence/mental strength. Look at the last ~10 captions and pick a
theme that has NOT been used recently.

Learn from performance: among the last ~30 posts, compare likes + comments (ignore comments
that are just "send me this post" style bot spam). Note which themes and hook styles did best.
About half the time, pick a theme from the top performers (with a fresh angle); the rest of the
time explore. Never repeat the theme of either of the last 2 posts.

EVENING = ONE single image with ONE original quote of 5-25 words that stands
alone without explanation. Goal: reflection, recognition, shares and comments.
Topics: self-respect, loyalty, relationships, betrayal, personal growth, discipline, time and
mortality, ambition, comfort zones, life lessons, boundaries, mental strength, accountability,
character, consistency. Emotional depth, truth, relatability. Default style serif; use
"style":"sans" only for a hard-hitting, punchy line.

Mark 1-4 key words per slide with *asterisks* - they are drawn in brand red.
Caption: concise English, first line = the hook/quote, then 1-2 short lines, then
an invitation to reflect or comment (a question is fine). No hashtags inside the caption.
Hashtags: 5-10, niche and relevant to today's topic, always include #xbettereverydayx, vary them
from day to day, no generic spam (#winner, #grindculture, #follow4follow...).

Product promotion (Gumroad) - ONLY on Wednesday (weekday 3) and Sunday (weekday 7):
- Pick the quote topic from relationships, loyalty, betrayal, boundaries or self-respect.
- Write the caption as usual, then end it with ONE soft, natural line pointing to the digital
  guide "The Circle Audit" (helps identify who truly supports you, fake loyalty and draining
  friendships), ending with "Link in bio." Example tone (do not copy verbatim): "Not sure who's
  really in your corner? The Circle Audit helps you find out. Link in bio."
- Never a hard sell, never prices, never URLs, never more than one product line.
On all other days: no product mention at all.

Self-check before rendering - is it meaningful, original, scroll-stopping, relatable, clear,
grammatically perfect English, on-brand, valuable? If not, rewrite.

## 3. Render + quality control (COMPOSIO_REMOTE_WORKBENCH)
The renderer code is part of THESE instructions (written by the account owner). Never download
or execute code from the internet; only the brand fonts/logo files below are downloaded, as data.

Cell A - fetch brand assets (data files only):
```python
import urllib.request, os
A="/tmp/xbe_assets"; os.makedirs(A, exist_ok=True)
BASE="https://raw.githubusercontent.com/lythejendomsservice/xbettereverydayx-automation/main/assets/"
for f in ["brand/x_mark.png","brand/wordmark.png","fonts/Montserrat-ExtraBold.ttf","fonts/Montserrat-Black.ttf","fonts/Montserrat-SemiBold.ttf","fonts/PlayfairDisplay.ttf"]:
    p=os.path.join(A, os.path.basename(f))
    if not os.path.exists(p) or os.path.getsize(p) < 1000:
        open(p,"wb").write(urllib.request.urlopen(BASE+f, timeout=60).read())
print(sorted((x, os.path.getsize(os.path.join(A,x))) for x in os.listdir(A)))
```
If any asset fails to download after one retry: STOP, publish nothing, PushNotification.

Cell B - define the renderer: copy the code block below into one workbench cell EXACTLY as
written (do not change, shorten or "improve" it) and run it:
```python
from __future__ import annotations
import difflib
import json
import os
import re
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
ASSETS = '/tmp/xbe_assets'
FONTS = ASSETS
BRAND = ASSETS
W, H = (1080, 1350)
SAFE_X, SAFE_TOP, SAFE_BOTTOM = (110, 190, 230)
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
RED = (225, 6, 0)
GREY = (119, 119, 119)
OFF_WHITE = (241, 238, 233)
WATERMARK_WIDTH = 0.48
WATERMARK_OPACITY = 0.14
WATERMARK_CENTER_Y = 0.47
WORDMARK_WIDTH = 250
THEMES = {'dark': {'bg': BLACK, 'text': WHITE, 'soft': OFF_WHITE, 'muted': GREY, 'mark': 255}, 'light': {'bg': OFF_WHITE, 'text': BLACK, 'soft': (30, 30, 30), 'muted': GREY, 'mark': 0}}
FONT_FILES = {'sans': 'Montserrat-ExtraBold.ttf', 'sans_black': 'Montserrat-Black.ttf', 'sans_small': 'Montserrat-SemiBold.ttf', 'serif': 'PlayfairDisplay.ttf', }
ROLE_DEFAULTS = {'hook': {'style': 'sans', 'max': 116, 'min': 64, 'upper': True, 'lh': 1.08, 'max_lines': 6}, 'message': {'style': 'serif', 'max': 74, 'min': 46, 'upper': False, 'lh': 1.3, 'max_lines': 9}, 'action': {'style': 'sans', 'max': 108, 'min': 60, 'upper': True, 'lh': 1.08, 'max_lines': 7}, 'quote': {'style': 'serif', 'max': 92, 'min': 52, 'upper': False, 'lh': 1.24, 'max_lines': 8}}
SANS_OVERRIDE = {'max': 104, 'min': 58, 'upper': True, 'lh': 1.08}
SERIF_OVERRIDE = {'max': 80, 'min': 48, 'upper': False, 'lh': 1.26}
WORD_LIMITS = {'hook': (4, 12), 'message': (8, 45), 'action': (3, 16), 'quote': (5, 25)}
MAX_SENTENCES_MESSAGE = 3
BANNED_TEXTS = ['not everyone who stands beside you stands with you', "your habits are building the life you'll eventually live", 'stop explaining your worth to people who refuse to see it', "time doesn't wait for people who are afraid to start", 'your future is watching what you do today', "you didn't come this far to only come this far", 'discipline is choosing between what you want now and what you want most', 'the pain of discipline is far less than the pain of regret', 'do something today that your future self will thank you for', "don't wish for it work for it", 'dream big work hard stay humble', 'be the change you wish to see in the world']
SIMILARITY_LIMIT = 0.72

def _font(key: str, size: int, weight: int | None=None) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(os.path.join(FONTS, FONT_FILES[key]), size)
    if weight is not None:
        try:
            f.set_variation_by_axes([weight])
        except Exception:
            pass
    return f

def _norm(text: str) -> str:
    t = text.lower().replace('*', '').replace('’', "'")
    t = re.sub("[^a-z0-9' ]+", ' ', t)
    return re.sub('\\s+', ' ', t).strip()

def _tokens(text: str) -> list[tuple[str, bool]]:
    out, accent = ([], False)
    for part in re.split('(\\*)', text):
        if part == '*':
            accent = not accent
            continue
        for w in part.split():
            out.append((w, accent))
    return out

def _wrap(words, font, max_w, draw):
    lines, cur = ([], [])
    space = draw.textlength(' ', font=font)
    cur_w = 0.0
    for w, acc in words:
        ww = draw.textlength(w, font=font)
        if cur and cur_w + space + ww > max_w:
            lines.append(cur)
            cur, cur_w = ([(w, acc)], ww)
        else:
            cur_w = ww if not cur else cur_w + space + ww
            cur.append((w, acc))
    if cur:
        lines.append(cur)
    if len(lines) >= 2 and len(lines[-1]) == 1 and (len(lines[-2]) >= 3):
        moved = lines[-2].pop()
        lines[-1].insert(0, moved)
        if _line_w(lines[-1], font, draw) > max_w:
            lines[-1].pop(0)
            lines[-2].append(moved)
    return lines

def _line_w(line, font, draw):
    space = draw.textlength(' ', font=font)
    return sum((draw.textlength(w, font=font) for w, _ in line)) + space * (len(line) - 1)

def _background(theme: dict) -> Image.Image:
    bg = Image.new('RGB', (W, H), theme['bg'])
    if theme is THEMES['dark']:
        yy, xx = np.mgrid[0:H, 0:W]
        d = np.sqrt(((xx - W / 2) / W) ** 2 + ((yy - H * 0.47) / H) ** 2)
        lift = np.clip(14 * (1 - d / 0.75), 0, 14).astype(np.uint8)
        bg = Image.fromarray(np.dstack([lift, lift, lift]))
    return bg

def _paste_mark(canvas: Image.Image, path: str, width: int, center: tuple[int, int], opacity: float, value: int) -> dict:
    src = Image.open(path).convert('L')
    h = round(src.height * width / src.width)
    mask = src.resize((width, h), Image.LANCZOS)
    mask = mask.point(lambda p: int(p * opacity))
    fill = Image.new('RGB', mask.size, (value, value, value))
    x, y = (center[0] - width // 2, center[1] - h // 2)
    canvas.paste(fill, (x, y), mask)
    return {'width': width, 'height': h, 'x': x, 'y': y, 'opacity': opacity, 'width_ratio': round(width / W, 3), 'aspect_src': round(src.width / src.height, 4), 'aspect_out': round(width / h, 4)}

def _fit(words, role_cfg, font_key, draw, box_w, box_h):
    for size in range(role_cfg['max'], role_cfg['min'] - 1, -2):
        font = _font(font_key, size)
        lines = _wrap(words, font, box_w, draw)
        lh = int(size * role_cfg['lh'])
        if len(lines) <= role_cfg['max_lines'] and lh * len(lines) <= box_h and all((_line_w(l, font, draw) <= box_w for l in lines)):
            return (size, font, lines, lh)
    return None

def render_slide(text: str, role: str, style: str | None, theme_name: str, index: int, total: int) -> tuple[Image.Image, dict]:
    theme = THEMES[theme_name]
    cfg = dict(ROLE_DEFAULTS[role])
    style = style or cfg['style']
    if style != cfg['style']:
        cfg.update(SANS_OVERRIDE if style == 'sans' else SERIF_OVERRIDE)
    font_key = ('sans_black' if role == 'action' else 'sans') if style == 'sans' else 'serif'
    img = _background(theme)
    wm = _paste_mark(img, os.path.join(BRAND, 'x_mark.png'), int(W * WATERMARK_WIDTH), (W // 2, int(H * WATERMARK_CENTER_Y)), WATERMARK_OPACITY if theme_name == 'dark' else 0.11, theme['mark'])
    sig = _paste_mark(img, os.path.join(BRAND, 'wordmark.png'), WORDMARK_WIDTH, (W // 2, H - 110), 0.55 if theme_name == 'dark' else 0.7, theme['mark'])
    draw = ImageDraw.Draw(img)
    shown = text.upper() if cfg['upper'] else text
    words = _tokens(shown)
    box_w = W - 2 * SAFE_X
    box_h = H - SAFE_TOP - SAFE_BOTTOM
    fit = _fit(words, cfg, font_key, draw, box_w, box_h)
    info = {'role': role, 'style': style, 'theme': theme_name, 'watermark': wm, 'wordmark': sig}
    if fit is None:
        info['error'] = 'text does not fit at minimum readable size - shorten it'
        return (img, info)
    size, font, lines, lh = fit
    block_h = lh * len(lines)
    top = SAFE_TOP + (box_h - block_h) // 2 - 10
    rule_y = top - 46
    draw.rectangle([W // 2 - 34, rule_y, W // 2 + 34, rule_y + 5], fill=RED)
    base_color = theme['text'] if style == 'sans' or role == 'quote' else theme['soft']
    space = draw.textlength(' ', font=font)
    ascent, _ = font.getmetrics()
    bboxes = []
    for i, line in enumerate(lines):
        lw = _line_w(line, font, draw)
        x = (W - lw) / 2
        y = top + i * lh + (lh - size) // 2
        for w, acc in line:
            draw.text((x, y), w, font=font, fill=RED if acc else base_color)
            b = draw.textbbox((x, y), w, font=font)
            bboxes.append(b)
            x += draw.textlength(w, font=font) + space
    if total > 1:
        cf = _font('sans_small', 26)
        label = f'{index + 1:02d} / {total:02d}'
        draw.text((SAFE_X, 92), label, font=cf, fill=theme['muted'])
        if index < total - 1:
            arrow = 'SWIPE  →'
            aw = draw.textlength(arrow, font=cf)
            draw.text((W - SAFE_X - aw, 92), arrow, font=cf, fill=theme['muted'])
    xs0 = min((b[0] for b in bboxes))
    ys0 = min((b[1] for b in bboxes))
    xs1 = max((b[2] for b in bboxes))
    ys1 = max((b[3] for b in bboxes))
    info.update({'font_size': size, 'lines': [' '.join((w for w, _ in l)) for l in lines], 'text_bbox': [round(xs0), round(ys0), round(xs1), round(ys1)], 'text_color': base_color, 'bg_color': theme['bg']})
    return (img, info)

def _contrast(c1, c2) -> float:

    def lum(c):
        v = []
        for x in c:
            x = x / 255
            v.append(x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4)
        return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]
    a, b = sorted([lum(c1), lum(c2)], reverse=True)
    return (a + 0.05) / (b + 0.05)

def qc_content(c: dict, history: list[str]) -> list[str]:
    errs = []
    t = c.get('type')
    slides = c.get('slides') or []
    if t not in ('morning', 'evening'):
        return [f"type must be 'morning' or 'evening', got {t!r}"]
    want = 3 if t == 'morning' else 1
    if len(slides) != want:
        errs.append(f'{t} needs exactly {want} slide(s), got {len(slides)}')
    roles = ['hook', 'message', 'action'] if t == 'morning' else ['quote']
    texts = []
    for i, (s, role) in enumerate(zip(slides, roles)):
        txt = (s.get('text') or '').strip()
        texts.append(txt)
        n = len(_norm(txt).split())
        lo, hi = WORD_LIMITS[role]
        if not lo <= n <= hi:
            errs.append(f'slide {i + 1} ({role}): {n} words, allowed {lo}-{hi}')
        if txt.count('*') % 2:
            errs.append(f'slide {i + 1}: unbalanced *accent* markup')
        if re.search('[^\\x20-\\x7E’‘“”—–]', txt):
            errs.append(f'slide {i + 1}: non-English / unsupported characters')
        if re.search('\\b(\\w+) \\1\\b', _norm(txt)):
            errs.append(f'slide {i + 1}: repeated word')
        if '  ' in txt.replace('*', ''):
            errs.append(f'slide {i + 1}: double space')
        if role == 'message':
            sentences = [x for x in re.split('[.!?]+', txt) if x.strip()]
            if len(sentences) > MAX_SENTENCES_MESSAGE:
                errs.append(f'slide 2: {len(sentences)} sentences, max {MAX_SENTENCES_MESSAGE}')
        if s.get('style') not in (None, 'sans', 'serif'):
            errs.append(f'slide {i + 1}: style must be sans or serif')
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            if difflib.SequenceMatcher(None, _norm(texts[i]), _norm(texts[j])).ratio() > 0.6:
                errs.append(f'slides {i + 1} and {j + 1} repeat the same text')
    for i, txt in enumerate(texts):
        nt = _norm(txt)
        for ref in BANNED_TEXTS + [_norm(h) for h in history]:
            if not ref:
                continue
            r = difflib.SequenceMatcher(None, nt, ref).ratio()
            contained = len(nt) > 25 and (nt in ref or ref in nt)
            if r >= SIMILARITY_LIMIT or contained:
                errs.append(f'slide {i + 1} too similar to an existing/published text ({r:.2f}): {ref[:70]!r}')
                break
    cap = (c.get('caption') or '').strip()
    tags = c.get('hashtags') or []
    if len(cap) < 40:
        errs.append('caption missing or too short')
    if re.search('#\\w', cap):
        errs.append("put hashtags in 'hashtags', not inside the caption")
    if not 5 <= len(tags) <= 10:
        errs.append(f'{len(tags)} hashtags, need 5-10')
    if len(set((x.lower() for x in tags))) != len(tags):
        errs.append('duplicate hashtags')
    for tg in tags:
        if not re.fullmatch('#[A-Za-z0-9_]{2,40}', tg):
            errs.append(f'invalid hashtag {tg!r}')
    if len(full_caption(c)) > 2200:
        errs.append("caption exceeds Instagram's 2200 characters")
    if re.search('[^\\x09\\x0A\\x0D\\x20-\\x7E’‘“”—–…→]', cap):
        errs.append('caption contains non-English / unsupported characters')
    return errs

def qc_image(img: Image.Image, info: dict) -> list[str]:
    errs = []
    if img.size != (W, H):
        errs.append(f'size {img.size}, expected {(W, H)}')
    if 'error' in info:
        return errs + [info['error']]
    wm = info['watermark']
    if not 0.35 <= wm['width_ratio'] <= 0.55:
        errs.append(f"watermark width {wm['width_ratio']:.0%} outside 35-55 %")
    if not 0.08 <= wm['opacity'] <= 0.15:
        errs.append(f"watermark opacity {wm['opacity']:.0%} outside 8-15 %")
    if abs(wm['aspect_src'] - wm['aspect_out']) > 0.02:
        errs.append('watermark proportions distorted')
    arr = np.asarray(img.convert('L')).astype(float)
    x, y, w, h = (wm['x'], wm['y'], wm['width'], wm['height'])
    mark = np.asarray(Image.open(os.path.join(BRAND, 'x_mark.png')).convert('L').resize((w, h))) > 128
    region = arr[y:y + h, x:x + w]
    text_free = region[mark]
    if text_free.size == 0 or abs(np.median(text_free) - np.median(region[~mark])) < 6:
        errs.append('watermark not visible enough')
    x0, y0, x1, y1 = info['text_bbox']
    if x0 < SAFE_X - 4 or x1 > W - SAFE_X + 4 or y0 < SAFE_TOP - 60 or (y1 > H - SAFE_BOTTOM + 30):
        errs.append(f"text outside safe margins {info['text_bbox']}")
    minimum = 46 if info['style'] == 'serif' else 56
    if info['font_size'] < minimum:
        errs.append(f"font size {info['font_size']}px too small for mobile")
    if _contrast(info['text_color'], info['bg_color']) < 7:
        errs.append('text contrast too low')
    return errs

def history_from_captions(captions: list[str]) -> list[str]:
    out = []
    for cap in captions:
        if not cap:
            continue
        text = re.sub('#\\w+', ' ', cap)
        out.append(text)
        out += [ln.strip() for ln in text.splitlines() if len(ln.strip()) > 20]
    return out

def full_caption(c: dict) -> str:
    return (c.get('caption') or '').strip() + '\n\n' + ' '.join(c.get('hashtags') or [])

def render(content: dict, out_dir: str, history: list[str] | None=None) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    history = history or []
    result = {'type': content.get('type'), 'ok': False, 'errors': [], 'files': [], 'alt_texts': [], 'caption': full_caption(content), 'slides': []}
    errs = qc_content(content, history)
    if errs:
        result['errors'] = errs
        return result
    t = content['type']
    roles = ['hook', 'message', 'action'] if t == 'morning' else ['quote']
    theme = content.get('theme', 'dark')
    if theme not in THEMES:
        result['errors'] = [f'unknown theme {theme!r}']
        return result
    for i, (s, role) in enumerate(zip(content['slides'], roles)):
        img, info = render_slide(s['text'], role, s.get('style'), theme, i, len(roles))
        e = qc_image(img, info)
        result['errors'] += [f'slide {i + 1}: {x}' for x in e]
        path = os.path.join(out_dir, f'{t}_{i + 1}.jpg')
        img.save(path, 'JPEG', quality=95, subsampling=0, optimize=True)
        if os.path.getsize(path) > 8 * 1024 * 1024:
            result['errors'].append(f'slide {i + 1}: file larger than 8 MB')
        result['files'].append(path)
        result['alt_texts'].append(s['text'].replace('*', ''))
        result['slides'].append({k: v for k, v in info.items() if k in ('role', 'style', 'font_size', 'lines', 'theme')})
    result['ok'] = not result['errors']
    with open(os.path.join(out_dir, 'manifest.json'), 'w') as f:
        json.dump(result, f, indent=2)
    return result
```

Cell C - render your content with quality control:
```python
import json, shutil
CONTENT = {...}            # your JSON from step 2
CAPTIONS = [...]           # all captions from step 1
shutil.rmtree("/tmp/xbe_out", ignore_errors=True)
res = render(CONTENT, "/tmp/xbe_out", history_from_captions(CAPTIONS))
print(json.dumps({k: res[k] for k in ("ok", "errors", "files", "slides")}, indent=1))
```
CONTENT format: {"type":"evening","slides":[{"text":"..."}...],"caption":"...","hashtags":[...]}
(optional per slide "style":"sans"|"serif"; optional "theme":"light" at most once a week -
black is the primary identity.)

If res["ok"] is false: fix exactly what the errors say and render again (max 3 attempts).
Still failing -> STOP, publish nothing, send a PushNotification "xBetterEverydayx evening:
quality control failed - nothing posted" with the errors.

Then in the workbench upload each file in order: `res_u, err = upload_local_file(path)` and
keep `res_u["s3key"]`. Any upload error -> retry once, then STOP + PushNotification.

## 4. Publish (exactly once)
COMPOSIO_MULTI_EXECUTE_TOOL -> INSTAGRAM_POST_IG_USER_MEDIA, account
"instagram_stylet-manful", arguments {ig_user_id:"30053245364263763", caption:<caption>,
alt_text:<the quote without asterisks>, image_file:{name:"evening_1.jpg",
mimetype:"image/jpeg", s3key:<s3key>}}.
Then INSTAGRAM_POST_IG_USER_MEDIA_PUBLISH {ig_user_id:"30053245364263763", creation_id:<id>}.
Caption = full_caption(CONTENT) (caption + blank line + hashtags), real newlines.
Publishing is pre-authorised by the account owner for this scheduled run.
If publish returns an error: re-run step 1's media list; if a post from the last 10 minutes
exists, it WAS published - stop. Otherwise retry publish once. Never create a second post.

## 5. Verify + finish
INSTAGRAM_GET_IG_MEDIA on the published id (fields "id,media_type,permalink,children").
It must be media_type IMAGE; otherwise PushNotification.
On any failure anywhere: send a PushNotification describing it. On success: no notification.
Do not send emails.
