import re

# Small, explicit phrase map. This deliberately avoids guessing actions from vague messages.
ALIASES = {
    "create": ("create", "make", "add", "set up", "setup", "open", "spin up", "put together"),
    "channel": ("channel", "text channel", "chat channel", "room"),
    "forum": ("forum", "forum channel"),
    "thread": ("thread", "discussion thread"),
    "role": ("role", "server role", "member role"),
}

FILLER = re.compile(r"\b(?:hey|hi|hello|please|pls|plz|thanks|thank you|for me|if you can|if possible|when you get a chance|when you can|would you|could you|can you|will you|doll)\b", re.I)


def normalize(text: str) -> str:
    text = text.replace("’", "'").replace("“", '"').replace("”", '"')
    text = re.sub(r"\b(?:wanna)\b", "want to", text, flags=re.I)
    text = re.sub(r"\b(?:gonna)\b", "going to", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def extract_intent(raw_text: str):
    text = normalize(raw_text)
    # Require an explicit verb + resource + name. Quoted names preserve spaces.
    actions = [
        ("create_forum", r"\b(?:create|make|add|set up|setup|open)\s+(?:me\s+)?(?:a\s+)?forum(?:\s+channel)?\s+(?:named|called|titled)\s+(.+?)\s*(?:please|pls|thanks|thank you)?[.!?,;]*$", True),
        ("create_thread", r"\b(?:create|make|start|open|spin up|set up)\s+(?:me\s+)?(?:a\s+)?thread\s+(?:named|called|titled)\s+(.+?)\s*(?:please|pls|thanks|thank you)?[.!?,;]*$", False),
        ("create_role", r"\b(?:create|make|add|set up)\s+(?:me\s+)?(?:a\s+)?role\s+(?:named|called|titled)\s+(.+?)\s*(?:please|pls|thanks|thank you)?[.!?,;]*$", False),
        ("create_text_channel", r"\b(?:create|make|add|set up|setup|open)\s+(?:me\s+)?(?:a\s+)?(?:text\s+|chat\s+)?channel\s+(?:named|called|titled)\s+(.+?)\s*(?:please|pls|thanks|thank you)?[.!?,;]*$", True),
    ]
    for action, pattern, slug in actions:
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        name = match.group(1).strip().strip('"\'')
        if len(name) > 100 or not name:
            continue
        if slug:
            name = re.sub(r"[^\w -]", "", name)
            name = re.sub(r"\s+", "-", name).strip("-").lower()
        if name:
            return action, name
    return None
