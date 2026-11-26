"""Offline tests of scripts/xbe_pipeline.py - no network, nothing is posted.

The pipeline is exec'd together with prompts/renderer_inline.py, exactly as in the Composio workbench, with
fake run_composio_tool / upload_local_file / requests. Run: python scripts/test_pipeline.py
"""
import datetime as dt
import os
import shutil
import sys
import types

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CPH_WINTER = dt.timezone(dt.timedelta(hours=1))
FAILED = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILED.append(name)


def ts(y, mo, d, h, mi, tz=CPH_WINTER):
    """Instagram-style UTC timestamp for a Copenhagen wall-clock time."""
    return dt.datetime(y, mo, d, h, mi, tzinfo=tz).astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+0000")


def load(script=None, now=None):
    """Fresh workbench-like namespace. script: dict slug -> list of responses (exceptions are raised)."""
    os.makedirs("/tmp/xbe_assets", exist_ok=True)
    for f in ["brand/x_mark.png", "brand/wordmark.png", "fonts/Montserrat-ExtraBold.ttf",
              "fonts/Montserrat-Black.ttf", "fonts/Montserrat-SemiBold.ttf", "fonts/PlayfairDisplay.ttf"]:
        shutil.copy(os.path.join(ROOT, "assets", f), os.path.join("/tmp/xbe_assets", os.path.basename(f)))
    calls = []
    script = script or {}

    def run_composio_tool(slug, arguments, account=None):
        calls.append((slug, arguments, account))
        queue = script.get(slug)
        if not queue:
            return None, f"unexpected call {slug}"
        r = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(r, Exception):
            return None, str(r)
        return {"data": r, "successful": True}, None

    uploads = []

    def upload_local_file(path):
        uploads.append(path)
        n = len(uploads)
        return {"s3key": f"key{n}", "s3_url": f"https://backend.composio.dev/api/v3/sl/x{n}"}, None

    class FakeResp:
        def __init__(self, url):
            self.url = url
            self.content = b"x" * 2000

    fake_requests = types.SimpleNamespace(
        get=lambda url, **kw: FakeResp(url.replace("backend.composio.dev/api/v3/sl", "temp.r2.cloudflarestorage.com")))
    ns = {"__name__": "xbe_test"}
    exec(open(os.path.join(ROOT, "prompts", "renderer_inline.py")).read(), ns)
    exec(open(os.path.join(ROOT, "scripts", "xbe_pipeline.py")).read(), ns)
    ns.update(run_composio_tool=run_composio_tool, upload_local_file=upload_local_file, requests=fake_requests)
    ns["time"] = types.SimpleNamespace(sleep=lambda s: None)
    if now:
        ns["now_cph"] = lambda: now
    return ns, calls, uploads


MORNING = {"type": "morning", "slides": [
    {"text": "Your excuses sound *reasonable* because you wrote them yourself."},
    {"text": "Every delay comes with a story that makes it feel smart: tired, busy, not ready. The story is good. "
             "The *result* is still nothing."},
    {"text": "Do the *first step* before the story starts today."}],
    "caption": "Your excuses sound reasonable because you wrote them yourself.\n\nThe story always makes the delay "
               "feel smart.\nThe result never changes.\n\nWhat's the story you tell yourself most often?",
    "hashtags": ["#xbettereverydayx", "#selfdiscipline", "#noexcuses", "#takeaction", "#mindsetshift"]}
EVENING = {"type": "evening", "slides": [
    {"text": "People who only call when they *need* something are telling you exactly where you stand."}],
    "caption": "People who only call when they need something are telling you exactly where you stand.\n\n"
               "Notice who reaches out when you have nothing to offer.\n\nWho checks on you just because?\n\n"
               "Not sure who's really in your corner? The Circle Audit helps you find out. Link in bio.",
    "hashtags": ["#xbettereverydayx", "#selfrespect", "#realfriends", "#boundaries", "#innercircle"]}

