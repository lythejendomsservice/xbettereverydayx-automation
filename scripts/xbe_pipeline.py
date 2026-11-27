"""xBetterEverydayx - publishing pipeline for the Composio workbench (v2.2, 26/11-2026: three slots, evening Reel).

The scheduled tasks load this file, prompts/renderer_inline.py and scripts/xbe_reel.py from this repo at a PINNED
commit, check them against a SHA-256 in the task prompt, and exec them in the workbench. The model only writes the
text; everything deterministic runs here, in code:

    prepare(slot)            -> guard + history; returns whether to stop and the last 30 posts (short form)
    publish(content, slot)   -> guard again, render + quality control, upload, Instagram, verify, Facebook
    finish(slot)             -> Reels only: continue a Reel that publish() left at "processing"/"facebook_pending"

The evening slot is a Reel (Simon 26/11-2026): the quote as a 9:16 video with sound made by the system
(scripts/xbe_reel.py). Video takes Instagram 30-120 s to process and a workbench cell may run 180 s at most, so a
Reel is a small state machine: publish() renders, uploads and creates the container, then goes as far as it can in
~150 s; finish() carries on from the saved state. Each step runs at most once: before publishing it checks whether
the Reel already went out (a call that was cut off), and Facebook gets no blind retry for a video.

Why: the old prompts made the model copy ~15 KB of renderer code and drive ~18 tool calls per post
(~1.5 USD per run at list price). Now a run needs ~4-6 calls, and the safety rules are enforced by code,
not by the model's judgement:
  * publish only inside the slot window (early 07:00, midday 13:00, evening 20:00 - each +2 h, Copenhagen);
  * never if this slot already has a post today, or anything was posted in the last 3 hours;
  * never if quality control fails;
  * exactly one Instagram publish call - after an error it checks whether the post went out before it
    retries once;
  * Facebook only after a verified Instagram post, also checked before a retry;
  * dry_run=True renders and uploads, but never writes to Instagram or Facebook (and ignores the window).

Needs (from the workbench / renderer_inline.py): run_composio_tool, upload_local_file, render,
full_caption, history_from_captions.
"""
import contextlib
import datetime as _dt
import io
import json
import os
import shutil
import time

import requests

IG_ACCOUNT = "instagram_stylet-manful"
IG_USER_ID = "30053245364263763"
FB_ACCOUNT = "facebook_stoff-riksha"
FB_PAGE_ID = "1033703049835931"  # Page "XBetterEverydayx" - never post anywhere else
# Products that a caption may point to with "... Link in bio." - on Facebook that line gets the real link.
PRODUCTS = {
    "circle audit": "https://xbettereverydayx.gumroad.com/l/wzidk",
    "discipline reset": "https://xbettereverydayx.gumroad.com/l/discipline-reset",  # live 27/11-2026 (Dispatch)
}
GUMROAD_URL = PRODUCTS["circle audit"]
STORE_URL = "https://xbettereverydayx.gumroad.com"  # the bio link should be the store, so every product is one tap away
REPO_RAW = "https://raw.githubusercontent.com/lythejendomsservice/xbettereverydayx-automation/"
ASSET_DIR = "/tmp/xbe_assets"
ASSET_FILES = ["brand/x_mark.png", "brand/wordmark.png", "fonts/Montserrat-ExtraBold.ttf",
               "fonts/Montserrat-Black.ttf", "fonts/Montserrat-SemiBold.ttf", "fonts/PlayfairDisplay.ttf"]
