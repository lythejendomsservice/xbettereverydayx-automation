"""xBetterEverydayx - Reels (v1, 26/11-2026): the evening quote as a 9:16 video with original sound.

Simon 26/11-2026: the 20:00 quote becomes a Reel, with sound made by the system ("Lyd fra systemet") - no
third-party music, so no rights problems and nothing to do by hand.

Loaded in the Composio workbench next to prompts/renderer_inline.py and scripts/xbe_pipeline.py (pinned commit,
SHA-256 checked). It reuses the renderer's fonts, tokenizer, line fitting and brand marks, so a Reel looks like
the image posts:

    render_reel(text, style, theme_name, out_dir, seed) -> {"ok", "errors", "video", "cover", "duration", ...}

The words fade in one by one in reading order (*accent* words in brand red), the X watermark grows slowly, and
the text fades out at the end so the loop restarts cleanly. The sound is synthesised here with numpy: soft minor
chords, a low sub, a few bell notes and a short reverb - different every day, peaks below -1 dBFS.

ffmpeg: the system one if present (CI, local); in the workbench the imageio-ffmpeg wheel, pinned by version AND
SHA-256 (pip --require-hashes), so no unverified code runs.
"""
import hashlib
import os
import re
import shutil
import subprocess
import sys
import wave

import numpy as np
from PIL import Image, ImageDraw

REEL_W, REEL_H, REEL_FPS = 1080, 1920, 30
# Reels UI: like/comment buttons on the right, caption + username at the bottom. The grid shows the middle 3:4
# (y 240-1680) of the cover, so text and wordmark stay inside that too.
REEL_SAFE_X, REEL_SAFE_TOP, REEL_SAFE_BOTTOM = 100, 300, 560
REEL_WORDMARK_Y = 1440
REEL_RULE_GAP = 46          # red rule above the text, as on the images
WORD_GAP = 0.30             # s between two words appearing (~200 words per minute)
WORD_FADE = 0.28            # s for one word to fade in
WORD_RISE = 14              # px a word rises while it fades in
LEAD_IN = 0.25              # s before the first word
HOLD_MIN, HOLD_MAX = 3.0, 4.5
END_FADE = 0.5              # s - text fades out at the end
MIN_LEN, MAX_LEN = 6.0, 13.0
ZOOM = 0.05                 # the X grows 5 % over the clip
SR = 48000
MAX_MB = 50
FFMPEG_REQ = "imageio-ffmpeg==0.8.1 --hash=sha256:050d6850601c3b3890bd2b28306f3b842b3daea390a561101174375a1c460bda"
FFMPEG_VERSION = "0.8.1"


# ---------------------------------------------------------------- ffmpeg

def ffmpeg_exe():
    """System ffmpeg, else the pinned imageio-ffmpeg wheel (installed once per sandbox, hash-checked by pip)."""
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    for attempt in range(2):
        try:
            import imageio_ffmpeg
            if getattr(imageio_ffmpeg, "__version__", "") == FFMPEG_VERSION:
                return imageio_ffmpeg.get_ffmpeg_exe()
        except ImportError:
            pass
        if attempt:
            break
        req = "/tmp/xbe_ffmpeg_req.txt"
        with open(req, "w") as f:
            f.write(FFMPEG_REQ + "\n")
        r = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--no-deps", "--only-binary=:all:",
                            "--require-hashes", "-r", req], capture_output=True, text=True, timeout=170)
        if r.returncode:
            raise RuntimeError("ffmpeg install failed: " + (r.stderr or r.stdout)[-300:])
        sys.modules.pop("imageio_ffmpeg", None)
    raise RuntimeError("ffmpeg not available")


# ---------------------------------------------------------------- layout (the renderer's own fitting)

