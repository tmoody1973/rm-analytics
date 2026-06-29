import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "jobs"))
sys.path.insert(0, os.path.join(ROOT, "loaders"))
sys.path.insert(0, ROOT)

import pytest
import refresh_social_intel as job
import _socialfetch as sf

ACCOUNTS = [
    {"account_id": "ig:a", "platform": "instagram", "handle": "a"},
    {"account_id": "ig:b", "platform": "instagram", "handle": "b"},
]


class _FakeConn:
    """Minimal DB connection stub: no real DB, just a no-op close()."""
    def close(self):
        pass


def _setup(monkeypatch, load_side_effect):
    monkeypatch.setattr(job, "get_db_connection", lambda: _FakeConn())
    monkeypatch.setattr(job, "active_accounts", lambda conn: list(ACCOUNTS))
    monkeypatch.setattr(job, "load", load_side_effect)


def test_run_aggregates_and_posts_success(monkeypatch):
    def fake_load(account, *, conn):
        return {"account_id": account["account_id"], "skipped": False,
                "posts_total": 3, "posts_upserted": 3, "snapshots_upserted": 1,
                "enriched": 2, "elapsed_sec": 1.0}
    _setup(monkeypatch, fake_load)
    posted = {}
    monkeypatch.setattr(job, "post_success", lambda tag, stats: posted.setdefault("ok", (tag, stats)))
    monkeypatch.setattr(job, "post_failure", lambda tag, err: posted.setdefault("fail", (tag, err)))

    out = job.run()
    assert out["tag"] == "[SOCIAL-INTEL]"
    assert out["accounts"] == 2 and out["fetched"] == 2
    assert out["posts_upserted"] == 6 and out["enriched"] == 4
    assert posted["ok"][0] == "[SOCIAL-INTEL]"
    assert "fail" not in posted


def test_run_isolates_one_bad_handle(monkeypatch):
    def fake_load(account, *, conn):
        if account["account_id"] == "ig:b":
            raise RuntimeError("boom")
        return {"account_id": "ig:a", "skipped": False, "posts_total": 1,
                "posts_upserted": 1, "snapshots_upserted": 1, "enriched": 0, "elapsed_sec": 1.0}
    _setup(monkeypatch, fake_load)
    monkeypatch.setattr(job, "post_success", lambda tag, stats: None)
    monkeypatch.setattr(job, "post_failure", lambda tag, err: None)

    out = job.run()
    assert out["fetched"] == 1            # the good account still landed
    assert out["failures"] == 1          # the bad one is counted, not fatal


def test_run_aborts_on_credit_error(monkeypatch):
    def fake_load(account, *, conn):
        raise sf.SocialfetchCreditError("402")
    _setup(monkeypatch, fake_load)
    posted = {}
    monkeypatch.setattr(job, "post_success", lambda tag, stats: posted.setdefault("ok", 1))
    monkeypatch.setattr(job, "post_failure", lambda tag, err: posted.setdefault("fail", err))

    with pytest.raises(sf.SocialfetchCreditError):
        job.run()
    assert "fail" in posted and "ok" not in posted
