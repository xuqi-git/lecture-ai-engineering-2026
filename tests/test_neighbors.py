"""第5回 宿題（実装）: 前後ページ付き検索のテスト（APIを呼ばない）。"""

import json

import pytest

from app import retrieval, tools
from app.retrieval import add_neighbor_pages, load_pages


def _pages():
    return [
        {"page_id": f"{doc}-p{n:03d}", "document_id": doc, "page": n, "title": f"{doc} {n}", "content": f"{doc} 本文{n}"}
        for doc in ("lec01-main", "lec02-main") for n in range(1, 5)
    ]


def _hit(page_id, distance):
    page = next(p for p in _pages() if p["page_id"] == page_id)
    return {**page, "distance": distance}


def test_adds_previous_and_next_page_of_same_document():
    out = add_neighbor_pages([_hit("lec02-main-p002", 0.1)], _pages(), window=1)
    assert [r["page_id"] for r in out] == ["lec02-main-p002", "lec02-main-p001", "lec02-main-p003"]
    assert [r["role"] for r in out] == ["hit", "neighbor", "neighbor"]
    assert out[1]["neighbor_of"] == "lec02-main-p002" and out[1]["offset"] == -1


def test_does_not_cross_document_boundary():
    out = add_neighbor_pages([_hit("lec01-main-p004", 0.1)], _pages(), window=1)
    assert [r["page_id"] for r in out] == ["lec01-main-p004", "lec01-main-p003"]


def test_no_duplicates_and_hits_keep_rank_and_role():
    hits = [_hit("lec02-main-p002", 0.1), _hit("lec02-main-p003", 0.2)]
    out = add_neighbor_pages(hits, _pages(), window=1)
    ids = [r["page_id"] for r in out]
    assert len(ids) == len(set(ids))
    assert ids == ["lec02-main-p002", "lec02-main-p001", "lec02-main-p003", "lec02-main-p004"]
    assert next(r for r in out if r["page_id"] == "lec02-main-p003")["role"] == "hit"


def test_window_zero_returns_hits_only_and_negative_is_rejected():
    hits = [_hit("lec01-main-p002", 0.1)]
    assert [r["page_id"] for r in add_neighbor_pages(hits, _pages(), window=0)] == ["lec01-main-p002"]
    with pytest.raises(ValueError):
        add_neighbor_pages(hits, _pages(), window=-1)


def test_real_lecture_page_order_has_neighbors_for_lec02_p052(monkeypatch):
    pages = load_pages()
    target = next(p for p in pages if p["page_id"] == "lec02-main-p052")
    out = add_neighbor_pages([{**target, "distance": 0.0}], pages, window=1)
    assert out[0]["page_id"] == "lec02-main-p052"
    assert {r["page"] for r in out[1:]} <= {target["page"] - 1, target["page"] + 1}
    assert all(r["document_id"] == "lec02-main" for r in out)


def test_tool_returns_json_with_roles(monkeypatch):
    monkeypatch.setattr(retrieval, "search", lambda q: [_hit("lec02-main-p002", 0.1)])
    monkeypatch.setattr(retrieval, "load_pages", lambda source=None: _pages())
    data = json.loads(tools.search_materials_with_neighbors("LoRA"))
    assert [r["role"] for r in data["results"]] == ["hit", "neighbor", "neighbor"]
