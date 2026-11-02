"""Render every post in content/test_week.json and fail if any QC check fails."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import xbe_render  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
out = sys.argv[1] if len(sys.argv) > 1 else "previews"
week = json.load(open(os.path.join(ROOT, "content", "test_week.json")))

failed = 0
for day in week:
    for kind in ("morning", "evening"):
        res = xbe_render.render(day[kind], os.path.join(out, f"day{day['day']}"), [])
        n = len(res["files"])
        status = "OK " if res["ok"] else "FAIL"
        print(f"{status} day {day['day']} {kind}: {n} image(s)")
        for e in res["errors"]:
            print("     -", e)
        expected = 3 if kind == "morning" else 1
        if not res["ok"] or n != expected:
            failed += 1
print("all passed" if not failed else f"{failed} post(s) failed")
sys.exit(1 if failed else 0)
