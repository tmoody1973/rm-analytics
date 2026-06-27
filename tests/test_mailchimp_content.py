# tests/test_mailchimp_content.py
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "loaders"))

import pytest
import _mailchimp as mc
import _enrich as en


def test_base_url_uses_datacenter_suffix():
    assert mc.mailchimp_base_url("abc123def456-us21") == "https://us21.api.mailchimp.com/3.0"


def test_base_url_rejects_keys_without_suffix():
    with pytest.raises(ValueError):
        mc.mailchimp_base_url("no-datacenter-here-")


def test_parse_content_extracts_links_and_word_count():
    html = '<p>Hear <a href="https://radiomilwaukee.org/show">the show</a> now</p>'
    plain = "Hear the show now"
    out = mc.parse_content(html, plain)
    assert out["word_count"] == 4
    assert out["links"] == [{"url": "https://radiomilwaukee.org/show", "label": "the show"}]
    assert out["plain_text"] == "Hear the show now"
    assert out["html"] == html


def test_parse_content_handles_missing_body():
    out = mc.parse_content(None, None)
    assert out == {"plain_text": "", "html": None, "links": [], "word_count": 0}


def test_validate_drops_out_of_vocab_topics_and_dedups():
    raw = {"primary_theme": "events", "topics": ["events", "events", "made_up", "podcasts"],
           "content_type": "event_promo", "featured_artists": ["GGOOLD", "  Klassik  "]}
    out = en.validate_enrichment(raw)
    assert out["topics"] == ["events", "podcasts"]
    assert out["primary_theme"] == "events"
    assert out["content_type"] == "event_promo"
    assert out["featured_artists"] == ["GGOOLD", "Klassik"]


def test_validate_nulls_invalid_scalars():
    out = en.validate_enrichment({"primary_theme": "nope", "topics": "notalist",
                                  "content_type": "bogus", "featured_artists": None})
    assert out == {"primary_theme": None, "topics": [], "content_type": None, "featured_artists": []}


def test_enrich_text_uses_injected_client_and_validates():
    class FakeBlock:
        type = "tool_use"
        input = {"primary_theme": "local_music", "topics": ["local_music", "junk"],
                 "content_type": "newsletter", "featured_artists": ["Foo"]}
    class FakeResp:
        content = [FakeBlock()]
    class FakeClient:
        def __init__(self): self.messages = self
        def create(self, **kw):
            assert kw["tool_choice"]["name"] == "record_enrichment"
            return FakeResp()
    out = en.enrich_text(FakeClient(), "some newsletter body", model="claude-haiku-4-5-20251001")
    assert out["content_type"] == "newsletter"
    assert out["topics"] == ["local_music"]   # 'junk' dropped
