"""Builds the scheduled-task prompts from task_template.md, so all slots share one set of rules:
prompts/midday.md (13:00 routine), prompts/quote.md (one routine at 07:00 and 20:00 - the clock picks the slot)
and prompts/early.md + prompts/evening.md (the same two slots, for separate routines if they get their own).

v2 (26/11-2026): the renderer and the publishing steps are no longer copied into the prompt. The task loads
prompts/renderer_inline.py and scripts/xbe_pipeline.py at a PINNED commit and checks their SHA-256:

    python prompts/build_prompts.py <commit-sha>

The commit must contain exactly the local versions of both files (checked with git). v1 is in prompts/archive/.
"""
import hashlib
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PINNED = {"H_RENDERER": "prompts/renderer_inline.py", "H_REEL": "scripts/xbe_reel.py",
          "H_PIPELINE": "scripts/xbe_pipeline.py"}

commit = sys.argv[1] if len(sys.argv) > 1 else subprocess.check_output(
    ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
hashes = {}
for key, path in PINNED.items():
    local = open(os.path.join(ROOT, path), "rb").read()
    committed = subprocess.check_output(["git", "show", f"{commit}:{path}"], cwd=ROOT)
    assert local == committed, f"{path} differs from commit {commit} - commit it first"
    hashes[key] = hashlib.sha256(committed).hexdigest()

boot = open(os.path.join(HERE, "bootstrap.py.tpl")).read().strip().replace("{{COMMIT}}", commit)
for key, value in hashes.items():
    boot = boot.replace("{{" + key + "}}", value)
tpl = open(os.path.join(HERE, "task_template.md")).read()

SLOTS = {
    "early": {
        "SLOT_RULES": """EARLY = ONE single image with ONE original quote of 5-25 words that stands alone without
explanation. It goes out at 07:00 Copenhagen time - the first post of the day for Europe and midday
for India, Asia and Australia. Short and punchy: discipline, standards, action, consistency,
self-respect, mental strength. Use "style":"sans" (bold uppercase) by default; "serif" only for a
quieter, reflective line. Never the theme of the last midday carousel or evening quote.""",
        "CAPTION_END": "one short question that invites a comment",
        "CTA_RULES": "Product promotion: none in early posts. Never mention products, links or sales.",
        "FB_NOTE": "Facebook gets the same text.",
    },
    "midday": {
        "SLOT_RULES": """MIDDAY = Instagram carousel with EXACTLY 3 slides that form ONE coherent message.
It goes out at 13:00 Copenhagen time = early morning in the US, where a third of the followers
live, and evening in India. Focus: motivation, discipline, mindset, taking action. Goal: start
the day with intention.
- Slide 1 THE HOOK: 5-12 words, stops the scroll, creates curiosity or emotional impact,
  makes people swipe. (Rendered as bold uppercase sans.)
- Slide 2 THE MESSAGE: 1-3 short sentences (max ~40 words) expanding the hook; the reader
  should recognise their own life. No long explanations. (Rendered as elegant serif.)
- Slide 3 THE ACTION: 3-16 words, a direct challenge for today. Short, memorable,
  uncompromising. (Rendered as heavy uppercase sans.)
Slide 1 = interest, slide 2 = recognition, slide 3 = action. Never three unrelated quotes,
never the same sentence on two slides.
Themes: discipline, responsibility, time, ambition, consistency, procrastination, bad habits,
accountability.""",
        "CAPTION_END": 'one natural engagement question about today',
        "CTA_RULES": "Product promotion: none in midday posts. Never mention products, links or sales.",
        "FB_NOTE": "Facebook gets the same text.",
    },
    "evening": {
        "SLOT_RULES": """EVENING = ONE single image with ONE original quote of 5-25 words that stands
alone without explanation. Goal: reflection, recognition, shares and comments.
Topics: self-respect, loyalty, relationships, betrayal, personal growth, discipline, time and
mortality, ambition, comfort zones, life lessons, boundaries, mental strength, accountability,
character, consistency. Emotional depth, truth, relatability. Default style serif; use
"style":"sans" only for a hard-hitting, punchy line.
The evening quote is posted as a Reel: the code shows it word by word over original background sound
(6-13 seconds) and holds it at the end. Write it so it builds to its last words; 8-20 words works best.""",
        "CAPTION_END": 'an invitation to reflect or comment (a question is fine)',
        "CTA_RULES": """Product promotion (Gumroad) - ONLY on Wednesday (weekday 3) and Sunday (weekday 7):
- Pick the quote topic from relationships, loyalty, betrayal, boundaries or self-respect.
- Write the caption as usual, then end it with ONE soft, natural line pointing to the digital
  guide "The Circle Audit" (helps identify who truly supports you, fake loyalty and draining
  friendships), ending with "Link in bio." Example tone (do not copy verbatim): "Not sure who's
  really in your corner? The Circle Audit helps you find out. Link in bio."
- Never a hard sell, never prices, never URLs, never more than one product line.
On all other days: no product mention at all.""",
        "FB_NOTE": 'Facebook gets the Reel as a video with the same text, with "Link in bio." turned into the\n'
                   'Gumroad link by the code.',
        "REEL_STEPS": "REEL",
    },
}

# Reels (Simon 26/11-2026: the 20:00 quote is a Reel). Video takes Instagram 30-120 s to process and a workbench
# cell may run 180 s at most, so publish() can stop at "processing"/"facebook_pending" and finish() carries on.
REEL_STEPS = """- stage "processing" or "facebook_pending" (evening Reel only): the Reel is uploaded and Instagram or
  Facebook needs more time. Run this cell and read its result the same way - repeat while the stage is
  "processing" or "facebook_pending", at most 4 times; still not done after 4 runs: send a PushNotification
  "xBetterEverydayx {{SLOT}}: the Reel is not finished after 4 tries (<stage>)" and STOP:
```python
@@BOOTSTRAP@@
{{SLOT_CODE}}
print(json.dumps(finish(SLOT), indent=1))
```
- stage "lost" (from finish): run the publish cell once more - the guard stops it if the Reel is already out.
"""



def render(name, slot_label, parts):
    parts = dict(parts)
    steps = REEL_STEPS if parts.pop("REEL_STEPS", "") == "REEL" else ""
    text = tpl.replace("{{REEL_STEPS}}", steps).replace("@@BOOTSTRAP@@", boot)
    text = text.replace("{{SLOT}}", slot_label)
    for k, v in parts.items():
        text = text.replace("{{" + k + "}}", v)
    assert "{{" not in text, f"unfilled placeholder in {name}"
    with open(os.path.join(HERE, f"{name}.md"), "w") as f:
        f.write(text)
    print(name, len(text), "chars")


for slot, parts in SLOTS.items():
    render(slot, slot, dict(parts,
                            SLOT_HEADER=f"{slot}  (early 07:00 | midday 13:00 | evening 20:00)",
                            SLOT_CODE=f'SLOT = "{slot}"',
                            SLOT_NOTE=""))

# 26/11-2026: a routine created from a session without connector grants gets no Composio access, so the two
# single-image slots share the routine that has it. The clock decides the slot in BOTH cells (a run takes
# minutes and fires at 07:00 or 20:00, so the two cells always agree); the slot windows in the code still apply.
E, V = SLOTS["early"], SLOTS["evening"]
_cta = V["CTA_RULES"].replace("Product promotion (Gumroad) - ONLY", "Evening posts - product promotion (Gumroad) ONLY", 1)
assert _cta != V["CTA_RULES"]
render("quote", "<slot>", {
    "SLOT_HEADER": "early at 07:00 or evening at 20:00 - this routine runs at both times; step 1 prints the slot",
    "SLOT_CODE": 'SLOT = "early" if now_cph().hour < 14 else "evening"  # this routine runs at 07:00 and 20:00',
    "SLOT_NOTE": '- "slot" is early or evening - the clock decides. Below, <slot> means that slot.\n',
    "SLOT_RULES": "Write for <slot> only, with the rules for that slot:\n\n" + E["SLOT_RULES"] + "\n\n" + V["SLOT_RULES"],
    "CAPTION_END": "one short question that invites a comment (early), or an invitation to reflect or comment -\n"
                   "a question is fine (evening)",
    "CTA_RULES": "Early posts - no product promotion: never mention products, links or sales.\n" + _cta,
    "FB_NOTE": 'Facebook gets the same image (early) or the Reel as a video (evening) with the same text, with\n'
               '"Link in bio." turned into the Gumroad link by the code.',
    "REEL_STEPS": "REEL",
})
