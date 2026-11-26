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

# Five sounds that rotate day by day (Simon 26/11-2026: "lave nogle forskellige og skifte lidt imellem" and
# "lidt mere ... du er en mand, du skal disciplin-agtig vibe ... lidt mere rå"). Four are raw, one is the calm
# sound from the first sample (Simon: "ganske tilfreds"). In the raw ones a hit lands when the last word appears.
SOUND_STYLES = ["march", "heartbeat", "grit", "cinematic", "calm"]
SOUND_START = (2026, 11, 27)  # the first Reel gets "march", then the list repeats day by day
KEYS = [57, 60, 62, 64, 53, 55]  # calm: minor-key roots A, C, D, E, F, G (MIDI)
PROGRESSIONS = [
    [(0, 3), (8, 4), (3, 4), (10, 4)],   # i - VI - III - VII   (root offset, third in semitones)
    [(0, 3), (10, 4), (8, 4), (10, 4)],  # i - VII - VI - VII
    [(0, 3), (5, 3), (8, 4), (7, 3)],    # i - iv - VI - v
    [(0, 3), (8, 4), (5, 3), (7, 4)],    # i - VI - iv - V
]


def sound_for_day(day):
    """The sound for a date - never the same two days in a row."""
    start = day.__class__(*SOUND_START)
    return SOUND_STYLES[(day - start).days % len(SOUND_STYLES)]


def _hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def _lowpass(x, sr, fc, order=4):
    spec = np.fft.rfft(x, axis=0)
    f = np.fft.rfftfreq(x.shape[0], 1 / sr)
    resp = 1 / np.sqrt(1 + (f / fc) ** (2 * order))
    return np.fft.irfft(spec * (resp[:, None] if x.ndim == 2 else resp), n=x.shape[0], axis=0)


def _bandpass(x, sr, lo, hi):
    return _lowpass(x, sr, hi) - _lowpass(x, sr, lo)


def _add(buf, x, t0, sr, gain=1.0):
    i = int(round(t0 * sr))
    if i >= len(buf) or i + len(x) <= 0:
        return
    a, b = max(0, -i), min(len(x), len(buf) - i)
    buf[i + a:i + b] += gain * x[a:b]


def _saws(t, notes, cents, rng):
    """Naive sawtooth voices (aliasing is negligible at these pitches and is filtered afterwards)."""
    x = np.zeros(len(t))
    for note in notes:
        for c in (-cents, cents):
            f = _hz(note) * 2 ** (c / 1200)
            x += 2 * ((f * t + rng.random()) % 1.0) - 1
    return x


def _drum(sr, rng, f_hi, f_lo, pitch_decay, amp_decay, length, noise=0.0, band=(1500, 6000), noise_decay=0.03,
          drive=2.5):
    """A pitched hit (kick, taiko, heartbeat) with a noise attack, saturated so a phone can hear it."""
    m = int(length * sr)
    t = np.arange(m) / sr
    f = f_lo + (f_hi - f_lo) * np.exp(-t / pitch_decay)
    body = np.sin(2 * np.pi * np.cumsum(f) / sr) * np.minimum(t / 0.002, 1) * np.exp(-t / amp_decay)
    if noise:
        nz = _bandpass(rng.standard_normal(m), sr, *band) * np.exp(-t / noise_decay)
        body = body + noise * nz / (np.max(np.abs(nz)) or 1)
    return np.tanh(drive * body) / np.tanh(drive)


def _pad(n, sr, notes, cutoff, drive, attack, rng, cents=7):
    t = np.arange(n) / sr
    x = _lowpass(_saws(t, notes, cents, rng), sr, cutoff)
    x /= np.sqrt(np.mean(x ** 2)) or 1.0
    x = np.tanh(drive * 0.5 * x)
    return x * _ease_arr(t / attack) * (1 + 0.08 * np.sin(2 * np.pi * 0.2 * t))


