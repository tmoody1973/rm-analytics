import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "loaders"))

import _social_enrich as se


def test_validate_drops_out_of_vocab_and_dedups_artists():
    raw = {"content_theme": "local_artist_feature", "format": "reel",
           "primary_topic": "music_discovery", "hook_style": "question",
           "has_cta": True, "featured_artists": ["Klassik", "Klassik", "  GGOOLD "]}
    out = se.validate_enrichment(raw)
    assert out["content_theme"] == "local_artist_feature"
    assert out["format"] == "reel"
    assert out["has_cta"] is True
    assert out["featured_artists"] == ["Klassik", "GGOOLD"]


def test_validate_nulls_invalid_scalars():
    out = se.validate_enrichment({"content_theme": "nope", "format": "bogus",
                                  "primary_topic": "nope", "hook_style": "nope",
                                  "has_cta": "yes", "featured_artists": None})
    assert out == {"content_theme": None, "format": None, "primary_topic": None,
                   "hook_style": None, "has_cta": None, "featured_artists": []}


def test_enrich_post_uses_injected_client_and_validates():
    class FakeBlock:
        type = "tool_use"
        input = {"content_theme": "event_promo", "format": "image",
                 "primary_topic": "events", "hook_style": "announcement",
                 "has_cta": True, "featured_artists": ["junk", "Foo"]}
    class FakeResp:
        content = [FakeBlock()]
    class FakeClient:
        def __init__(self): self.messages = self
        def create(self, **kw):
            assert kw["tool_choice"]["name"] == "record_post_enrichment"
            return FakeResp()
    out = se.enrich_post(FakeClient(), "Big show this Friday — tickets in bio!")
    assert out["content_theme"] == "event_promo"
    assert out["has_cta"] is True