def reel_layout(text, style=None):
    cfg = dict(ROLE_DEFAULTS["quote"])  # noqa: F821 (renderer_inline.py)
    style = style or cfg["style"]
    if style != cfg["style"]:
        cfg.update(SANS_OVERRIDE if style == "sans" else SERIF_OVERRIDE)  # noqa: F821
    font_key = "sans" if style == "sans" else "serif"
    scratch = ImageDraw.Draw(Image.new("L", (8, 8)))
    words = _tokens(text.upper() if cfg["upper"] else text)  # noqa: F821
    box_w = REEL_W - 2 * REEL_SAFE_X
    box_h = REEL_H - REEL_SAFE_TOP - REEL_SAFE_BOTTOM
    fit = _fit(words, cfg, font_key, scratch, box_w, box_h)  # noqa: F821
    if fit is None:
        return {"style": style, "error": "text does not fit at minimum readable size - shorten it"}
    size, font, lines, lh = fit
    top = REEL_SAFE_TOP + (box_h - lh * len(lines)) // 2 - 10
    space = scratch.textlength(" ", font=font)
    placed = []
    for i, line in enumerate(lines):
        x = (REEL_W - _line_w(line, font, scratch)) / 2  # noqa: F821
        y = top + i * lh + (lh - size) // 2
        for w, acc in line:
            placed.append(_word_patch(w, acc, font, x, y))
            x += scratch.textlength(w, font=font) + space
    xs = [p["x"] + 2 for p in placed] + [p["x"] + p["mask"].shape[1] - 2 for p in placed]  # without the 2 px pad
    ys = [p["y"] + 2 for p in placed] + [p["y"] + p["mask"].shape[0] - 2 for p in placed]
    return {"style": style, "font_size": size, "lines": [" ".join(w for w, _ in ln) for ln in lines],
            "words": placed, "rule_y": top - REEL_RULE_GAP, "text_bbox": [min(xs), min(ys), max(xs), max(ys)]}


def _word_patch(word, accent, font, x, y):
    """One word as an anti-aliased mask at its final position."""
    x0, y0, x1, y1 = font.getbbox(word)
    img = Image.new("L", (x1 - x0 + 4, y1 - y0 + 4), 0)
    ImageDraw.Draw(img).text((2 - x0, 2 - y0), word, font=font, fill=255)
    return {"word": word, "accent": accent, "x": int(round(x + x0 - 2)), "y": int(round(y + y0 - 2)),
            "mask": np.asarray(img, dtype=np.float32) / 255.0}


def qc_reel_layout(lay):
    errs = []
    if "error" in lay:
        return [lay["error"]]
    x0, y0, x1, y1 = lay["text_bbox"]
    if x0 < REEL_SAFE_X - 4 or x1 > REEL_W - REEL_SAFE_X + 4 or y0 < REEL_SAFE_TOP - 60 \
            or y1 > REEL_H - REEL_SAFE_BOTTOM + 30:
        errs.append(f"text outside the Reel's safe area {lay['text_bbox']}")
    minimum = 46 if lay["style"] == "serif" else 56
    if lay["font_size"] < minimum:
        errs.append(f"font size {lay['font_size']}px too small for mobile")
    return errs


def reel_timeline(n_words):
    """Start time of each word and the clip length (s)."""
    starts = [LEAD_IN + i * WORD_GAP for i in range(n_words)]
    revealed = (starts[-1] if starts else 0) + WORD_FADE
    hold = min(HOLD_MAX, max(HOLD_MIN, 2.6 + 0.08 * n_words))
    return starts, round(min(MAX_LEN, max(MIN_LEN, revealed + hold + END_FADE)), 2)


# ---------------------------------------------------------------- frames

def _clip01(v):
    return 0.0 if v <= 0 else 1.0 if v >= 1 else v


def _ease(v):
    v = _clip01(v)
    return v * v * (3 - 2 * v)


def _blend(frame, x, y, mask, color, alpha):
    """frame (uint8 HxWx3) <- color through mask*alpha at (x, y)."""
    if alpha <= 0:
        return
    h, w = mask.shape
    fx0, fy0, fx1, fy1 = max(x, 0), max(y, 0), min(x + w, REEL_W), min(y + h, REEL_H)
    if fx1 <= fx0 or fy1 <= fy0:
        return
    m = mask[fy0 - y:fy1 - y, fx0 - x:fx1 - x, None] * alpha
    region = frame[fy0:fy1, fx0:fx1].astype(np.float32)
    region += (np.asarray(color, np.float32) - region) * m
    frame[fy0:fy1, fx0:fx1] = (region + 0.5).astype(np.uint8)


