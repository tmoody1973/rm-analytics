"""LLM enrichment of newsletter body text into structured, closed-vocab tags.

One Haiku pass per newsletter. The taxonomy here is the single source of truth;
validate_enrichment drops anything the model invents so GROUP BY stays clean.
"""
from __future__ import annotations

CONTENT_TYPES = {"newsletter", "event_promo", "fundraising_appeal", "announcement", "contest"}
TOPICS = {"local_music", "artist_spotlight", "music_discovery", "events",
          "membership_giving", "station_news", "community", "partnerships",
          "podcasts", "contests"}

_MAX_ARTISTS = 20

ENRICH_TOOL = {
    "name": "record_enrichment",
    "description": "Record structured tags for one newsletter.",
    "input_schema": {
        "type": "object",
        "properties": {
            "primary_theme": {"type": "string", "enum": sorted(TOPICS),
                              "description": "The single most-central topic."},
            "topics": {"type": "array", "items": {"type": "string", "enum": sorted(TOPICS)},
                       "description": "All topics the newsletter covers."},
            "content_type": {"type": "string", "enum": sorted(CONTENT_TYPES)},
            "featured_artists": {"type": "array", "items": {"type": "string"},
                                 "description": "Musicians/artists named in the body."},
        },
        "required": ["primary_theme", "topics", "content_type", "featured_artists"],
    },
}

_PROMPT = (
    "You tag Radio Milwaukee email newsletters. Read the body and call "
    "record_enrichment with the closed-vocabulary tags. Use only the allowed "
    "enum values; if unsure of a topic, omit it. featured_artists are proper "
    "names of musicians/bands actually mentioned.\n\nNewsletter body:\n"
)


def validate_enrichment(raw: dict) -> dict:
    raw = raw or {}
    pt = raw.get("primary_theme")
    ct = raw.get("content_type")
    topics_in = raw.get("topics") if isinstance(raw.get("topics"), list) else []
    artists_in = raw.get("featured_artists") if isinstance(raw.get("featured_artists"), list) else []

    topics = sorted({t for t in topics_in if t in TOPICS})
    artists, seen = [], set()
    for a in artists_in:
        if not isinstance(a, str):
            continue
        name = a.strip()
        if name and name not in seen:
            seen.add(name)
            artists.append(name)
    return {
        "primary_theme": pt if pt in TOPICS else None,
        "topics": topics,
        "content_type": ct if ct in CONTENT_TYPES else None,
        "featured_artists": artists[:_MAX_ARTISTS],
    }


def enrich_text(client, plain_text: str, *, model: str = "claude-haiku-4-5-20251001") -> dict:
    """Run one enrichment pass; returns a validated enrichment dict."""
    resp = client.messages.create(
        model=model,
        max_tokens=1024,
        tools=[ENRICH_TOOL],
        tool_choice={"type": "tool", "name": "record_enrichment"},
        messages=[{"role": "user", "content": _PROMPT + (plain_text or "")[:20000]}],
    )
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use":
            return validate_enrichment(block.input)
    return validate_enrichment({})
