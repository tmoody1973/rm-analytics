from __future__ import annotations
import os
from pathlib import Path
import pytest
from service.chat_api import ChatThreadIn, _title_from

_ENV = Path.home() / ".radio-milwaukee" / ".env"

def _db() -> bool:
    if os.environ.get("DATABASE_URL"):
        return True
    if _ENV.exists():
        from dotenv import dotenv_values
        return bool(dotenv_values(_ENV).get("DATABASE_URL"))
    return False

def test_title_falls_back_to_first_user_message():
    t = ChatThreadIn(
        thread_id="11111111-1111-1111-1111-111111111111",
        clerk_user_id="user_1", user_email="a@b.org", title=None,
        messages=[{"seq": 0, "role": "user", "content": "How many donors?"}],
    )
    assert _title_from(t) == "How many donors?"

def test_title_truncates_long_first_message():
    long = "x" * 200
    t = ChatThreadIn(
        thread_id="11111111-1111-1111-1111-111111111111",
        clerk_user_id="u", user_email=None, title=None,
        messages=[{"seq": 0, "role": "user", "content": long}],
    )
    assert len(_title_from(t)) <= 120

_TID = "22222222-2222-2222-2222-222222222222"

def _sample(n_msgs: int) -> dict:
    return {
        "thread_id": _TID, "clerk_user_id": "user_test", "user_email": "t@rm.org",
        "title": None,
        "messages": [
            {"seq": i, "role": "user" if i % 2 == 0 else "assistant",
             "content": f"msg {i} donors", "tool_calls": None}
            for i in range(n_msgs)
        ],
    }

@pytest.mark.skipif(not _db(), reason="DATABASE_URL not set")
def test_resave_is_idempotent():
    from service.chat_api import save_thread, _owner_dsn
    import psycopg
    save_thread(_sample(3))
    save_thread(_sample(3))  # re-save same thread
    with psycopg.connect(_owner_dsn()) as c, c.cursor() as cur:
        cur.execute("SELECT count(*) FROM chat.messages WHERE thread_id=%s", (_TID,))
        assert cur.fetchone()[0] == 3   # not 6
        cur.execute("DELETE FROM chat.threads WHERE thread_id=%s", (_TID,))
        c.commit()

@pytest.mark.skipif(not _db(), reason="DATABASE_URL not set")
def test_list_threads_returns_saved_thread_newest_first():
    from service.chat_api import save_thread, list_threads, _owner_dsn
    import psycopg
    save_thread(_sample(2))
    rows = list_threads(limit=50)
    assert any(r["thread_id"] == _TID for r in rows)
    r = next(r for r in rows if r["thread_id"] == _TID)
    assert r["message_count"] == 2 and "updated_at" in r
    with psycopg.connect(_owner_dsn()) as c, c.cursor() as cur:
        cur.execute("DELETE FROM chat.threads WHERE thread_id=%s", (_TID,)); c.commit()

@pytest.mark.skipif(not _db(), reason="DATABASE_URL not set")
def test_search_finds_thread_by_message_word():
    from service.chat_api import save_thread, search_chats, _owner_dsn
    import psycopg
    save_thread({
        "thread_id": _TID, "clerk_user_id": "u", "user_email": "t@rm.org", "title": None,
        "messages": [{"seq": 0, "role": "user", "content": "underwriting revenue by daypart"}],
    })
    hits = search_chats("underwriting", limit=30)
    assert any(h["thread_id"] == _TID for h in hits)
    assert "snippet" in next(h for h in hits if h["thread_id"] == _TID)
    with psycopg.connect(_owner_dsn()) as c, c.cursor() as cur:
        cur.execute("DELETE FROM chat.threads WHERE thread_id=%s", (_TID,)); c.commit()

@pytest.mark.skipif(not _db(), reason="DATABASE_URL not set")
def test_get_thread_returns_messages_in_order():
    from service.chat_api import save_thread, get_thread, _owner_dsn
    import psycopg
    save_thread(_sample(3))
    out = get_thread(_TID)
    assert out is not None
    assert [m["seq"] for m in out["messages"]] == [0, 1, 2]
    with psycopg.connect(_owner_dsn()) as c, c.cursor() as cur:
        cur.execute("DELETE FROM chat.threads WHERE thread_id=%s", (_TID,)); c.commit()
