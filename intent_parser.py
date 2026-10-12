import re

# Explicit aliases keep parsing predictable and avoid guessing from vague messages.
ALIASES = {
    "create": ("create", "make", "add", "set up", "setup", "open", "spin up", "put together"),
    "channel": ("channel", "text channel", "chat channel", "room"),
    "forum": ("forum", "forum channel"),
    "thread": ("thread", "discussion thread"),
    "role": ("role", "server role", "member role"),
}


def normalize(text: str) -> str:
    text = text.replace("’", "'").replace("“", '"').replace("”", '"')
    text = re.sub(r"\b(?:wanna)\b", "want to", text, flags=re.I)
    text = re.sub(r"\b(?:gonna)\b", "going to", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def _clean_name(value: str, slug: bool = False):
    name = value.strip().strip('"').strip("'").strip().rstrip(".,!?;")
    if not name or len(name) > 100:
        return None
    if slug:
        name = re.sub(r"[^\w -]", "", name)
        name = re.sub(r"\s+", "-", name).strip("-").lower()
    return name or None


def extract_intent(raw_text: str):
    """Parse one supported action, preserving the original single-action API."""
    text = normalize(raw_text)
    actions = [
        ("create_forum", r"\b(?:create|make|add|set up|setup|open|spin up|put together)\s+(?:me\s+)?(?:a\s+)?forum(?:\s+channel)?\s+(?:named|called|titled)\s+(.+?)\s*(?:please|pls|thanks|thank you)?[.!?,;]*$", True),
        ("create_thread", r"\b(?:create|make|start|open|spin up|set up)\s+(?:me\s+)?(?:a\s+)?thread\s+(?:named|called|titled)\s+(.+?)\s*(?:please|pls|thanks|thank you)?[.!?,;]*$", False),
        ("create_role", r"\b(?:create|make|add|set up)\s+(?:me\s+)?(?:a\s+)?role\s+(?:named|called|titled)\s+(.+?)\s*(?:please|pls|thanks|thank you)?[.!?,;]*$", False),
        ("create_text_channel", r"\b(?:create|make|add|set up|setup|open)\s+(?:me\s+)?(?:a\s+)?(?:text\s+|chat\s+)?channel\s+(?:named|called|titled)\s+(.+?)\s*(?:please|pls|thanks|thank you)?[.!?,;]*$", True),
    ]
    for action, pattern, slug in actions:
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        name = _clean_name(match.group(1), slug=slug)
        if name:
            return action, name
    return None


def extract_intents(raw_text: str):
    """Return ordered actions for a message, including forum creation followed by a post."""
    text = normalize(raw_text)

    forum_match = re.search(
        r"""\b(?:create|make|add|set up|setup|open|spin up|put together)\s+(?:me\s+)?(?:a\s+)?forum(?:\s+channel)?\s+(?:named|called|titled)\s+(?:"([^"]+)"|'([^']+)'|(.+?))(?=\s+and\s+(?:make|create|add)\s+(?:a\s+)?post\b|[.!?]*$)""",
        text, re.I,
    )
    post_match = re.search(
        r"""\b(?:make|create|add)\s+(?:me\s+)?(?:a\s+)?post\s+(?:in\s+(?:it|that\s+forum|the\s+forum)\s+)?(?:titled|named|called)\s+(?:"([^"]+)"|'([^']+)'|(.+?))\s+with\s+(?:a\s+)?message\s+saying\s+(?:"([^"]*)"|'([^']*)'|(.+?))[.!?]*$""",
        text, re.I,
    )
    if forum_match and post_match:
        forum_name = _clean_name(next(group for group in forum_match.groups() if group is not None), slug=True)
        title = _clean_name(next(group for group in post_match.groups()[:3] if group is not None))
        body = next(group for group in post_match.groups()[3:] if group is not None).strip().rstrip(".,!?;")
        if forum_name and title and body and len(body) <= 2000:
            return [("create_forum", forum_name), ("create_forum_post", forum_name, title, body)]

    single = extract_intent(text)
    return [single] if single else []