# ---------------------------------------------------------------- guard
ns, _, _ = load()
g = ns["check_guard"]
at = lambda h, mi, d=26: dt.datetime(2026, 11, d, h, mi, tzinfo=CPH_WINTER)  # noqa: E731
yesterday_evening = [{"timestamp": ts(2026, 11, 25, 20, 4), "permalink": "p0"}]
check("early 07:05, last post yesterday evening -> go", g("early", yesterday_evening, at(7, 5)) == [])
r = g("early", [{"timestamp": ts(2026, 11, 26, 7, 2), "permalink": "p1"}] + yesterday_evening, at(7, 9))
check("early 07:09, posted 07:02 -> stop (recent + slot)", len(r) == 2 and "already posted" in r[1], r)
check("early 09:30 -> too late", "too late" in " ".join(g("early", yesterday_evening, at(9, 30))))
check("early 06:40 -> too early", "too early" in " ".join(g("early", yesterday_evening, at(6, 40))))
check("early 06:55 -> within tolerance", g("early", yesterday_evening, at(6, 55)) == [])
today_early = [{"timestamp": ts(2026, 11, 26, 7, 3), "permalink": "e1"}] + yesterday_evening
check("midday 13:05 after early 07:03 -> go", g("midday", today_early, at(13, 5)) == [])
r = g("midday", [{"timestamp": ts(2026, 11, 26, 13, 2), "permalink": "m1"}] + today_early, at(13, 9))
check("midday 13:09, posted 13:02 -> stop", any("already posted" in x for x in r), r)
today_two = [{"timestamp": ts(2026, 11, 26, 13, 4), "permalink": "m1"}] + today_early
check("evening 20:05 after 07 and 13 -> go", g("evening", today_two, at(20, 5)) == [])
r = g("evening", [{"timestamp": ts(2026, 11, 26, 20, 1), "permalink": "v1"}] + today_two, at(20, 6))
check("evening 20:06, posted 20:01 -> stop", any("already posted" in x for x in r), r)
check("evening 22:30 -> too late", "too late" in " ".join(g("evening", today_two, at(22, 30))))
check("a post at 06:11 counts as today's early slot",
      any("already posted" in x for x in g("early", [{"timestamp": ts(2026, 11, 26, 6, 11), "permalink": "o"}], at(7, 30))))
so = ns["slot_of"]
check("slot_of boundaries", [so(at(h, m)) for h, m in [(9, 59), (10, 0), (16, 59), (17, 0), (20, 0)]]
      == ["early", "midday", "midday", "evening", "evening"])
check("dry run ignores the window", g("midday", yesterday_evening, at(23, 30), enforce_window=False) == [])
off = ns["_cph_offset_hours"]
U = dt.timezone.utc
check("DST fallback: winter", off(dt.datetime(2026, 11, 25, 12, tzinfo=U)) == 1)
check("DST fallback: summer", off(dt.datetime(2026, 7, 1, 12, tzinfo=U)) == 2)
check("DST fallback: 29/3 00:59 UTC", off(dt.datetime(2026, 3, 29, 0, 59, tzinfo=U)) == 1)
check("DST fallback: 29/3 01:00 UTC", off(dt.datetime(2026, 3, 29, 1, 0, tzinfo=U)) == 2)
check("DST fallback: 25/10 01:00 UTC", off(dt.datetime(2026, 10, 25, 1, 0, tzinfo=U)) == 1)
check("zoneinfo summer +2", ns["to_cph"](dt.datetime(2026, 7, 1, 4, 0, tzinfo=U)).hour == 6)

# ---------------------------------------------------------------- renderer: punctuation after a red word (26/11-2026)
tok = ns["_tokens"]
check("tokens: '*exits*.' keeps the period on the word", tok("fewer *exits*.") == [("fewer", False), ("exits.", True)])
check("tokens: '*Monday*,' keeps the comma", tok("*Monday*, again") == [("Monday,", True), ("again", False)])
check("tokens: no change without accents", tok("plain text, no accents.") == [("plain", False), ("text,", False),
                                                                              ("no", False), ("accents.", False)])
img, info = ns["render_slide"]("You don't need more motivation. You need fewer *exits*.", "hook", None, "dark", 0, 3)
check("render: no line is only punctuation", all(any(c.isalnum() for c in ln) for ln in info["lines"]), info["lines"])

