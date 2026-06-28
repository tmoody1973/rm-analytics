"""LLM enrichment of a social post caption into structured, closed-vocab tags.

One Haiku pass per post. The taxonomy here is the single source of truth;
validate_enrichment drops anything the model invents so GROUP BY stays clean.
Mirrors loaders/_enrich.py (newsletter enrichment).
"""
from __future__ import annotations

CONTENT_THEMES = {
    "local_artist_feature", "event_promo", "behind_the_scenes", "community",
    "music_discovery", "station_news", "contest_giveaway", "membership_giving",
    "partnership", "other",
}
FORMATS = {"reel", "carousel", "image", "video", "short", "text", "story"}
HOOK_STYLES = {"question", "bold_claim", "announcement", "listicle",
               "storytelling", "callout", "none"}
TOPICS = {"local_music", "artist_spotlight", "music_discovery", "events",
          "membership_giving", "station_news", "community", "partnerships",
          "podcasts", "contests"}

_MAX_ARTISTS = 20

ENRICH_TOOL = {
    "name": "record_post_enrichment",
    "description": "Record structured tags for one social media post.",
    "input_schema": {
        "type": "object",
        "properties": {
            "content_theme": {"type": "string", "enum": sorted(CONTENT_THEMES),
                              "description": "The single best-fit theme of the post."},
            "format": {"type": "string", "enum": sorted(FORMATS)},
            "primary_topic": {"type": "string", "enum": sorted(TOPICS)},
            "hook_style": {"type": "string", "enum": sorted(HOOK_STYLES),
                           "description": "The opening device of the caption."},
            "has_cta": {"type": "boolean",
                        "description": "True if the post asks the viewer to act (link in bio, tickets, donate, follow)."},
            "featured_artists": {"type": "array", "items": {"type": "string"},
                                 "description": "Proper names of musicians/bands actually mentioned."},
        },
        "required": ["content_theme", "format", "primary_topic", "hook_style",
                     "has_cta", "featured_artists"],
    },
}

_PROMPT = (
    "You tag social media posts for Radio Milwaukee's competitive intelligence. "
    "Read the caption and call record_post_enrichment with the closed-vocabulary "
    "tags. Use only the allowed enum values; if unsure of a field, choose the "
    "closest allowed value (or 'other'/'none'). featured_artists are proper names "
    "of musicians/bands actually mentioned.\n\nPost caption:\n"
)


def validate_enrichment(raw: dict) -> dict:
    raw = raw or {}
    ct = raw.get("content_theme")
    fmt = raw.get("format")
    pt = raw.get("primary_topic")
    hook = raw.get("hook_style")
    cta = raw.get("has_cta")
    artists_in = raw.get("featured_artists") if isinstance(raw.get("featured_artists"), list) else []

    artists, seen = [], set()
    for a in artists_in:
        if not isinstance(a, str):
            continue
        name = a.strip()
        if name and name not in seen:
            seen.add(name)
            artists.append(name)
    return {
        "content_theme": ct if ct in CONTENT_THEMES else None,
        "format": fmt if fmt in FORMATS else None,
        "primary_topic": pt if pt in TOPICS else None,
        "hook_style": hook if hook in HOOK_STYLES else None,
        "has_cta": cta if isinstance(cta, bool) else None,
        "featured_artists": artists[:_MAX_ARTISTS],
    }


def enrich_post(client, caption: str, *, model: str = "claude-haiku-4-5-20251001") -> dict:
    """Run one enrichment pass; returns a validated enrichment dict."""
    resp = client.messages.create(
        model=model,
        max_tokens=512,
        tools=[ENRICH_TOOL],
        tool_choice={"type": "tool", "name": "record_post_enrichment"},
        messages=[{"role": "user", "content": _PROMPT + (caption or "")[:8000]}],
    )
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use":
            return validate_enrichment(block.input)
    return validate_enrichment({})