def _braam(sr, rng, root, length=3.2):
    """The big low brass hit: saws, a filter that closes after the attack, heavy saturation."""
    m = int(length * sr)
    t = np.arange(m) / sr
    x = _saws(t, (root - 12, root, root + 7), 9, rng)
    w = np.exp(-t / 0.4)
    y = _lowpass(x, sr, 2600) * w + _lowpass(x, sr, 420) * (1 - w)
    y /= np.max(np.abs(y)) or 1.0
    y = np.tanh(3.0 * y) / np.tanh(3.0)
    return y * np.minimum(t / 0.035, 1) * np.exp(-t / 1.6)


def _riser(sr, rng, length):
    """Noise + rising tone that swells into the hit."""
    m = int(length * sr)
    t = np.arange(m) / sr
    nz = _bandpass(rng.standard_normal(m), sr, 500, 7000)
    nz /= np.max(np.abs(nz)) or 1.0
    tone = np.sin(2 * np.pi * np.cumsum(200 * 4 ** (t / length)) / sr)
    return (0.7 * nz + 0.3 * tone) * (t / length) ** 3


def _pulse(n, sr, rng, root_hz, step, t0, t1):
    """Distorted saw bass in eighths - the growl comes from the overtones, so phones play it."""
    buf = np.zeros(n)
    m = int(step * sr * 0.95)
    tt = np.arange(m) / sr
    k, tb = 0, t0
    while tb < t1:
        f = root_hz * (2 if k % 8 == 6 else 1)
        x = (2 * ((f * tt + rng.random()) % 1.0) - 1) * np.minimum(tt / 0.004, 1) * np.exp(-tt / 0.16)
        _add(buf, x, tb, sr)
        tb += step
        k += 1
    buf = _lowpass(buf, sr, 900)
    buf /= np.max(np.abs(buf)) or 1.0
    return np.tanh(3.5 * buf) / np.tanh(3.5)


def _hit_into(buf, sr, rng, accent, root, riser=1.0, braam=0.9, taiko=1.0):
    if riser:
        r = _riser(sr, rng, min(riser, max(0.3, accent - 0.1)))
        _add(buf, r, accent - len(r) / sr, sr, 0.35)
    if braam:
        _add(buf, _braam(sr, rng, root), accent, sr, braam)
    if taiko:
        _add(buf, _drum(sr, rng, 125, 58, 0.07, 0.6, 1.6, 0.3, (150, 900), 0.05, 3.0), accent, sr, taiko)


def _march(n, sr, duration, accent, rng):
    beat = 60 / rng.uniform(84, 96)
    root = int(rng.choice([40, 41, 43, 45]))  # E2-A2 power chord
    buf = 0.55 * _pad(n, sr, (root, root + 7, root + 12), 1100, 2.2, 1.2, rng)
    k, tb = 0, 0.15
    while tb < duration - 0.4:
        gain = 0.8 if tb < accent else 1.0
        if accent - 0.45 <= tb < accent:  # a short break, so the hit on the last word lands harder
            tb += beat
            k += 1
            continue
        if k % 4 in (0, 2):
            _add(buf, _drum(sr, rng, 125, 60, 0.07, 0.5, 1.4, 0.3, (150, 900), 0.05, 3.0), tb, sr, gain)
        else:
            _add(buf, _drum(sr, rng, 240, 180, 0.02, 0.09, 0.4, 0.9, (1500, 7000), 0.08, 1.6), tb, sr, 0.45 * gain)
        if rng.random() < 0.5:
            _add(buf, _drum(sr, rng, 900, 700, 0.01, 0.02, 0.12, 0.8, (3000, 9000), 0.02, 1.2), tb + beat / 2, sr,
                 0.16 * gain)
        tb += beat
        k += 1
    _hit_into(buf, sr, rng, accent, root + 12, riser=0.8)
    return buf, 0.22, 0.35


def _heartbeat(n, sr, duration, accent, rng):
    period = 60 / rng.uniform(60, 70)
    root = int(rng.choice([45, 46, 48, 50]))
    buf = 0.5 * _pad(n, sr, (root - 12, root, root + 3, root + 7), 800, 1.6, 1.5, rng)
    tb = 0.25
    while tb < duration - 0.6:
        if accent - 0.4 <= tb < accent:
            tb += period
            continue
        g = 0.6 + 0.4 * min(1.0, tb / max(accent, 0.1)) if tb < accent else 0.75
        _add(buf, _drum(sr, rng, 120, 45, 0.04, 0.16, 0.5, 0.05, (200, 1200), 0.02, 3.2), tb, sr, g)
        _add(buf, _drum(sr, rng, 100, 42, 0.04, 0.14, 0.5, 0.04, (200, 1200), 0.02, 3.0), tb + 0.22, sr, 0.65 * g)
        tb += period
    _hit_into(buf, sr, rng, accent, root, riser=1.2)
    return buf, 0.25, 0.45


