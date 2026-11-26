"""Builds the scheduled-task prompts (prompts/morning.md, prompts/evening.md) from task_template.md,
so both tasks share one set of rules.

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
PINNED = {"H_RENDERER": "prompts/renderer_inline.py", "H_PIPELINE": "scripts/xbe_pipeline.py"}

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
tpl = open(os.path.join(HERE, "task_template.md")).read().replace("@@BOOTSTRAP@@", boot)

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
"style":"sans" only for a hard-hitting, punchy line.""",
        "CAPTION_END": 'an invitation to reflect or comment (a question is fine)',
        "CTA_RULES": """Product promotion (Gumroad) - ONLY on Wednesday (weekday 3) and Sunday (weekday 7):
- Pick the quote topic from relationships, loyalty, betrayal, boundaries or self-respect.
- Write the caption as usual, then end it with ONE soft, natural line pointing to the digital
  guide "The Circle Audit" (helps identify who truly supports you, fake loyalty and draining
  friendships), ending with "Link in bio." Example tone (do not copy verbatim): "Not sure who's
  really in your corner? The Circle Audit helps you find out. Link in bio."
- Never a hard sell, never prices, never URLs, never more than one product line.
On all other days: no product mention at all.""",
        "FB_NOTE": 'Facebook gets the same text, with "Link in bio." turned into the Gumroad link by the code.',
    },
}

for slot, parts in SLOTS.items():
    text = tpl.replace("{{SLOT}}", slot)
    for k, v in parts.items():
        text = text.replace("{{" + k + "}}", v)
    assert "{{" not in text, f"unfilled placeholder in {slot}"
    with open(os.path.join(HERE, f"{slot}.md"), "w") as f:
        f.write(text)
    print(slot, len(text), "chars")
