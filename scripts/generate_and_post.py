"""
xBetterEverydayx — Automated Instagram Posting
Generates a motivational quote image and posts to Instagram via Composio.
"""
import os
import sys
import datetime
import requests
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import base64
import io

def _load_logo_b64() -> str:
    """Load logo base64 from assets/logo_b64.txt."""
    logo_b64_path = os.path.join(os.path.dirname(__file__), "..", "assets", "logo_b64.txt")
    with open(logo_b64_path) as f:
        return f.read().strip()


# ── Config ────────────────────────────────────────────────────────────────────
WIDTH, HEIGHT = 1080, 1080
COMPOSIO_API_KEY = os.environ["COMPOSIO_API_KEY"]
IG_USER_ID = "30053245364263763"
ACCOUNT_ID = "ca_2o8RlJANXuJd"   # xBetterEverydayx Instagram connected account
SESSION_TYPE = sys.argv[1] if len(sys.argv) > 1 else "morning"   # morning | evening
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
USED_FILE = os.path.join(DATA_DIR, f"used_quotes_{SESSION_TYPE}.txt")

# ── Quality check ─────────────────────────────────────────────────────────────
def quality_check(img: Image.Image, quote_lines: list[str]) -> bool:
    """Basic sanity checks before posting."""
    if img.size != (WIDTH, HEIGHT):
        print(f"QC FAIL: wrong size {img.size}"); return False
    arr = np.array(img.convert("L"))
    if arr.mean() < 5:
        print("QC FAIL: image is all black"); return False
    if arr.mean() > 250:
        print("QC FAIL: image is all white"); return False
    if not any(line.strip() for line in quote_lines):
        print("QC FAIL: no quote text"); return False
    print("QC PASS \u2713"); return True

# ── Used quotes ───────────────────────────────────────────────────────────────
def load_used(path: str) -> set[str]:
    if not os.path.exists(path):
        return set()
    with open(path) as f:
        return {line.strip().lower() for line in f if line.strip()}

