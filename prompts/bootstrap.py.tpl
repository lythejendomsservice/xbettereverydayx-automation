import hashlib, json, urllib.request
XBE_COMMIT = "{{COMMIT}}"
XBE_FILES = {"prompts/renderer_inline.py": "{{H_RENDERER}}",
             "scripts/xbe_reel.py": "{{H_REEL}}",
             "scripts/xbe_pipeline.py": "{{H_PIPELINE}}"}
if globals().get("XBE_LOADED") != XBE_COMMIT:
    for _p, _h in XBE_FILES.items():
        _b = urllib.request.urlopen("https://raw.githubusercontent.com/lythejendomsservice/xbettereverydayx-automation/" + XBE_COMMIT + "/" + _p, timeout=60).read()
        if hashlib.sha256(_b).hexdigest() != _h:
            raise SystemExit("HASH MISMATCH: " + _p + " - stop, publish nothing")
        exec(_b.decode("utf-8"))
    XBE_LOADED = XBE_COMMIT
