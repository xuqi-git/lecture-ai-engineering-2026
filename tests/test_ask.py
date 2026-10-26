"""Validate the lecture's token-display change without making API requests."""

from types import SimpleNamespace as NS

import pytest

from app import ask


@pytest.mark.parametrize("usage,expected", [
    (NS(prompt_token_count=12,candidates_token_count=5), "input=12 output=5"),
    (None, "input=N/A output=N/A"),
    (NS(prompt_token_count=0,candidates_token_count=0), "input=0 output=0"),
])
def test_api_usage_is_displayed_without_inventing_missing_values(monkeypatch,capsys,usage,expected):
    calls = []
    def generate_content(**kwargs):
        calls.append(kwargs)
        return NS(text="テスト回答",usage_metadata=usage)
    monkeypatch.setattr(ask,"get_api_key",lambda:"offline-test-key")
    monkeypatch.setattr(ask.genai,"Client",lambda **kwargs:NS(models=NS(generate_content=generate_content)))
    assert ask.ask("質問") == "テスト回答"
    assert expected in capsys.readouterr().out
    assert calls == [dict(model=ask.MODEL,contents="質問")]
