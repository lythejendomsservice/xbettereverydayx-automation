"""Builds the final scheduled-task prompts (prompts/morning.md, prompts/evening.md)
from task_template.md so both tasks share one set of rules."""
import os

HERE = os.path.dirname(__file__)
tpl = open(os.path.join(HERE, "task_template.md")).read()

SLOTS = {
    "morning": {
        "SLOT_RULES": """MORNING = Instagram carousel with EXACTLY 3 slides that form ONE coherent message.
Focus: motivation, discipline, mindset, taking action. Goal: start the day with intention.
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
        "CAPTION_END": "one natural engagement question about today",
        "PUBLISH_STEPS": """COMPOSIO_MULTI_EXECUTE_TOOL -> INSTAGRAM_CREATE_CAROUSEL_CONTAINER, account
"instagram_stylet-manful", arguments {ig_user_id:"30053245364263763", caption:<caption>,
child_image_files:[{name:"morning_1.jpg",mimetype:"image/jpeg",s3key:<s3key 1>}, ...slide 2,
...slide 3 in this order]}. Must be exactly 3 children - never publish an incomplete carousel.
Check INSTAGRAM_GET_POST_STATUS on the returned id until status_code is FINISHED
(every 5 s, max 20 tries; ERROR -> STOP + PushNotification).""",
        "VERIFY": "It must be media_type CAROUSEL_ALBUM with exactly 3 children; otherwise PushNotification.",
    },
    "evening": {
        "SLOT_RULES": """EVENING = ONE single image with ONE original quote of 5-25 words that stands
alone without explanation. Goal: reflection, recognition, shares and comments.
Topics: self-respect, loyalty, relationships, betrayal, personal growth, discipline, time and
mortality, ambition, comfort zones, life lessons, boundaries, mental strength, accountability,
character, consistency. Emotional depth, truth, relatability. Default style serif; use
"style":"sans" only for a hard-hitting, punchy line.""",
        "CAPTION_END": "an invitation to reflect or comment (a question is fine)",
        "PUBLISH_STEPS": """COMPOSIO_MULTI_EXECUTE_TOOL -> INSTAGRAM_POST_IG_USER_MEDIA, account
"instagram_stylet-manful", arguments {ig_user_id:"30053245364263763", caption:<caption>,
alt_text:<the quote without asterisks>, image_file:{name:"evening_1.jpg",
mimetype:"image/jpeg", s3key:<s3key>}}.""",
        "VERIFY": "It must be media_type IMAGE; otherwise PushNotification.",
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