def _grit(n, sr, duration, accent, rng):
    bpm = rng.uniform(88, 100)
    eighth = 30 / bpm
    root = int(rng.choice([40, 41, 43, 45]))  # E2-A2: low enough to growl, high enough for a phone
    buf = 0.25 * _pad(n, sr, (root, root + 3, root + 7), 1200, 1.4, 1.0, rng)
    t = np.arange(n) / sr
    drop = 1 - _ease_arr((t - (accent - 0.5)) / 0.08) * (1 - _ease_arr((t - accent) / 0.02))  # silence just before the hit
    buf += 0.7 * _pulse(n, sr, rng, _hz(root), eighth, 0.1, duration - 0.5) * drop
    k, tb = 0, 0.1
    while tb < duration - 0.5:
        if accent - 0.5 <= tb < accent:
            tb += 2 * eighth
            k += 1
            continue
        _add(buf, _drum(sr, rng, 160, 50, 0.03, 0.28, 0.6, 0.12, (2000, 7000), 0.02, 2.5), tb, sr, 0.9)
        if tb >= accent and k % 2 == 1:  # claps join when the last word lands
            _add(buf, _drum(sr, rng, 1000, 900, 0.01, 0.001, 0.3, 1.0, (1000, 5000), 0.08, 1.4), tb, sr, 0.5)
        tb += 2 * eighth
        k += 1
    _hit_into(buf, sr, rng, accent, root, riser=1.0, braam=0.6, taiko=0.8)
    return buf, 0.15, 0.3


def _cinematic(n, sr, duration, accent, rng):
    root = int(rng.choice([45, 47, 48, 50]))
    buf = 0.45 * _pad(n, sr, (root, root + 3, root + 7, root + 12), 1800, 1.3, 2.2, rng)
    buf += 0.35 * _pad(n, sr, (root - 12,), 500, 1.5, 1.0, rng)
    t = np.arange(n) / sr
    ost = _pulse(n, sr, rng, _hz(root - 12), 30 / 90, accent, duration - 0.5)
    buf += 0.35 * ost * _ease_arr((t - accent) / 0.3)
    _hit_into(buf, sr, rng, accent, root, riser=1.8, braam=1.0, taiko=1.0)
    return buf, 0.35, 0.6