def _mark(name, width):
    src = Image.open(os.path.join(BRAND, name)).convert("L")  # noqa: F821
    h = round(src.height * width / src.width)
    return np.asarray(src.resize((width, h), Image.BILINEAR), dtype=np.float32) / 255.0


def _base(theme, theme_name):
    """Background (with the dark theme's soft centre light) + wordmark - everything that never moves."""
    if theme_name == "dark":
        yy, xx = np.mgrid[0:REEL_H, 0:REEL_W]
        d = np.sqrt(((xx - REEL_W / 2) / REEL_W) ** 2 + ((yy - REEL_H * 0.43) / REEL_H) ** 2)
        lift = np.clip(14 * (1 - d / 0.6), 0, 14)
        bg = np.dstack([lift, lift, lift]).astype(np.uint8)
    else:
        bg = np.empty((REEL_H, REEL_W, 3), np.uint8)
        bg[:] = theme["bg"]
    sig = _mark("wordmark.png", WORDMARK_WIDTH)  # noqa: F821
    _blend(bg, REEL_W // 2 - sig.shape[1] // 2, REEL_WORDMARK_Y - sig.shape[0] // 2, sig, (theme["mark"],) * 3,
           0.55 if theme_name == "dark" else 0.7)
    return bg


class _Frames:
    def __init__(self, lay, theme, theme_name, starts, total):
        self.lay, self.theme, self.starts, self.total = lay, theme, starts, total
        self.base = _base(theme, theme_name)
        self.wm_alpha = WATERMARK_OPACITY if theme_name == "dark" else 0.11  # noqa: F821
        self.wm_cache = {}
        self.wm_cy = REEL_SAFE_TOP + (REEL_H - REEL_SAFE_TOP - REEL_SAFE_BOTTOM) // 2

    def frame(self, t, final=False):
        f = self.base.copy()
        scale = 1.0 if final else 1.0 + ZOOM * t / self.total
        w = int(round(REEL_W * WATERMARK_WIDTH * scale / 2)) * 2  # noqa: F821
        if w not in self.wm_cache:
            self.wm_cache[w] = _mark("x_mark.png", w)
        m = self.wm_cache[w]
        _blend(f, REEL_W // 2 - w // 2, self.wm_cy - m.shape[0] // 2, m, (self.theme["mark"],) * 3, self.wm_alpha)
        out = 1.0 if final else _clip01((self.total - t) / END_FADE)
        a = 1.0 if final else _ease(t / 0.3)
        ry = self.lay["rule_y"]
        _blend(f, REEL_W // 2 - 34, ry, np.ones((6, 69), np.float32), RED, a * out)  # noqa: F821
        for p, start in zip(self.lay["words"], self.starts):
            a = 1.0 if final else _ease((t - start) / WORD_FADE)
            if a <= 0:
                continue
            dy = 0 if final else int(round((1 - a) * WORD_RISE))
            _blend(f, p["x"], p["y"] + dy, p["mask"], RED if p["accent"] else self.theme["text"], a * out)  # noqa: F821
        return f


# ---------------------------------------------------------------- sound (original, generated here)

KEYS = [57, 60, 62, 64, 53, 55]  # minor-key roots: A, C, D, E, F, G (MIDI)
PROGRESSIONS = [
    [(0, 3), (8, 4), (3, 4), (10, 4)],   # i - VI - III - VII   (root offset, third in semitones)
    [(0, 3), (10, 4), (8, 4), (10, 4)],  # i - VII - VI - VII
    [(0, 3), (5, 3), (8, 4), (7, 3)],    # i - iv - VI - v
    [(0, 3), (8, 4), (5, 3), (7, 4)],    # i - VI - iv - V
]


def _hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def _lowpass(x, sr, fc, order=4):
    spec = np.fft.rfft(x, axis=0)
    f = np.fft.rfftfreq(x.shape[0], 1 / sr)
    resp = 1 / np.sqrt(1 + (f / fc) ** (2 * order))
    return np.fft.irfft(spec * (resp[:, None] if x.ndim == 2 else resp), n=x.shape[0], axis=0)


def make_sound(duration, seed, sr=SR):
    """Stereo float array (n, 2) in [-1, 1]: calm minor chords and a few bell notes with a short reverb.

    Made for phone speakers (mono, nothing below ~150 Hz): the chords sit around 200-450 Hz with overtones,
    the bells around 440-880 Hz, and the stereo width comes only from the reverb, so mono never cancels out.
    Deterministic per seed - the seed changes with the quote, so every day sounds a little different.
    """
    rng = np.random.default_rng(seed)
    n = int(round(duration * sr))
    t = np.arange(n) / sr
    root = KEYS[int(rng.integers(len(KEYS)))]
    prog = PROGRESSIONS[int(rng.integers(len(PROGRESSIONS)))]
    k = 2 if duration <= 8 else 3 if duration <= 11 else 4
    seg = duration / k
    pad = np.zeros(n)
    bells = np.zeros((n, 2))
    for c, (off, third) in enumerate(prog[:k]):
        s, e = c * seg, (c + 1) * seg
        i0, i1 = int(max(0, s - 0.05) * sr), min(n, int((e + 1.2) * sr))
        tt = t[i0:i1]
        env = _ease_arr((tt - s) / 0.9) * (1 - _ease_arr((tt - e + 0.4) / 1.2))
        r = root + off
        for note, level in ((r - 12, 0.5), (r, 1.0), (r + third, 0.9), (r + 7, 0.9), (r + 12, 0.6)):
            for h, amp in ((1, 1.0), (2, 0.4), (3, 0.18), (4, 0.08)):
                for cents in (-5, 5):  # two slightly detuned voices in BOTH channels: chorus, mono-safe
                    fq = _hz(note) * h * 2 ** (cents / 1200)
                    pad[i0:i1] += level * amp * env * np.sin(2 * np.pi * fq * tt + rng.uniform(0, 6.28))
        for b in range(int(seg // 1.6) + 1):  # soft bell notes from the chord, panned a little left/right
            bt = s + 0.8 + b * 1.6
            if bt > duration - 1.2:
                break
            note = r + int(rng.choice([12, 12 + third, 19, 24]))
            j0 = int(bt * sr)
            j1 = min(n, j0 + int(2.5 * sr))
            u = t[j0:j1] - bt
            bell = (np.sin(2 * np.pi * _hz(note) * u) + 0.25 * np.sin(2 * np.pi * _hz(note) * 2.0 * u)
                    + 0.06 * np.sin(2 * np.pi * _hz(note) * 3.0 * u)) * np.exp(-u / 0.9) * np.minimum(u / 0.005, 1)
            pan = 0.4 if b % 2 else 0.6
            bells[j0:j1, 0] += bell * (1 - pan)
            bells[j0:j1, 1] += bell * pan
    pad /= np.sqrt(np.mean(pad ** 2)) or 1.0
    bells /= np.sqrt(np.mean(bells ** 2)) or 1.0
    dry = np.stack([pad, pad], axis=1) + 0.55 * bells
    dry = _lowpass(dry, sr, 3000) - _lowpass(dry, sr, 140)   # band 140 Hz - 3 kHz: what a phone can play
    ir_n = int(2.4 * sr)
    tail = np.exp(-np.arange(ir_n) / (0.55 * sr))
    ir = _lowpass(rng.standard_normal((ir_n, 2)) * tail[:, None], sr, 3000)
    ir /= np.sqrt(np.sum(ir ** 2, axis=0, keepdims=True))
    size = 1 << int(np.ceil(np.log2(n + ir_n)))
    wet = np.fft.irfft(np.fft.rfft(dry, size, axis=0) * np.fft.rfft(ir, size, axis=0), size, axis=0)[:n]
    mix = dry + 0.3 * wet
    mix -= mix.mean(axis=0)
    rms = np.sqrt(np.mean(mix.mean(axis=1) ** 2)) or 1.0
    mix *= 0.16 / rms                         # about -16 dBFS RMS (mono sum): present on a phone, still a background
    mix = np.tanh(mix * 1.5) / 1.5
    peak = np.max(np.abs(mix)) or 1.0
    if peak > 0.85:
        mix *= 0.85 / peak
    fade_in = np.minimum(t / 0.08, 1)
    fade_out = np.clip((duration - t) / (END_FADE + 0.3), 0, 1)
    return mix * (fade_in * fade_out)[:, None]


def _ease_arr(v):
    v = np.clip(v, 0, 1)
    return v * v * (3 - 2 * v)


def write_wav(path, stereo, sr=SR):
    data = (np.clip(stereo, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(data.tobytes())


# ---------------------------------------------------------------- encode + QC

def qc_reel(path, expected_seconds):
    errs = []
    size = os.path.getsize(path) if os.path.exists(path) else 0
    if size < 50_000:
        return [f"video missing or too small ({size} bytes)"], 0.0
    if size > MAX_MB * 1024 * 1024:
        errs.append(f"video larger than {MAX_MB} MB")
    info = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", path], capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", info)
    seconds = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0
    if abs(seconds - expected_seconds) > 0.3:
        errs.append(f"video is {seconds:.2f} s, expected {expected_seconds:.2f} s")
    if "Video: h264" not in info or f"{REEL_W}x{REEL_H}" not in info:
        errs.append("video stream is not H.264 1080x1920")
    if "Audio: aac" not in info:
        errs.append("audio stream missing (AAC expected)")
    return errs, round(seconds, 2)


def render_reel(text, style=None, theme_name="dark", out_dir="/tmp/xbe_reel", seed=None):
    """The quote as reel.mp4 (1080x1920, H.264 + AAC) and cover.jpg (all words shown)."""
    out = {"ok": False, "errors": []}
    theme = THEMES.get(theme_name)  # noqa: F821
    if theme is None:
        out["errors"] = [f"unknown theme {theme_name!r}"]
        return out
    lay = reel_layout(text, style)
    errs = qc_reel_layout(lay)
    if errs:
        out["errors"] = errs
        return out
    os.makedirs(out_dir, exist_ok=True)
    starts, total = reel_timeline(len(lay["words"]))
    seed = seed if seed is not None else int(hashlib.sha256(text.encode()).hexdigest()[:8], 16)
    frames = _Frames(lay, theme, theme_name, starts, total)
    cover = os.path.join(out_dir, "cover.jpg")
    Image.fromarray(frames.frame(total, final=True)).save(cover, "JPEG", quality=92, optimize=True)
    wav = os.path.join(out_dir, "sound.wav")
    write_wav(wav, make_sound(total, seed))
    video = os.path.join(out_dir, "reel.mp4")
    n_frames = int(round(total * REEL_FPS))
    cmd = [ffmpeg_exe(), "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{REEL_W}x{REEL_H}", "-r", str(REEL_FPS), "-i", "-",
           "-i", wav, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
           "-profile:v", "high", "-level", "4.1", "-g", str(REEL_FPS * 2),
           "-c:a", "aac", "-b:a", "128k", "-ar", str(SR), "-ac", "2", "-shortest", "-movflags", "+faststart", video]
    err_path = os.path.join(out_dir, "ffmpeg.log")
    with open(err_path, "wb") as err:
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=err)
        try:
            for i in range(n_frames):
                p.stdin.write(frames.frame(i / REEL_FPS).tobytes())
        finally:
            p.stdin.close()
            rc = p.wait()
    if rc:
        out["errors"] = ["ffmpeg failed: " + open(err_path, errors="replace").read()[-300:]]
        return out
    errs, seconds = qc_reel(video, n_frames / REEL_FPS)
    out.update(ok=not errs, errors=errs, video=video, cover=cover, duration=seconds, frames=n_frames, seed=seed,
               style=lay["style"], font_size=lay["font_size"], lines=lay["lines"],
               size_mb=round(os.path.getsize(video) / 1e6, 2))
    return out