OUT_DIR = "/tmp/xbe_out"
# Three posts a day (Simon 26/11-2026: "3 posts om dagen ... 7-13-20"). "render" is the renderer's content type:
# "morning" = 3-slide carousel, "evening" = one quote. The evening quote is posted as a Reel (Simon 26/11-2026).
SLOTS = {
    "early": {"start": (7, 0), "media_type": "IMAGE", "images": 1, "render": "evening"},
    "midday": {"start": (13, 0), "media_type": "CAROUSEL_ALBUM", "images": 3, "render": "morning"},
    "evening": {"start": (20, 0), "media_type": "VIDEO", "images": 1, "render": "evening", "reel": True},
}
REEL_DIR = "/tmp/xbe_reel"
REEL_STATE_DIRS = ["/mnt/files/xbe_state", "/tmp/xbe_state"]  # first that works; /mnt/files survives a sandbox restart
REEL_BUDGET = 150          # s of work per workbench cell (hard limit 180 s)
REEL_AUDIO_NAME = "xBetterEverydayx - Original Sound"
_REELS = globals().get("_REELS", {})  # in-memory Reel state; kept if this file is exec'd again in the same sandbox
WINDOW = _dt.timedelta(hours=2)        # a run that starts later than this is a late/catch-up run
EARLY = _dt.timedelta(minutes=10)      # tolerance before the slot time
RECENT = _dt.timedelta(hours=3)        # nothing may have been posted this recently
JUST_NOW = _dt.timedelta(minutes=10)   # "it WAS published" window after an API error


# ---------------------------------------------------------------- time (Europe/Copenhagen)

def _cph_offset_hours(utc):
    """EU summer time: last Sunday of March 01:00 UTC to last Sunday of October 01:00 UTC."""
    def last_sunday(month):
        d = _dt.datetime(utc.year, month, 31, 1, 0, tzinfo=_dt.timezone.utc)
        while d.weekday() != 6:
            d -= _dt.timedelta(days=1)
        return d
    return 2 if last_sunday(3) <= utc < last_sunday(10) else 1