def _calm(n, sr, duration, accent, rng):
    """The first sample's sound: soft minor chords and a few bell notes (no hit)."""
    t = np.arange(n) / sr
    root = KEYS[int(rng.integers(len(KEYS)))]
    prog = PROGRESSIONS[int(rng.integers(len(PROGRESSIONS)))]
    k = 2 if duration <= 8 else 3 if duration <= 11 else 4
    seg = duration / k
    pad = np.zeros(n)
    bells = np.zeros(n)
    for c, (off, third) in enumerate(prog[:k]):
        s, e = c * seg, (c + 1) * seg
        i0, i1 = int(max(0, s - 0.05) * sr), min(n, int((e + 1.2) * sr))
        tt = t[i0:i1]
        env = _ease_arr((tt - s) / 0.9) * (1 - _ease_arr((tt - e + 0.4) / 1.2))
        r = root + off
        for note, level in ((r - 12, 0.5), (r, 1.0), (r + third, 0.9), (r + 7, 0.9), (r + 12, 0.6)):
            for h, amp in ((1, 1.0), (2, 0.4), (3, 0.18), (4, 0.08)):
                for cents in (-5, 5):
                    fq = _hz(note) * h * 2 ** (cents / 1200)
                    pad[i0:i1] += level * amp * env * np.sin(2 * np.pi * fq * tt + rng.uniform(0, 6.28))
        for b in range(int(seg // 1.6) + 1):
            bt = s + 0.8 + b * 1.6
            if bt > duration - 1.2:
                break
            note = r + int(rng.choice([12, 12 + third, 19, 24]))
            u = np.arange(int(2.5 * sr)) / sr
            bell = (np.sin(2 * np.pi * _hz(note) * u) + 0.25 * np.sin(2 * np.pi * _hz(note) * 2.0 * u)
                    + 0.06 * np.sin(2 * np.pi * _hz(note) * 3.0 * u)) * np.exp(-u / 0.9) * np.minimum(u / 0.005, 1)
            _add(bells, bell, bt, sr)
    pad /= np.sqrt(np.mean(pad ** 2)) or 1.0
    bells /= np.sqrt(np.mean(bells ** 2)) or 1.0
    return _lowpass(pad + 0.55 * bells, sr, 3000), 0.3, 0.55


SOUND_BUILDERS = {"march": _march, "heartbeat": _heartbeat, "grit": _grit, "cinematic": _cinematic, "calm": _calm}


def make_sound(duration, seed, sr=SR, style=None, accent=None):
    """Stereo float array (n, 2) in [-1, 1]. Deterministic per seed; style = one of SOUND_STYLES.

    Made for phone speakers: drums, bass and pads are saturated, so their overtones (150 Hz - 5 kHz) carry
    them; loudness is set on that band. Everything sits in the middle; the width comes only from the reverb,
    so mono never cancels out.
    """
    rng = np.random.default_rng(seed)
    style = style if style in SOUND_BUILDERS else SOUND_STYLES[seed % len(SOUND_STYLES)]
    accent = accent if accent is not None else 0.55 * duration
    n = int(round(duration * sr))
    t = np.arange(n) / sr
    dry, wet_amount, decay = SOUND_BUILDERS[style](n, sr, duration, accent, rng)
    ir_n = int(2.4 * sr)
    ir = _lowpass(rng.standard_normal((ir_n, 2)) * np.exp(-np.arange(ir_n) / (decay * sr))[:, None], sr, 3000)
    ir /= np.sqrt(np.sum(ir ** 2, axis=0, keepdims=True))
    stereo = np.stack([dry, dry], axis=1)
    size = 1 << int(np.ceil(np.log2(n + ir_n)))
    wet = np.fft.irfft(np.fft.rfft(stereo, size, axis=0) * np.fft.rfft(ir, size, axis=0), size, axis=0)[:n]
    mix = stereo + wet_amount * wet
    mix -= _lowpass(mix, sr, 40)                      # no rumble below 40 Hz
    if style != "calm":                               # -6 dB below ~60 Hz: the sub must not eat the headroom
        f = np.fft.rfftfreq(n, 1 / sr)
        shelf = 0.5 + 0.5 * _ease_arr((f - 60) / 80)
        mix = np.fft.irfft(np.fft.rfft(mix, axis=0) * shelf[:, None], n=n, axis=0)
    phone = _bandpass(mix.mean(axis=1), sr, 150, 5000)
    target = 0.16 if style == "calm" else 0.18        # about -16 / -15 dBFS in the band a phone plays
    mix *= target / (np.sqrt(np.mean(phone ** 2)) or 1.0)
    mix = np.tanh(mix * 1.2) / 1.2
    peak = np.max(np.abs(mix)) or 1.0
    if peak > 0.89:
        mix *= 0.89 / peak
    fade_in = np.minimum(t / 0.05, 1)
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


def render_reel(text, style=None, theme_name="dark", out_dir="/tmp/xbe_reel", seed=None, sound=None):
    """The quote as reel.mp4 (1080x1920, H.264 + AAC) and cover.jpg (all words shown).
    sound: one of SOUND_STYLES (the pipeline picks today's with sound_for_day)."""
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
    sound = sound if sound in SOUND_STYLES else SOUND_STYLES[seed % len(SOUND_STYLES)]
    write_wav(wav, make_sound(total, seed, style=sound, accent=starts[-1] + WORD_FADE))
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
    out.update(ok=not errs, errors=errs, video=video, cover=cover, duration=seconds, frames=n_frames, seed=seed, sound=sound,
               style=lay["style"], font_size=lay["font_size"], lines=lay["lines"],
               size_mb=round(os.path.getsize(video) / 1e6, 2))
    return out
