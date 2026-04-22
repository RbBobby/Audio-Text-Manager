from __future__ import annotations

from backend.app.summary.text_clip import clip_head_tail


def test_clip_head_tail_short_unchanged() -> None:
    s = "hello world"
    assert clip_head_tail(s, 100) == s


def test_clip_head_tail_long() -> None:
    s = "A" * 5000
    out = clip_head_tail(s, 200)
    assert len(out) <= 200
    assert "omitted middle" in out
    assert out.startswith("A")
    assert out.endswith("A")