def to_cph(utc):
    utc = utc.astimezone(_dt.timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        return utc.astimezone(ZoneInfo("Europe/Copenhagen"))
    except Exception:
        return utc.astimezone(_dt.timezone(_dt.timedelta(hours=_cph_offset_hours(utc))))


def now_cph():
    return to_cph(_dt.datetime.now(_dt.timezone.utc))


def _utc_now():
    return _dt.datetime.now(_dt.timezone.utc)


def parse_ts(ts):
    """Instagram/Facebook timestamps: '2026-11-25T18:38:02+0000'."""
    return _dt.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S%z")


def slot_of(local_dt):
    """Which slot a post (Copenhagen time) belongs to: before 10:00 early, 10-17 midday, from 17:00 evening."""
    if local_dt.hour < 10:
        return "early"
    if local_dt.hour < 17:
        return "midday"
    return "evening"


# ---------------------------------------------------------------- Composio helpers

def _quiet(fn, *args, **kwargs):
    """The workbench helpers print a lot; keep it out of the model's context."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        return fn(*args, **kwargs)


def _call(slug, arguments, account):
    result, error = _quiet(run_composio_tool, slug, arguments, account=account)  # noqa: F821 (workbench)
    if error:
        raise RuntimeError(f"{slug}: {error}")
    if not isinstance(result, dict):
        raise RuntimeError(f"{slug}: unexpected response {str(result)[:200]}")
    if result.get("successful") is False or result.get("error"):
        raise RuntimeError(f"{slug}: {result.get('error') or result}")
    return result.get("data") or {}


def _items(data):
    """List payloads come as {'data': [...], 'paging': ...} - sometimes one level deeper."""
    while isinstance(data, dict) and "data" in data:
        data = data["data"]
    return data if isinstance(data, list) else []


def fetch_media(limit=100):
    data = _call("INSTAGRAM_GET_IG_USER_MEDIA", {
        "ig_user_id": "me", "limit": limit,
        "fields": "id,caption,timestamp,media_type,like_count,comments_count,permalink",
    }, IG_ACCOUNT)
    return _items(data)


# ---------------------------------------------------------------- guard

def check_guard(slot, media, now=None, enforce_window=True):
    """Return the reasons NOT to publish (empty list = go)."""
    now = now or now_cph()
    hour, minute = SLOTS[slot]["start"]
    start = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    reasons = []
    if enforce_window:
        if now < start - EARLY:
            reasons.append(f"too early ({now:%H:%M}) - the {slot} slot is {hour:02d}:{minute:02d}")
        elif now > start + WINDOW:
            reasons.append(f"started too late ({now:%H:%M}) - the {slot} slot is {hour:02d}:{minute:02d}")
    for m in media:
        t = to_cph(parse_ts(m["timestamp"]))
        if _dt.timedelta(0) <= now - t < RECENT:
            reasons.append(f"a post went out {int((now - t).total_seconds() // 60)} min ago ({m.get('permalink')})")
            break
    for m in media:
        t = to_cph(parse_ts(m["timestamp"]))
        if t.date() == now.date() and slot_of(t) == slot:
            reasons.append(f"the {slot} slot is already posted today ({t:%H:%M}, {m.get('permalink')})")
            break
    return reasons


def _summary_line(m):
    t = to_cph(parse_ts(m["timestamp"]))
    first = ((m.get("caption") or "").strip().split("\n") or [""])[0][:120]
    return (f"{t:%d/%m %H:%M} {slot_of(t)[:3]} likes={m.get('like_count', 0)} "
            f"comments={m.get('comments_count', 0)} | {first}")


def prepare(slot, dry_run=False):
    """Step 1: may this run publish, and what has been posted lately?"""
    assert slot in SLOTS, f"unknown slot {slot!r}"
    now = now_cph()
    media = fetch_media()
    reasons = check_guard(slot, media, now, enforce_window=not dry_run)
    return {
        "slot": slot,
        "dry_run": dry_run,
        "stop": bool(reasons) and not dry_run,
        "reasons": reasons,
        "now": f"{now:%Y-%m-%d %H:%M}",
        "weekday": now.isoweekday(),  # 1=Mon ... 7=Sun
        "recent_posts": [_summary_line(m) for m in media[:30]],  # newest first
    }


# ---------------------------------------------------------------- render + upload

def ensure_assets(commit):
    os.makedirs(ASSET_DIR, exist_ok=True)
    for f in ASSET_FILES:
        path = os.path.join(ASSET_DIR, os.path.basename(f))
        if os.path.exists(path) and os.path.getsize(path) >= 1000:
            continue
        last = None
        for _ in range(2):
            try:
                data = requests.get(REPO_RAW + commit + "/assets/" + f, timeout=60).content
                if len(data) < 1000:
                    raise RuntimeError(f"only {len(data)} bytes")
                with open(path, "wb") as fh:
                    fh.write(data)
                break
            except Exception as ex:  # noqa: BLE001
                last = ex
        else:
            raise RuntimeError(f"brand asset {f} could not be downloaded: {last}")


def _direct_url(s3_url):
    """Facebook needs a direct image link; the s3_url redirects to it (sometimes only on a retry)."""
    for _ in range(3):
        try:
            r = requests.get(s3_url, allow_redirects=True, timeout=60, stream=True)  # headers only, not the file
            url = r.url
            r.close()
            if "r2.cloudflarestorage" in url:
                return url
        except Exception:  # noqa: BLE001
            pass
        time.sleep(2)
    return None


def upload(path):
    last = None
    for _ in range(3):
        res, err = _quiet(upload_local_file, path)  # noqa: F821 (workbench)
        if err or not res:
            last = err
            continue
        direct = _direct_url(res["s3_url"])
        if direct:
            return {"name": os.path.basename(path), "s3key": res["s3key"], "s3_url": res["s3_url"], "url": direct}
        last = "no direct link"
    raise RuntimeError(f"upload of {os.path.basename(path)} failed: {last}")


# ---------------------------------------------------------------- Instagram

def _wait_finished(creation_id):
    for _ in range(20):
        data = _call("INSTAGRAM_GET_POST_STATUS", {"creation_id": creation_id}, IG_ACCOUNT)
        status = str(data.get("status_code") or data.get("status") or "").upper()
        if "FINISHED" in status:
            return
        if "ERROR" in status or "EXPIRED" in status:
            raise RuntimeError(f"container {creation_id}: {status}")
        time.sleep(5)
    raise RuntimeError(f"container {creation_id} not ready after 100 s")


def _just_published():
    now = _dt.datetime.now(_dt.timezone.utc)
    for m in fetch_media(limit=5):
        if now - parse_ts(m["timestamp"]) < JUST_NOW:
            return m["id"]
    return None


def _publish_instagram(slot, caption, up, alt_text):
    if SLOTS[slot]["media_type"] == "CAROUSEL_ALBUM":
        created = _call("INSTAGRAM_CREATE_CAROUSEL_CONTAINER", {
            "ig_user_id": IG_USER_ID, "caption": caption,
            "child_image_files": [{"name": u["name"], "mimetype": "image/jpeg", "s3key": u["s3key"]} for u in up],
        }, IG_ACCOUNT)
    else:
        created = _call("INSTAGRAM_POST_IG_USER_MEDIA", {
            "ig_user_id": IG_USER_ID, "caption": caption, "alt_text": alt_text,
            "image_file": {"name": up[0]["name"], "mimetype": "image/jpeg", "s3key": up[0]["s3key"]},
        }, IG_ACCOUNT)
    creation_id = created["id"]
    _wait_finished(creation_id)
    args = {"ig_user_id": IG_USER_ID, "creation_id": creation_id}
    try:
        return _call("INSTAGRAM_POST_IG_USER_MEDIA_PUBLISH", args, IG_ACCOUNT)["id"], None
    except Exception as ex:  # noqa: BLE001
        published = _just_published()
        if published:
            return published, f"publish reported an error, but the post went out: {ex}"
        time.sleep(5)
        return _call("INSTAGRAM_POST_IG_USER_MEDIA_PUBLISH", args, IG_ACCOUNT)["id"], f"published on retry after: {ex}"


# ---------------------------------------------------------------- Facebook

def fb_caption(slot, caption):
    """A '... Link in bio.' product line gets the product's Gumroad link on Facebook (links are clickable there);
    a line about an unknown product is dropped on Facebook."""
    out = []
    for ln in caption.split("\n"):
        if ln.rstrip().endswith("Link in bio."):
            url = next((u for name, u in PRODUCTS.items() if name in ln.lower()), None)
            if url:
                out.append(ln.replace("Link in bio.", f"Get it here: {url}"))
            continue
        out.append(ln)
    return "\n".join(out)


def ig_caption(caption, bio):
    """Instagram: a '... Link in bio.' product line stays only when the bio link leads to that product or to the
    store - otherwise the post would send people to the wrong place (seen 27/11-2026: the bio pointed to another
    product). Returns (caption, dropped lines)."""
    b = (bio or "").strip().rstrip("/").lower()
    out, dropped = [], []
    for ln in caption.split("\n"):
        if ln.rstrip().endswith("Link in bio."):
            url = next((u for name, u in PRODUCTS.items() if name in ln.lower()), None)
            if not url or b not in (STORE_URL.lower(), url.rstrip("/").lower()):
                dropped.append(ln.strip())
                continue
        out.append(ln)
    text = "\n".join(out)
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text.strip(), dropped


def _bio_link():
    return (_call("INSTAGRAM_GET_USER_INFO", {"ig_user_id": "me", "fields": "website"}, IG_ACCOUNT).get("website") or "")


def _instagram_caption(caption, out):
    """The caption for Instagram after the bio-link check (only looked up when a product line is there)."""
    if not any(ln.rstrip().endswith("Link in bio.") for ln in caption.split("\n")):
        return caption
    try:
        text, dropped = ig_caption(caption, _bio_link())
    except Exception as ex:  # noqa: BLE001
        out["warnings"].append(f"bio link check failed ({ex}) - caption unchanged")
        return caption
    if dropped:
        out["warnings"].append(f"bio link does not lead to the product - left out on Instagram: {dropped[0][:90]}")
    return text


def _fb_just_posted():
    now = _dt.datetime.now(_dt.timezone.utc)
    for p in _items(_call("FACEBOOK_GET_PAGE_POSTS", {"page_id": FB_PAGE_ID, "limit": 3}, FB_ACCOUNT)):
        ct = p.get("created_time")
        if ct and now - parse_ts(ct) < JUST_NOW:
            return p.get("id") or True
    return None


def _publish_facebook(slot, caption, up):
    message = fb_caption(slot, caption)

    def attempt():
        if SLOTS[slot]["media_type"] == "CAROUSEL_ALBUM":
            return _call("FACEBOOK_CREATE_MULTI_PHOTO_POST", {
                "page_id": FB_PAGE_ID, "message": message, "photo_urls": [u["url"] for u in up],
            }, FB_ACCOUNT)
        return _call("FACEBOOK_CREATE_PHOTO_POST", {
            "page_id": FB_PAGE_ID, "message": message, "published": True,
            "photo": {"name": up[0]["name"], "mimetype": "image/jpeg", "s3key": up[0]["s3key"]},
        }, FB_ACCOUNT)

    try:
        r = attempt()
        return f"ok {r.get('post_id') or r.get('id')}"
    except Exception as ex:  # noqa: BLE001
        if _fb_just_posted():
            return f"ok (posted despite an error: {ex})"
        for u in up:  # the direct links expire after ~1 h - refresh them before the one retry
            u["url"] = _direct_url(u["s3_url"]) or u["url"]
        r = attempt()
        return f"ok after one retry {r.get('post_id') or r.get('id')} (first error: {ex})"


# ---------------------------------------------------------------- Reels (the evening slot)

def _reel_key(slot):
    return f"{now_cph():%Y-%m-%d}_{slot}"


def _save_reel(st):
    _REELS[st["key"]] = st
    for d in REEL_STATE_DIRS:
        try:
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, f"reel_{st['key']}.json"), "w") as f:
                json.dump(st, f)
            return
        except OSError:
            continue


def _load_reel(slot):
    key = _reel_key(slot)
    if key in _REELS:
        return _REELS[key]
    for d in REEL_STATE_DIRS:
        try:
            with open(os.path.join(d, f"reel_{key}.json")) as f:
                st = json.load(f)
            _REELS[key] = st
            return st
        except (OSError, ValueError):
            continue
    return None


def _left(t0):
    return REEL_BUDGET - (time.monotonic() - t0)


def _reel_out(st):
    """The Reel's media id if a post went out after its container was made (a cut-off call), else None."""
    since = parse_ts(st["created"]) - _dt.timedelta(minutes=1)
    for m in fetch_media(limit=5):
        if parse_ts(m["timestamp"]) >= since:
            return m["id"]
    return None


def _reel_status(creation_id, t0):
    """FINISHED, or PROCESSING when this cell's time is used up. Raises on ERROR/EXPIRED."""
    while True:
        data = _call("INSTAGRAM_GET_POST_STATUS", {"creation_id": creation_id}, IG_ACCOUNT)
        status = str(data.get("status_code") or data.get("status") or "").upper()
        if "FINISHED" in status:
            return "FINISHED"
        if "ERROR" in status or "EXPIRED" in status:
            raise RuntimeError(f"Reel container {creation_id}: {data.get('status') or status}")
        if _left(t0) < 30:
            return "PROCESSING"
        time.sleep(5)


def _reel_publish(st):
    args = {"ig_user_id": IG_USER_ID, "creation_id": st["container"], "max_wait_seconds": 10}
    try:
        return _call("INSTAGRAM_POST_IG_USER_MEDIA_PUBLISH", args, IG_ACCOUNT)["id"], None
    except Exception as ex:  # noqa: BLE001
        time.sleep(5)
        published = _reel_out(st)
        if published:
            return published, f"publish reported an error, but the Reel went out: {ex}"
        time.sleep(5)
        return _call("INSTAGRAM_POST_IG_USER_MEDIA_PUBLISH", args, IG_ACCOUNT)["id"], f"published on retry after: {ex}"


def _publish_facebook_video(st):
    message = fb_caption(st["slot"], st["caption"])
    try:
        r = _call("FACEBOOK_CREATE_VIDEO_POST", {
            "page_id": FB_PAGE_ID, "description": message, "published": True,
            "video": {"name": st["video"]["name"], "mimetype": "video/mp4", "s3key": st["video"]["s3key"]},
        }, FB_ACCOUNT)
        return f"ok {r.get('post_id') or r.get('id')}"
    except Exception as ex:  # noqa: BLE001
        time.sleep(10)
        if _fb_just_posted():
            return f"ok (posted despite an error: {ex})"
        raise  # no blind retry for a video: a second copy on the page is worse than none


def _reel_continue(st, out, t0):
    """Instagram publish -> verify -> Facebook, each at most once, as far as this cell's time allows."""
    out["stage"] = "instagram"
    if not st.get("ig_media_id"):
        media_id, note = _reel_out(st), None
        if not media_id:
            if _reel_status(st["container"], t0) != "FINISHED":
                out.update(stage="processing", container=st["container"])
                return out
            media_id, note = _reel_publish(st)
        if note:
            out["warnings"].append(note)
        st["ig_media_id"] = media_id
        _save_reel(st)
    out["ok"] = True  # the Reel is out - nothing below may repeat or undo it
    out["ig_media_id"] = st["ig_media_id"]
    if not st.get("permalink"):
        out["stage"] = "verify"
        v = _call("INSTAGRAM_GET_IG_MEDIA", {"ig_media_id": st["ig_media_id"],
                                             "fields": "id,media_type,media_product_type,permalink"}, IG_ACCOUNT)
        st["permalink"] = v.get("permalink") or "?"
        _save_reel(st)
        if v.get("media_type") != "VIDEO" or v.get("media_product_type", "REELS") != "REELS":
            out["warnings"].append(f"verify: media_type={v.get('media_type')}, product={v.get('media_product_type')}")
    out["permalink"] = st["permalink"]
    if not st.get("facebook"):
        if _left(t0) < 45:
            out["stage"] = "facebook_pending"
            return out
        out["stage"] = "facebook"
        try:
            st["facebook"] = _publish_facebook_video(st)
        except Exception as ex:  # noqa: BLE001
            st["facebook"] = f"FAILED: {ex}"
        _save_reel(st)
    out["facebook"] = st["facebook"]
    out["stage"] = "done"
    return out


def _publish_reel(content, slot, caption, out, dry_run, t0, ig_text=None):
    slide = content["slides"][0]
    out["stage"] = "video"
    shutil.rmtree(REEL_DIR, ignore_errors=True)
    rr = render_reel(slide["text"], slide.get("style"), content.get("theme", "dark"), REEL_DIR,  # noqa: F821
                     sound=sound_for_day(now_cph().date()))  # noqa: F821 (xbe_reel.py) - a new sound every day
    if not rr["ok"]:
        out["errors"] = rr["errors"]
        return out
    out["video_seconds"], out["sound"] = rr["duration"], rr.get("sound")

    out["stage"] = "upload"
    vid, cov = upload(rr["video"]), upload(rr["cover"])
    out["video"], out["cover"] = vid["url"], cov["url"]  # direct links (valid ~1 h) - for checking the Reel
    if dry_run:
        out.update(ok=True, stage="dry_run_done", caption=caption, facebook_caption=fb_caption(slot, caption))
        return out

    out["stage"] = "instagram"
    created = _call("INSTAGRAM_POST_IG_USER_MEDIA", {
        "ig_user_id": IG_USER_ID, "media_type": "REELS", "caption": ig_text or caption, "share_to_feed": True,
        "audio_name": REEL_AUDIO_NAME, "cover_url": cov["url"],
        "video_file": {"name": vid["name"], "mimetype": "video/mp4", "s3key": vid["s3key"]},
    }, IG_ACCOUNT)
    st = {"key": _reel_key(slot), "slot": slot, "container": created["id"], "caption": caption,
          "created": _utc_now().strftime("%Y-%m-%dT%H:%M:%S+0000"),
          "video": {"name": vid["name"], "s3key": vid["s3key"]},
          "ig_media_id": None, "permalink": None, "facebook": None}
    _save_reel(st)
    return _reel_continue(st, out, t0)


def finish(slot):
    """Step 3b (Reels): carry on with today's Reel for this slot - publish, verify, Facebook - from where it stopped."""
    out = {"slot": slot, "dry_run": False, "ok": False, "stage": "finish", "errors": [], "warnings": []}
    t0 = time.monotonic()
    try:
        st = _load_reel(slot)
        if not st:
            out["stage"] = "lost"
            out["errors"] = ["no Reel in progress for this slot today"]
            return out
        return _reel_continue(st, out, t0)
    except Exception as ex:  # noqa: BLE001
        out["errors"].append(f"{type(ex).__name__}: {ex}")
        return out


# ---------------------------------------------------------------- the whole run

def publish(content, slot, dry_run=False):
    """Step 3: render + QC, then (unless dry_run) Instagram once, verify, Facebook once."""
    out = {"slot": slot, "dry_run": dry_run, "ok": False, "stage": "setup", "errors": [], "warnings": []}
    t0 = time.monotonic()
    try:
        assert slot in SLOTS, f"unknown slot {slot!r}"
        content = dict(content, type=SLOTS[slot]["render"])  # the renderer knows "morning" (carousel) / "evening" (quote)
        ensure_assets(globals().get("XBE_COMMIT", "main"))

        out["stage"] = "guard"  # again, right before posting: protects against a second run
        media = fetch_media()
        reasons = check_guard(slot, media, enforce_window=not dry_run)
        if reasons and not dry_run:
            out["errors"] = reasons
            return out
        out["warnings"] += [f"(dry run - ignored) {r}" for r in reasons]

        out["stage"] = "qc"
        shutil.rmtree(OUT_DIR, ignore_errors=True)
        res = render(content, OUT_DIR, history_from_captions([m.get("caption") or "" for m in media]))  # noqa: F821
        if not res["ok"]:
            out["errors"] = res["errors"]
            return out
        want = SLOTS[slot]["images"]
        if len(res["files"]) != want:
            out["errors"] = [f"expected {want} image(s), got {len(res['files'])}"]
            return out
        caption = full_caption(content)  # noqa: F821
        out["slides"] = [s.get("lines") for s in res["slides"]]
        ig_text = _instagram_caption(caption, out)
        if ig_text != caption:
            out["caption_instagram"] = ig_text
        if SLOTS[slot].get("reel"):
            return _publish_reel(content, slot, caption, out, dry_run, t0, ig_text)

        out["stage"] = "upload"
        up = [upload(p) for p in res["files"]]
        out["images"] = [u["url"] for u in up]  # direct links (valid ~1 h) - for checking the slides
        if dry_run:
            out.update(ok=True, stage="dry_run_done", caption=caption, facebook_caption=fb_caption(slot, caption))
            return out

        out["stage"] = "instagram"
        media_id, note = _publish_instagram(slot, ig_text, up, res["alt_texts"][0])
        if note:
            out["warnings"].append(note)
        out["ig_media_id"] = media_id
        out["ok"] = True  # the post is out - nothing below may repeat or undo it

        out["stage"] = "verify"
        v = _call("INSTAGRAM_GET_IG_MEDIA", {"ig_media_id": media_id, "fields": "id,media_type,permalink,children"},
                  IG_ACCOUNT)
        out["permalink"] = v.get("permalink")
        children = len(_items(v.get("children")))
        if v.get("media_type") != SLOTS[slot]["media_type"] or (SLOTS[slot]["images"] == 3 and children != 3):
            out["warnings"].append(f"verify: media_type={v.get('media_type')}, children={children}")

        out["stage"] = "facebook"
        try:
            out["facebook"] = _publish_facebook(slot, caption, up)
        except Exception as ex:  # noqa: BLE001
            out["facebook"] = f"FAILED: {ex}"
        out["stage"] = "done"
        return out
    except Exception as ex:  # noqa: BLE001
        out["errors"].append(f"{type(ex).__name__}: {ex}")
        return out
