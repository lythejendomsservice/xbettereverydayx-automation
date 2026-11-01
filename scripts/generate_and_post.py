"""
xBetterEverydayx â Automated Instagram Posting
Brand-accurate motivational image generator with proper visual hierarchy,
large X watermark, dark cinematic background and red accent support.
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


# ââ Config ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
WIDTH, HEIGHT = 1080, 1080
COMPOSIO_API_KEY = os.environ["COMPOSIO_API_KEY"]
IG_USER_ID = "30053245364263763"
ACCOUNT_ID = "ca_2o8RlJANXuJd"   # xBetterEverydayx Instagram connected account
SESSION_TYPE = sys.argv[1] if len(sys.argv) > 1 else "morning"   # morning | evening
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
USED_FILE = os.path.join(DATA_DIR, f"used_quotes_{SESSION_TYPE}.txt")

# Brand colors
BLACK       = (0,   0,   0,   255)
DARK_GREY   = (17,  17,  17,  255)
WHITE       = (255, 255, 255, 255)
SOFT_WHITE  = (242, 242, 242, 255)
RED_ACCENT  = (225, 6,   0,   255)   # #E10600
BRAND_GREY  = (90,  90,  90,  255)   # subtle brand name

# ââ Quality check âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
def quality_check(img: Image.Image, text_lines: list[str]) -> bool:
    if img.size != (WIDTH, HEIGHT):
        print(f"QC FAIL: wrong size {img.size}"); return False
    arr = np.array(img.convert("L"))
    if arr.mean() < 3:
        print("QC FAIL: image is all black"); return False
    if arr.mean() > 250:
        print("QC FAIL: image is all white"); return False
    if not any(t.strip() for t in text_lines):
        print("QC FAIL: no text"); return False
    print("QC PASS â"); return True

# ââ Used quotes âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
def load_used(path: str) -> set[str]:
    if not os.path.exists(path):
        return set()
    with open(path) as f:
        return {line.strip().lower() for line in f if line.strip()}

def save_used(path: str, quote: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(quote.strip() + "\n")

# ââ Font loader âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
def load_font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        "/usr/share/fonts/truetype/lato/Lato-Heavy.ttf",
        "/usr/share/fonts/truetype/lato/Lato-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()

# ââ X watermark â LARGE, brand-correct ââââââââââââââââââââââââââââââââââââââââ
def make_x_watermark() -> Image.Image:
    """Large X watermark at ~12% opacity â brand-correct size (80%+ of frame)."""
    logo_data = base64.b64decode(_load_logo_b64())
    logo = Image.open(io.BytesIO(logo_data)).convert("RGBA")

    # Scale to 85% of WIDTH
    target_w = int(WIDTH * 0.85)
    target_h = int(logo.height * (target_w / logo.width))
    if target_h > int(HEIGHT * 0.90):
        target_h = int(HEIGHT * 0.90)
        target_w = int(logo.width * (target_h / logo.height))

    logo_resized = logo.resize((target_w, target_h), Image.LANCZOS)
    arr = np.array(logo_resized)

    # Use luminance of the logo to drive alpha; cap at ~12% opacity (30/255)
    luminance = arr[:, :, 0].astype(float) / 255.0
    arr[:, :, 3] = (luminance * 30).astype(np.uint8)
    logo_rgba = Image.fromarray(arr)

    # Paste centered
    wm = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    x_off = (WIDTH  - target_w) // 2
    y_off = (HEIGHT - target_h) // 2
    wm.paste(logo_rgba, (x_off, y_off))
    return wm

# ââ Dark cinematic background ââââââââââââââââââââââââââââââââââââââââââââââââââ
def make_background() -> Image.Image:
    """Deep black background with subtle dark-to-charcoal gradient."""
    bg = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    draw = ImageDraw.Draw(bg)
    # Subtle vignette: slightly lighter in centre, darker at edges
    cx, cy = WIDTH // 2, HEIGHT // 2
    for r in range(max(WIDTH, HEIGHT), 0, -20):
        shade = max(0, min(22, int(22 * (1 - r / max(WIDTH, HEIGHT)))))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(shade, shade, shade))
    return bg

# ââ Core brand renderer ââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
def render_brand_post(
    lines: list[tuple[str, int]],   # (text, font_size)
    accent_lines: set[str] = None,  # lines to draw in RED accent
) -> Image.Image:
    """
    Renders a brand-accurate post.
    lines: list of (text, font_size). Empty text '' = spacer.
    accent_lines: set of line texts that should use RED (#E10600).
    """
    if accent_lines is None:
        accent_lines = set()

    # Build canvas
    bg = make_background().convert("RGBA")
    wm = make_x_watermark()
    img = Image.alpha_composite(bg, wm)

    draw = ImageDraw.Draw(img)

    # Pre-load fonts and measure each line
    entries = []
    for text, size in lines:
        font = load_font(size)
        if text.strip():
            bb = draw.textbbox((0, 0), text, font=font)
            h = bb[3] - bb[1]
            w = bb[2] - bb[0]
        else:
            h = size // 2   # spacer height = half the font size
            w = 0
        entries.append((text, font, w, h))

    # Total block height with 10px gap between lines
    GAP = 14
    total_h = sum(h for _, _, _, h in entries) + GAP * (len(entries) - 1)

    # Reserve 80px at bottom for brand name â push quote block slightly above centre
    y = (HEIGHT - 80 - total_h) // 2

    for text, font, tw, lh in entries:
        if text.strip():
            x = (WIDTH - tw) // 2
            color = RED_ACCENT if text in accent_lines else WHITE
            draw.text((x, y), text, fill=color, font=font)
        y += lh + GAP

    # Brand name â subtle, bottom-centre
    brand_font = load_font(24)
    brand_text = "xBetterEverydayx"
    bb = draw.textbbox((0, 0), brand_text, font=brand_font)
    bw = bb[2] - bb[0]
    draw.text(((WIDTH - bw) // 2, HEIGHT - 68), brand_text, fill=BRAND_GREY, font=brand_font)

    return img.convert("RGB")

# ââ Quote content library ââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# Each entry: (lines, caption, quote_text_for_dedup, accent_lines)
# lines: list of (text, font_size)
#   Large impact phrases  â 88â100 pt
#   Medium phrases        â 54â64 pt
#   Small connector words â 38â44 pt
#   Empty spacer          â ("", 40)

def _morning_quotes() -> list[tuple]:
    return [
        # Mon / Thu â "Do the work others won't"
        (
            [
                ("DO THE WORK", 88),
                ("OTHERS WON'T.", 88),
                ("", 36),
                ("SHOW UP", 64),
                ("WHEN IT'S HARD.", 64),
                ("", 36),
                ("THAT'S HOW YOU WIN.", 54),
            ],
            "Nobody claps for the 5 AM alarm, the lonely reps, or the days nobody sees. But those are exactly the days that build you.\n\nSave this. Read it again tomorrow.",
            "DO THE WORK OTHERS WON'T SHOW UP WHEN IT'S HARD THAT'S HOW YOU WIN",
            {"DO THE WORK"},
        ),
        # Tue / Fri â "Hard truth: discipline vs. time"
        (
            [
                ("THE TRUTH IS:", 48),
                ("", 20),
                ("YOU DON'T NEED", 76),
                ("MORE TIME.", 100),
                ("", 20),
                ("YOU NEED MORE", 76),
                ("DISCIPLINE.", 100),
            ],
            "Time isn't the problem. What you do with it is.\n\nSave this. Read it again tomorrow.",
            "THE TRUTH IS YOU DON'T NEED MORE TIME YOU NEED MORE DISCIPLINE",
            {"DISCIPLINE."},
        ),
        # Wed / Sat / Sun â "You didn't come this far"
        (
            [
                ("YOU DIDN'T", 88),
                ("COME THIS FAR", 72),
                ("", 28),
                ("TO ONLY", 54),
                ("", 28),
                ("COME THIS FAR.", 88),
            ],
            "Every morning you wake up is another shot. Don't waste it on small thinking and comfort zones.\n\nSave this. Read it again tomorrow.",
            "YOU DIDN'T COME THIS FAR TO ONLY COME THIS FAR",
            {"COME THIS FAR."},
        ),
        # Extra â contrast formula
        (
            [
                ("TEMPORARY", 72),
                ("COMFORT", 100),
                ("", 24),
                ("OR", 44),
                ("", 24),
                ("A BETTER FUTURE.", 72),
                ("", 20),
                ("YOU CAN'T KEEP", 50),
                ("CHOOSING BOTH.", 50),
            ],
            "Every comfortable choice is a vote for the person you are today. Every hard choice is a vote for the person you want to become.\n\nSave this. Read it again tomorrow.",
            "TEMPORARY COMFORT OR A BETTER FUTURE YOU CAN'T KEEP CHOOSING BOTH",
            {"A BETTER FUTURE."},
        ),
        # Extra â identity shift
        (
            [
                ("STOP WAITING", 80),
                ("FOR MOTIVATION.", 80),
                ("", 32),
                ("START BUILDING", 64),
                ("DISCIPLINE.", 100),
            ],
            "Motivation leaves. Discipline stays. Build the second one and you'll never need the first.\n\nSave this. Read it again tomorrow.",
            "STOP WAITING FOR MOTIVATION START BUILDING DISCIPLINE",
            {"DISCIPLINE."},
        ),
        # Extra â direct confrontation
        (
            [
                ("YOU KEEP SAYING", 58),
                ("YOU WANT A", 58),
                ("BETTER LIFE.", 88),
                ("", 28),
                ("BUT YOUR HABITS", 54),
                ("KEEP VOTING FOR", 54),
                ("THE OLD ONE.", 54),
            ],
            "Your habits are making decisions about your future right now. Are they voting for who you want to become?\n\nSave this. Read it again tomorrow.",
            "YOU KEEP SAYING YOU WANT A BETTER LIFE BUT YOUR HABITS KEEP VOTING FOR THE OLD ONE",
            {"BETTER LIFE."},
        ),
        # Extra â future regret
        (
            [
                ("ONE DAY", 72),
                ("", 20),
                ("YOU WILL WISH", 64),
                ("YOU STARTED", 88),
                ("TODAY.", 100),
            ],
            "The best time was a year ago. The second best time is right now. Stop waiting.\n\nSave this. Read it again tomorrow.",
            "ONE DAY YOU WILL WISH YOU STARTED TODAY",
            {"TODAY."},
        ),
    ]

def _evening_quotes() -> list[tuple]:
    return [
        # Mon / Thu â reflection
        (
            [
                ("TODAY", 72),
                ("WAS", 44),
                ("ENOUGH.", 100),
                ("", 32),
                ("TOMORROW", 72),
                ("DO", 44),
                ("MORE.", 100),
            ],
            "You don't have to crush every day. Some days you just survive â and that still counts.\n\nSave this. Read it again tomorrow.",
            "TODAY WAS ENOUGH TOMORROW DO MORE",
            {"ENOUGH.", "MORE."},
        ),
        # Tue / Fri â identity
        (
            [
                ("WHO YOU WERE", 64),
                ("YESTERDAY", 80),
                ("", 28),
                ("IS NOT", 54),
                ("", 28),
                ("WHO YOU'LL BE", 64),
                ("TOMORROW.", 88),
            ],
            "Growth is uncomfortable. That discomfort you felt today? That's the sound of you becoming better.\n\nSave this. Read it again tomorrow.",
            "WHO YOU WERE YESTERDAY IS NOT WHO YOU'LL BE TOMORROW",
            {"TOMORROW."},
        ),
        # Wed / Sat / Sun â rest
        (
            [
                ("YOU EARNED", 80),
                ("THE REST.", 100),
                ("", 32),
                ("NOW RECOVER.", 64),
                ("", 20),
                ("TOMORROW,", 54),
                ("WE GO AGAIN.", 54),
            ],
            "Rest isn't weakness. It's strategy. The best athletes in the world know when to stop â so they can go harder tomorrow.\n\nSave this. Read it again tomorrow.",
            "YOU EARNED THE REST NOW RECOVER TOMORROW WE GO AGAIN",
            {"THE REST."},
        ),
        # Extra â pain/growth
        (
            [
                ("THE MOMENTS", 64),
                ("YOU WANT TO QUIT", 72),
                ("", 24),
                ("ARE OFTEN THE", 50),
                ("MOMENTS THAT", 50),
                ("CHANGE YOU.", 88),
            ],
            "The hardest days are the ones that build you the most. Stay in it.\n\nSave this. Read it again tomorrow.",
            "THE MOMENTS YOU WANT TO QUIT ARE OFTEN THE MOMENTS THAT CHANGE YOU",
            {"CHANGE YOU."},
        ),
        # Extra â self-respect
        (
            [
                ("KEEP EVERY", 72),
                ("PROMISE", 100),
                ("YOU MAKE", 72),
                ("", 28),
                ("TO YOURSELF.", 80),
            ],
            "Self-discipline is just self-respect in action. Every promise you keep to yourself builds the person you want to become.\n\nSave this. Read it again tomorrow.",
            "KEEP EVERY PROMISE YOU MAKE TO YOURSELF",
            {"PROMISE"},
        ),
        # Extra â loneliness of building
        (
            [
                ("NOBODY SEES", 64),
                ("THE WORK.", 88),
                ("", 28),
                ("EVERYONE WILL", 60),
                ("SEE THE RESULT.", 60),
            ],
            "Build in silence. Let the results speak. The grind is lonely â but what it creates isn't.\n\nSave this. Read it again tomorrow.",
            "NOBODY SEES THE WORK EVERYONE WILL SEE THE RESULT",
            {"THE WORK."},
        ),
        # Extra â growth
        (
            [
                ("YOU DON'T HAVE TO", 54),
                ("CHANGE YOUR", 72),
                ("ENTIRE LIFE", 72),
                ("TONIGHT.", 100),
                ("", 28),
                ("JUST DON'T QUIT.", 60),
            ],
            "Progress is built one night at a time. One more rep. One more chapter. One more choice. That's all.\n\nSave this. Read it again tomorrow.",
            "YOU DON'T HAVE TO CHANGE YOUR ENTIRE LIFE TONIGHT JUST DON'T QUIT",
            {"ENTIRE LIFE"},
        ),
    ]

def pick_quote(pool: list[tuple], used: set[str]) -> tuple:
    """Pick the first unused quote from the pool, cycling if all used."""
    for entry in pool:
        _, _, key, _ = entry
        if key.lower() not in used:
            return entry
    # All used â reset by returning first
    return pool[0]

# ââ Composio REST helpers âââââââââââââââââââââââââââââââââââââââââââââââââââââ
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

# ── Image upload – GitHub repo as CDN (GITHUB_TOKEN available in Actions) ────────
REPO = "lythejendomsservice/xbettereverydayx-automation"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

def upload_image(path: str) -> str:
    """Upload image; try GitHub repo first (always works in Actions), then fallbacks."""
    hosts = [
        ("github",       _upload_github),
        ("catbox.moe",   _upload_catbox),
        ("litterbox",    _upload_litterbox),
        ("file.io",      _upload_fileio),
        ("0x0.st",       _upload_0x0),
    ]
    for name, fn in hosts:
        try:
            url = fn(path)
            if url and url.startswith("http"):
                print(f"Upload OK via {name}: {url}")
                return url
        except Exception as exc:
            print(f"Upload via {name} failed: {exc}")
    raise RuntimeError("All image upload hosts failed – cannot post.")

def _upload_github(path: str) -> str:
    """Upload image to repo tmp_img/ and return raw.githubusercontent.com URL."""
    import base64
    import datetime

    if not GITHUB_TOKEN:
        raise RuntimeError("GITHUB_TOKEN not set")

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    fname = f"post_{SESSION_TYPE}_{ts}.png"
    repo_path = f"tmp_img/{fname}"

    with open(path, "rb") as f:
        content_b64 = base64.b64encode(f.read()).decode()

    r = requests.put(
        f"https://api.github.com/repos/{REPO}/contents/{repo_path}",
        headers=headers,
        json={"message": f"tmp: upload {fname}", "content": content_b64},
        timeout=60,
    )
    r.raise_for_status()
    # raw.githubusercontent.com is publicly accessible for public repos
    return f"https://raw.githubusercontent.com/{REPO}/main/{repo_path}"

def _upload_catbox(path: str) -> str:
    with open(path, "rb") as f:
        r = requests.post(
            "https://catbox.moe/user/api.php",
            data={"reqtype": "fileupload"},
            files={"fileToUpload": ("quote.png", f, "image/png")},
            timeout=60,
        )
    r.raise_for_status()
    url = r.text.strip()
    if not url.startswith("http"):
        raise ValueError(f"Unexpected catbox response: {url!r}")
    return url

def _upload_litterbox(path: str) -> str:
    with open(path, "rb") as f:
        r = requests.post(
            "https://litterbox.catbox.moe/resources/internals/api.php",
            data={"reqtype": "fileupload", "time": "72h"},
            files={"fileToUpload": ("quote.png", f, "image/png")},
            timeout=60,
        )
    r.raise_for_status()
    url = r.text.strip()
    if not url.startswith("http"):
        raise ValueError(f"Unexpected litterbox response: {url!r}")
    return url

def _upload_fileio(path: str) -> str:
    with open(path, "rb") as f:
        r = requests.post(
            "https://file.io",
            files={"file": ("quote.png", f, "image/png")},
            data={"expires": "14d", "autoDelete": "false"},
            timeout=60,
        )
    r.raise_for_status()
    data = r.json()
    if data.get("success") and data.get("link"):
        return data["link"]
    raise ValueError(f"Unexpected file.io response: {data}")

def _upload_0x0(path: str) -> str:
    with open(path, "rb") as f:
        r = requests.post(
            "https://0x0.st",
            files={"file": ("quote.png", f, "image/png")},
            timeout=60,
        )
    r.raise_for_status()
    url = r.text.strip()
    if not url.startswith("http"):
        raise ValueError(f"Unexpected 0x0.st response: {url!r}")
    return url
# ââ Hashtags ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
HASHTAGS = (
    "#motivation #mindset #discipline #selfimprovement #grindculture "
    "#mentalstrength #levelup #xBetterEverydayx #bettereveryday #growth "
    "#hardwork #winner #focusmode #noexcuses #dailymotivation"
)

# ââ Main ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
def main():
    weekday = datetime.datetime.now().weekday()  # 0=Mon
    used = load_used(USED_FILE)

    if SESSION_TYPE == "morning":
        pool = _morning_quotes()
    else:
        pool = _evening_quotes()

    lines, caption_body, quote_text, accent_lines = pick_quote(pool, used)

    if quote_text.lower() in used:
        print(f"â ï¸  Quote already used, skipping: {quote_text[:60]}")
        sys.exit(0)

    # Render image
    print("Rendering imageâ¦")
    img = render_brand_post(lines, accent_lines)

    # Quality check
    all_texts = [t for t, _ in lines]
    if not quality_check(img, all_texts):
        print("â Quality check failed â aborting post")
        sys.exit(1)

    # Save image
    img_path = f"/tmp/xbettereverydayx_{SESSION_TYPE}.png"
    img.save(img_path)
    print(f"Image saved: {img_path}")

    # Upload
    print("Uploading imageâ¦")
    img_url = upload_image(img_path)
    print(f"Image URL: {img_url}")

    # Create Instagram container
    caption = f"{caption_body}\n\n{HASHTAGS}"
    print("Creating Instagram containerâ¦")
    res = composio_execute("INSTAGRAM_POST_IG_USER_MEDIA", {
        "ig_user_id": IG_USER_ID,
        "image_url": img_url,
        "caption": caption,
    })
    container_id = res["data"]["id"]
    print(f"Container: {container_id}")

    # Publish
    print("Publishingâ¦")
    composio_execute("INSTAGRAM_POST_IG_USER_MEDIA_PUBLISH", {
        "ig_user_id": IG_USER_ID,
        "creation_id": container_id,
    })
    print("â Posted successfully!")

    # Record used quote
    save_used(USED_FILE, quote_text)
    print("Quote saved to used list.")

if __name__ == "__main__":
    main()
