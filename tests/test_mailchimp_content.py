# tests/test_mailchimp_content.py
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "loaders"))

import pytest
import _mailchimp as mc


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
