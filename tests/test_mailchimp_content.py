# tests/test_mailchimp_content.py
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "loaders"))
sys.path.insert(0, os.path.join(ROOT, "jobs"))

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


import load_mailchimp_content as loader
import refresh_mailchimp_content as job


def test_load_builds_rows_and_enriches(monkeypatch):
    calls = {"content": [], "enrich": 0, "upserts": []}

    def fake_fetch(api_key, cid, session=None):
        calls["content"].append(cid)
        return {"html": f'<a href="https://x/{cid}">go</a>', "plain_text": f"body {cid}"}

    class FakeEnrichClient: pass
    def fake_enrich(client, text, *, model):
        calls["enrich"] += 1
        return {"primary_theme": "events", "topics": ["events"],
                "content_type": "newsletter", "featured_artists": []}

    def fake_bulk_upsert(conn, table, columns, rows, conflict_columns, update_columns, batch_size=5000):
        calls["upserts"].append((table, len(rows)))
        return len(rows)

    monkeypatch.setattr(loader, "fetch_campaign_content", fake_fetch)
    monkeypatch.setattr(loader, "enrich_text", fake_enrich)
    monkeypatch.setattr(loader, "bulk_upsert", fake_bulk_upsert)

    stats = loader.load(["c1", "c2"], api_key="k-us1", client=FakeEnrichClient(),
                        model="m", conn=object())
    assert stats["rows_read"] == 2
    assert stats["rows_upserted"] == 2
    assert stats["enriched"] == 2
    assert ("email_esp.fact_campaign_content", 2) in calls["upserts"]
    assert ("email_esp.fact_campaign_enrichment", 2) in calls["upserts"]


def test_job_run_posts_success(monkeypatch):
    posted = {}
    monkeypatch.setattr(job, "load", lambda *a, **k: {"table": "t", "rows_read": 3,
                        "rows_upserted": 3, "enriched": 3, "elapsed_sec": 1.0})
    monkeypatch.setattr(job, "post_success", lambda tag, stats: posted.setdefault("ok", (tag, stats)))
    monkeypatch.setattr(job, "post_failure", lambda tag, err: posted.setdefault("fail", (tag, err)))
    out = job.run()
    assert out["tag"] == "[ESP-CONTENT]"
    assert posted["ok"][0] == "[ESP-CONTENT]"
    assert "fail" not in posted


# D. Failure-path test
def test_job_run_posts_failure(monkeypatch):
    posted = {}
    monkeypatch.setattr(job, "load", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(job, "post_success", lambda tag, stats: posted.setdefault("ok", (tag, stats)))
    monkeypatch.setattr(job, "post_failure", lambda tag, err: posted.setdefault("fail", (tag, err)))
    with pytest.raises(RuntimeError):
        job.run()
    assert posted["fail"][0] == "[ESP-CONTENT]"
    assert "ok" not in posted


# F. HTML fallback test
def test_parse_content_falls_back_to_html_when_plaintext_empty():
    html = '<p>Hello <a href="https://radiomilwaukee.org/listen">listen here</a> now</p>'
    out = mc.parse_content(html, "")
    assert out["word_count"] > 0
    assert out["links"] == [{"url": "https://radiomilwaukee.org/listen", "label": "listen here"}]
    assert out["html"] == html


# E. Datacenter validation test
def test_base_url_rejects_invalid_datacenter_suffix():
    with pytest.raises(ValueError):
        mc.mailchimp_base_url("abc-notadc")


# G. fetch_campaign_content endpoint + auth test
def test_fetch_campaign_content_calls_endpoint_with_basic_auth():
    class FakeResponse:
        def raise_for_status(self):
            self._raised = True
        def json(self):
            return {"plain_text": "x", "html": "<p>x</p>"}

    calls = {}

    class FakeSession:
        def get(self, url, *, auth, timeout):
            calls["url"] = url
            calls["auth"] = auth
            calls["timeout"] = timeout
            self._resp = FakeResponse()
            return self._resp

    session = FakeSession()
    result = mc.fetch_campaign_content("mykey-us1", "CID", session=session)
    assert calls["url"] == "https://us1.api.mailchimp.com/3.0/campaigns/CID/content"
    assert calls["auth"][1] == "mykey-us1"
    assert hasattr(session._resp, "_raised")  # raise_for_status was called
    assert result == {"plain_text": "x", "html": "<p>x</p>"}


# A. Per-campaign failure isolation test
def test_load_isolates_per_campaign_failure(monkeypatch):
    captured = {}

    def fake_fetch(api_key, cid, session=None):
        if cid == "bad":
            raise RuntimeError("404")
        return {"html": f'<a href="https://x/{cid}">go</a>', "plain_text": f"body {cid}"}

    def fake_enrich(client, text, *, model):
        return {"primary_theme": "events", "topics": ["events"],
                "content_type": "newsletter", "featured_artists": []}

    def fake_bulk_upsert(conn, table, columns, rows, conflict_columns, update_columns, batch_size=5000):
        captured.setdefault(table, []).append(rows)
        return len(rows)

    monkeypatch.setattr(loader, "fetch_campaign_content", fake_fetch)
    monkeypatch.setattr(loader, "enrich_text", fake_enrich)
    monkeypatch.setattr(loader, "bulk_upsert", fake_bulk_upsert)

    stats = loader.load(["good", "bad"], api_key="k-us1", client=object(),
                        model="m", conn=object())

    assert stats["failed"] == 1
    assert stats["rows_read"] == 2          # both ids attempted
    assert stats["rows_upserted"] == 1      # only the good one landed
    content_rows = captured["email_esp.fact_campaign_content"][0]
    assert len(content_rows) == 1
    assert content_rows[0][0] == "good"     # campaign_id is first tuple element


def test_load_skips_llm_for_empty_body(monkeypatch):
    captured = {}
    enrich_calls = []

    def fake_fetch(api_key, cid, session=None):
        # Empty-body campaign: no html, no plain_text (RSS/archived/variant).
        return {"html": None, "plain_text": ""}

    def fake_enrich(client, text, *, model):
        enrich_calls.append(text)
        return {"primary_theme": "events", "topics": ["events"],
                "content_type": "newsletter", "featured_artists": []}

    def fake_bulk_upsert(conn, table, columns, rows, conflict_columns, update_columns, batch_size=5000):
        captured.setdefault(table, []).append(rows)
        return len(rows)

    monkeypatch.setattr(loader, "fetch_campaign_content", fake_fetch)
    monkeypatch.setattr(loader, "enrich_text", fake_enrich)
    monkeypatch.setattr(loader, "bulk_upsert", fake_bulk_upsert)

    stats = loader.load(["empty"], api_key="k-us1", client=object(),
                        model="m", conn=object())

    assert enrich_calls == []                # LLM never asked to tag empty content
    assert stats["enriched"] == 1            # an enrichment row is still written
    enrich_rows = captured["email_esp.fact_campaign_enrichment"][0]
    assert enrich_rows[0][1] is None         # primary_theme null (no fabricated tag)
    assert enrich_rows[0][3] is None         # content_type null
    assert enrich_rows[0][5] == "skipped-empty-body"   # model column documents the skip