# ---------------------------------------------------------------- Facebook caption
fb = ns["fb_caption"]
check("evening FB: the Circle Audit line gets its Gumroad link",
      fb("evening", EVENING["caption"]).endswith("Get it here: https://xbettereverydayx.gumroad.com/l/wzidk"))
check("FB: a line about an unknown product is removed", "Link in bio" not in fb("midday", "Hook\n\nBuy it. Link in bio.\n\n#x"))

# ---------------------------------------------------------------- dry run
MEDIA = [{"id": "1", "caption": "Old caption about something else entirely.", "timestamp": ts(2026, 11, 25, 19, 38),
          "media_type": "IMAGE", "like_count": 1, "comments_count": 0, "permalink": "p"}]
ns, calls, uploads = load({"INSTAGRAM_GET_IG_USER_MEDIA": [{"data": MEDIA}]}, now=at(23, 30))
r = ns["publish"](MORNING, "midday", dry_run=True)
check("dry run: ok and 3 images", r["ok"] and r["stage"] == "dry_run_done" and len(r["images"]) == 3, r)
check("dry run: no Instagram/Facebook writes", [c[0] for c in calls] == ["INSTAGRAM_GET_IG_USER_MEDIA"])
p = ns["prepare"]("midday", dry_run=True)
check("prepare dry run: not stopped, 1 recent post", p["stop"] is False and len(p["recent_posts"]) == 1, p)
ns, calls, _ = load({"INSTAGRAM_GET_IG_USER_MEDIA": [{"data": MEDIA}]}, now=at(23, 30))
p = ns["prepare"]("midday")
check("prepare at 23:30: stop (late)", p["stop"] and "late" in p["reasons"][0], p)
r = ns["publish"](MORNING, "midday")
check("publish at 23:30 without dry run: blocked by guard", r["stage"] == "guard" and not r["ok"], r)
check("... and nothing written", all(c[0] == "INSTAGRAM_GET_IG_USER_MEDIA" for c in calls))

# ---------------------------------------------------------------- real midday carousel run (faked API)
OK_SCRIPT = {
    "INSTAGRAM_GET_IG_USER_MEDIA": [{"data": MEDIA}],
    "INSTAGRAM_CREATE_CAROUSEL_CONTAINER": [{"id": "c1"}],
    "INSTAGRAM_GET_POST_STATUS": [{"status_code": "IN_PROGRESS"}, {"status_code": "FINISHED"}],
    "INSTAGRAM_POST_IG_USER_MEDIA_PUBLISH": [{"id": "m1"}],
    "INSTAGRAM_GET_IG_MEDIA": [{"id": "m1", "media_type": "CAROUSEL_ALBUM", "permalink": "https://ig/p/m1",
                                "children": {"data": [{"id": "a"}, {"id": "b"}, {"id": "c"}]}}],
    "FACEBOOK_CREATE_MULTI_PHOTO_POST": [{"post_id": "fb1"}],
}
ns, calls, _ = load({k: list(v) for k, v in OK_SCRIPT.items()}, now=at(13, 9))
r = ns["publish"](MORNING, "midday")
names = [c[0] for c in calls]
check("morning: ok, done, permalink", r["ok"] and r["stage"] == "done" and r["permalink"] == "https://ig/p/m1", r)
check("morning: exactly one container, one publish, one FB post",
      names.count("INSTAGRAM_CREATE_CAROUSEL_CONTAINER") == 1 and names.count("INSTAGRAM_POST_IG_USER_MEDIA_PUBLISH") == 1
      and names.count("FACEBOOK_CREATE_MULTI_PHOTO_POST") == 1, names)
cont = next(c for c in calls if c[0] == "INSTAGRAM_CREATE_CAROUSEL_CONTAINER")
check("morning: 3 children in order with s3 keys",
      [x["name"] for x in cont[1]["child_image_files"]] == ["morning_1.jpg", "morning_2.jpg", "morning_3.jpg"])
check("morning: caption has hashtags after a blank line", cont[1]["caption"].endswith("#mindsetshift")
      and "\n\n#xbettereverydayx" in cont[1]["caption"])
fbc = next(c for c in calls if c[0] == "FACEBOOK_CREATE_MULTI_PHOTO_POST")
check("morning: FB only to the xBE page with 3 direct links", fbc[1]["page_id"] == "1033703049835931"
      and len(fbc[1]["photo_urls"]) == 3 and all("r2.cloudflarestorage" in u for u in fbc[1]["photo_urls"]))