def save_used(path: str, quote: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(quote.strip() + "\n")

# ── Font loader ───────────────────────────────────────────────────────────────
def load_font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        "/usr/share/fonts/truetype/lato/Lato-Heavy.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()

# ── Logo watermark ────────────────────────────────────────────────────────────
def make_logo_watermark() -> Image.Image:
    logo_data = base64.b64decode(_load_logo_b64())
    logo = Image.open(io.BytesIO(logo_data)).convert("RGBA")
    arr = np.array(logo)
    luminance = arr[:, :, 0].astype(float) / 255.0
    arr[:, :, 3] = (luminance * 35).astype(np.uint8)
    logo_rgba = Image.fromarray(arr)
    target_w = 520
    target_h = int(logo.height * (target_w / logo.width))
    logo_resized = logo_rgba.resize((target_w, target_h), Image.LANCZOS)
    wm = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    wm.paste(logo_resized, ((WIDTH - target_w) // 2, (HEIGHT - target_h) // 2))
    return wm

# ── Image styles ──────────────────────────────────────────────────────────────
def render_standard(quote_lines: list[str]) -> Image.Image:
    """Style 1/3: uniform Lato Heavy text, centered."""
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 255))
    img = Image.alpha_composite(img, make_logo_watermark())
    draw = ImageDraw.Draw(img)
    font = load_font(58)
    lh = 76
    total_h = len(quote_lines) * lh
    y = (HEIGHT - total_h) // 2 - 30
    for line in quote_lines:
        if line.strip():
            bb = draw.textbbox((0, 0), line, font=font)
            tw = bb[2] - bb[0]
            draw.text(((WIDTH - tw) // 2, y), line, fill=(255, 255, 255, 255), font=font)
        y += lh
    return img.convert("RGB")

def render_variable(quote_lines: list[tuple[str, int]]) -> Image.Image:
    """Style 4: variable font sizes — list of (text, size) tuples."""
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 255))
    img = Image.alpha_composite(img, make_logo_watermark())
    draw = ImageDraw.Draw(img)
    entries = [(text, load_font(size)) for text, size in quote_lines]
    line_heights = []
    for text, font in entries:
        bb = draw.textbbox((0, 0), text, font=font)
        line_heights.append(bb[3] - bb[1] + 8)
    total_h = sum(line_heights)
    y = (HEIGHT - total_h) // 2 - 20
    for i, (text, font) in enumerate(entries):
        bb = draw.textbbox((0, 0), text, font=font)
        tw = bb[2] - bb[0]
        draw.text(((WIDTH - tw) // 2, y), text, fill=(255, 255, 255, 255), font=font)
        y += line_heights[i]
    return img.convert("RGB")

# ── Composio REST helpers ─────────────────────────────────────────────────────
COMPOSIO_BASE = "https://backend.composio.dev/api/v3"
HEADERS = {"x-api-key": COMPOSIO_API_KEY, "Content-Type": "application/json"}

def composio_execute(tool: str, params: dict) -> dict:
    payload = {
        "connectedAccountId": ACCOUNT_ID,
        "input": params,
    }
    r = requests.post(
        f"{COMPOSIO_BASE}/actions/{tool}/execute",
        json=payload,
        headers=HEADERS,
        timeout=60,
    )
    if not r.ok:
        print(f"API error {r.status_code}: {r.text[:500]}")
    r.raise_for_status()
    return r.json()

def upload_image(path: str) -> str:
    """Upload image to Composio S3 and return s3key."""
    with open(path, "rb") as f:
        r = requests.post(
            f"{COMPOSIO_BASE}/files/upload",
            headers={"x-api-key": COMPOSIO_API_KEY},
            files={"file": ("quote.png", f, "image/png")},
            timeout=60,
        )
    if not r.ok:
        print(f"Upload error {r.status_code}: {r.text[:500]}")
    r.raise_for_status()
    data = r.json()
    return data.get("s3key") or data.get("key") or data["data"]["s3key"]

# ── Quote generators ──────────────────────────────────────────────────────────
def generate_morning_quote(weekday: int) -> tuple[list, str, str, int]:
    """Returns (lines, caption, quote_text, style)
    style 1=standard, 4=variable
    Weekday: 0=Mon \u2026 6=Sun"""
    if weekday in (0, 3):   # Mon, Thu \u2014 manifesto
        lines = [
            "DO THE WORK", "OTHERS WON'T.",
            "", "SHOW UP", "WHEN IT'S HARD.",
            "", "THAT'S HOW", "YOU WIN.",
        ]
        caption = "Nobody claps for the 5 AM alarm, the lonely reps, or the days nobody sees. But those are exactly the days that build you.\n\nSave this. Read it again tomorrow."
        return lines, caption, " ".join(l for l in lines if l), 1
    elif weekday in (1, 4):  # Tue, Fri \u2014 variable
        lines = [("WINNERS", 62), ("NEVER", 100), ("QUIT.", 140),
                 ("AND", 38), ("QUITTERS", 62), ("NEVER", 100), ("WIN.", 140)]
        caption = "The gap between where you are and where you want to be is called discipline. Fill it every single day.\n\nSave this. Read it again tomorrow."
        return lines, caption, "WINNERS NEVER QUIT AND QUITTERS NEVER WIN", 4
    else:                    # Wed, Sat, Sun \u2014 raw/cinematic
        lines = ["YOU DIDN'T COME", "THIS FAR", "TO ONLY", "COME THIS FAR."]
        caption = "Every morning you wake up is another shot. Don't waste it on small thinking and comfort zones.\n\nSave this. Read it again tomorrow."
        return lines, caption, " ".join(lines), 1

def generate_evening_quote(weekday: int) -> tuple[list, str, str, int]:
    if weekday in (0, 3):   # Mon, Thu \u2014 cinematic/variable
        lines = [("TODAY", 62), ("WAS", 38), ("ENOUGH.", 140),
                 ("TOMORROW", 62), ("DO", 38), ("MORE.", 140)]
        caption = "You don't have to crush every day. Some days you just survive \u2014 and that still counts.\n\nSave this. Read it again tomorrow."
        return lines, caption, "TODAY WAS ENOUGH. TOMORROW DO MORE.", 4
    elif weekday in (1, 4):  # Tue, Fri \u2014 manifesto
        lines = [
            "WHO YOU WERE", "YESTERDAY",
            "", "IS NOT", "WHO YOU'LL BE",
            "", "TOMORROW.", "",
        ]
        caption = "Growth is uncomfortable. That discomfort you felt today? That's the sound of you becoming better.\n\nSave this. Read it again tomorrow."
        return lines, caption, " ".join(l for l in lines if l), 1
    else:                    # Wed, Sat, Sun \u2014 raw
        lines = ["You earned the rest.", "", "Now recover.", "Tomorrow, we go again."]
        caption = "Rest isn't weakness. It's strategy. The best athletes in the world know when to stop \u2014 so they can go harder tomorrow.\n\nSave this. Read it again tomorrow."
        return lines, caption, " ".join(l for l in lines if l), 1

HASHTAGS = (
    "#motivation #mindset #discipline #selfimprovement #grindculture "
    "#mentalstrength #levelup #xBetterEverydayx #bettereveryday #growth "
    "#hardwork #winner #focusmode #noexcuses #dailymotivation"
)

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    weekday = datetime.datetime.now().weekday()  # 0=Mon
    used = load_used(USED_FILE)

    if SESSION_TYPE == "morning":
        lines, caption_body, quote_text, style = generate_morning_quote(weekday)
    else:
        lines, caption_body, quote_text, style = generate_evening_quote(weekday)

    if quote_text.lower() in used:
        print(f"\u26a0\ufe0f  Quote already used, skipping: {quote_text[:60]}")
        sys.exit(0)

    # Render image
    if style == 4:
        img = render_variable(lines)
    else:
        img = render_standard(lines)

    # Quality check
    quote_lines_flat = [t for t, _ in lines] if style == 4 else lines
    if not quality_check(img, quote_lines_flat):
        print("\u274c Quality check failed \u2014 aborting post")
        sys.exit(1)

    # Save image
    img_path = f"/tmp/xbettereverydayx_{SESSION_TYPE}.png"
    img.save(img_path)

    # Upload to Composio S3
    print("Uploading image\u2026")
    s3key = upload_image(img_path)
    print(f"S3 key: {s3key}")

    # Create IG container
    caption = f"{caption_body}\n\n{HASHTAGS}"
    print("Creating Instagram container\u2026")
    res = composio_execute("INSTAGRAM_POST_IG_USER_MEDIA", {
        "ig_user_id": IG_USER_ID,
        "image_file": {"name": "quote.png", "mimetype": "image/png", "s3key": s3key},
        "caption": caption,
    })
    container_id = res["data"]["id"]
    print(f"Container: {container_id}")

    # Publish
    print("Publishing\u2026")
    composio_execute("INSTAGRAM_POST_IG_USER_MEDIA_PUBLISH", {
        "ig_user_id": IG_USER_ID,
        "creation_id": container_id,
    })
    print("\u2705 Posted successfully!")

    # Save used quote
    save_used(USED_FILE, quote_text)
    print(f"Quote saved to used list.")

if __name__ == "__main__":
    main()