check("morning: accounts are the xBE accounts", all(c[2] in ("instagram_stylet-manful", "facebook_stoff-riksha")
                                                    for c in calls))

# publish error, but the post went out -> no second publish
s = {k: list(v) for k, v in OK_SCRIPT.items()}
s["INSTAGRAM_POST_IG_USER_MEDIA_PUBLISH"] = [RuntimeError("timeout")]
s["INSTAGRAM_GET_IG_USER_MEDIA"] = [{"data": MEDIA}, {"data": [{"id": "m1", "timestamp": dt.datetime.now(
    dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+0000")}]}]
ns, calls, _ = load(s, now=at(13, 9))
r = ns["publish"](MORNING, "midday")
names = [c[0] for c in calls]
check("publish error + post found: no retry", r["ok"] and names.count("INSTAGRAM_POST_IG_USER_MEDIA_PUBLISH") == 1
      and "went out" in " ".join(r["warnings"]), (r, names))

# publish error, nothing out -> exactly one retry
s = {k: list(v) for k, v in OK_SCRIPT.items()}
s["INSTAGRAM_POST_IG_USER_MEDIA_PUBLISH"] = [RuntimeError("500"), {"id": "m1"}]
s["INSTAGRAM_GET_IG_USER_MEDIA"] = [{"data": MEDIA}, {"data": MEDIA}]
ns, calls, _ = load(s, now=at(13, 9))
r = ns["publish"](MORNING, "midday")
names = [c[0] for c in calls]
check("publish error + nothing out: exactly one retry", r["ok"]
      and names.count("INSTAGRAM_POST_IG_USER_MEDIA_PUBLISH") == 2, (r, names))

# container ERROR -> nothing published
s = {k: list(v) for k, v in OK_SCRIPT.items()}
s["INSTAGRAM_GET_POST_STATUS"] = [{"status_code": "ERROR"}]
ns, calls, _ = load(s, now=at(13, 9))
r = ns["publish"](MORNING, "midday")
check("container ERROR: not published", not r["ok"] and r["stage"] == "instagram"
      and "INSTAGRAM_POST_IG_USER_MEDIA_PUBLISH" not in [c[0] for c in calls], r)

# Facebook error but the post exists -> no second FB post
s = {k: list(v) for k, v in OK_SCRIPT.items()}
s["FACEBOOK_CREATE_MULTI_PHOTO_POST"] = [RuntimeError("bad url")]
s["FACEBOOK_GET_PAGE_POSTS"] = [{"data": [{"id": "fbX", "created_time": dt.datetime.now(dt.timezone.utc).strftime(
    "%Y-%m-%dT%H:%M:%S+0000")}]}]
ns, calls, _ = load(s, now=at(13, 9))
r = ns["publish"](MORNING, "midday")
check("FB error + post found: no second FB post", r["ok"] and r["facebook"].startswith("ok (posted despite")
      and [c[0] for c in calls].count("FACEBOOK_CREATE_MULTI_PHOTO_POST") == 1, r)

# Facebook fails twice -> Instagram stays ok, FB reported as FAILED
s = {k: list(v) for k, v in OK_SCRIPT.items()}
s["FACEBOOK_CREATE_MULTI_PHOTO_POST"] = [RuntimeError("bad url"), RuntimeError("bad url again")]
s["FACEBOOK_GET_PAGE_POSTS"] = [{"data": []}]
ns, calls, _ = load(s, now=at(13, 9))
r = ns["publish"](MORNING, "midday")
check("FB fails twice: IG ok, FB FAILED, two attempts", r["ok"] and r["facebook"].startswith("FAILED")
      and [c[0] for c in calls].count("FACEBOOK_CREATE_MULTI_PHOTO_POST") == 2, r)

# quality control failure -> nothing uploaded or posted
bad = dict(MORNING, slides=MORNING["slides"][:2])
ns, calls, uploads = load({k: list(v) for k, v in OK_SCRIPT.items()}, now=at(13, 9))
r = ns["publish"](bad, "midday")
check("QC failure: stage qc, no upload, no post", r["stage"] == "qc" and not uploads
      and [c[0] for c in calls] == ["INSTAGRAM_GET_IG_USER_MEDIA"], r)

# slot already posted today -> guard
s = {k: list(v) for k, v in OK_SCRIPT.items()}
s["INSTAGRAM_GET_IG_USER_MEDIA"] = [{"data": [{"id": "x", "caption": "", "timestamp": ts(2026, 11, 26, 13, 2),
                                               "permalink": "px"}] + MEDIA}]
ns, calls, _ = load(s, now=at(14, 30))
r = ns["publish"](MORNING, "midday")
check("slot already posted today: blocked", r["stage"] == "guard" and not r["ok"], r)

# ---------------------------------------------------------------- real evening run (faked API)
s = {
    "INSTAGRAM_GET_IG_USER_MEDIA": [{"data": MEDIA}],
    "INSTAGRAM_POST_IG_USER_MEDIA": [{"id": "c2"}],
    "INSTAGRAM_GET_POST_STATUS": [{"status_code": "FINISHED"}],
    "INSTAGRAM_POST_IG_USER_MEDIA_PUBLISH": [{"id": "m2"}],
    "INSTAGRAM_GET_IG_MEDIA": [{"id": "m2", "media_type": "IMAGE", "permalink": "https://ig/p/m2"}],
    "FACEBOOK_CREATE_PHOTO_POST": [{"id": "1", "post_id": "fb2"}],
}
ns, calls, _ = load(s, now=at(20, 6))
r = ns["publish"](EVENING, "evening")
ev = next(c for c in calls if c[0] == "INSTAGRAM_POST_IG_USER_MEDIA")
fbp = next(c for c in calls if c[0] == "FACEBOOK_CREATE_PHOTO_POST")
check("evening: ok and done", r["ok"] and r["stage"] == "done" and not r["warnings"], r)
check("evening: alt text without asterisks", ev[1]["alt_text"].startswith("People who only call") and "*" not in ev[1]["alt_text"])
check("evening: Instagram keeps 'Link in bio.'", "Link in bio." in ev[1]["caption"])
check("evening: Facebook gets the Gumroad link, published", "Get it here: https://xbettereverydayx.gumroad.com/l/wzidk"
      in fbp[1]["message"] and fbp[1]["published"] is True and fbp[1]["photo"]["s3key"])

# ---------------------------------------------------------------- real early run (faked API)
EARLY = {"type": "early", "slides": [{"text": "Discipline is remembering what you *want* when you no longer feel like it."}],
         "caption": "Discipline is remembering what you want when you no longer feel like it.\n\nFeelings fade by noon. "
                    "Standards don't.\n\nWhat will you do today even if you don't feel like it?",
         "hashtags": ["#xbettereverydayx", "#selfdiscipline", "#morningmindset", "#standards", "#consistency"]}
s = {
    "INSTAGRAM_GET_IG_USER_MEDIA": [{"data": MEDIA}],
    "INSTAGRAM_POST_IG_USER_MEDIA": [{"id": "c3"}],
    "INSTAGRAM_GET_POST_STATUS": [{"status_code": "FINISHED"}],
    "INSTAGRAM_POST_IG_USER_MEDIA_PUBLISH": [{"id": "m3"}],
    "INSTAGRAM_GET_IG_MEDIA": [{"id": "m3", "media_type": "IMAGE", "permalink": "https://ig/p/m3"}],
    "FACEBOOK_CREATE_PHOTO_POST": [{"id": "2", "post_id": "fb3"}],
}
ns, calls, _ = load(s, now=at(7, 5))
r = ns["publish"](EARLY, "early")
names = [c[0] for c in calls]
check("early: one quote image on Instagram + Facebook", r["ok"] and r["stage"] == "done"
      and names.count("INSTAGRAM_POST_IG_USER_MEDIA") == 1 and names.count("FACEBOOK_CREATE_PHOTO_POST") == 1, (r, names))
check("early: no carousel calls", "INSTAGRAM_CREATE_CAROUSEL_CONTAINER" not in names)

print("\nall passed" if not FAILED else f"\n{len(FAILED)} FAILED: {FAILED}")
sys.exit(1 if FAILED else 0)
