"""Offline structural tests. These are never submitted as measured API results."""

import json
from types import SimpleNamespace as NS

import pytest

from app.benchmark import build_schedule, load_questions, measure_once, run_benchmark, summarize


def response(text="回答", **usage):
    return NS(text=text, usage_metadata=NS(**usage), model_version="model-version",
              candidates=[NS(finish_reason=NS(value="STOP"))])


class Client:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []
        self.models = self

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        result = next(self.responses)
        if isinstance(result, Exception):
            raise result
        return result


QUESTION = {"id": "example", "prompt": "公開テスト用の質問"}


def test_each_combination_repeated_without_sending_review_criteria():
    questions = [QUESTION, dict(id="other", prompt="別の質問", review_criteria="秘密の正解")]
    schedule = build_schedule(["a", "b"], questions, 3, 5)
    assert len(schedule) == 12
    assert schedule == build_schedule(["a", "b"], questions, 3, 5)
    for model in ["a", "b"]:
        for question in questions:
            assert sum(m == model and q["id"] == question["id"] for _,m,q in schedule) == 3
    client = Client([response()])
    measure_once(client, model="a", question=questions[1], repeat=1, sequence=1, max_output_tokens=123)
    assert client.calls[0]["contents"] == "別の質問"
    assert "秘密の正解" not in str(client.calls)
    assert client.calls[0]["config"].max_output_tokens == 123


def test_elapsed_and_actual_usage_preserve_missing_values():
    ticks = iter([2.0, 3.25])
    row = measure_once(Client([response(prompt_token_count=12, candidates_token_count=4,
                                        thoughts_token_count=8, total_token_count=24)]),
                       model="a", question=QUESTION, repeat=1, sequence=1,
                       max_output_tokens=50, clock=lambda: next(ticks))
    assert row["elapsed_seconds"] == 1.25
    assert row["prompt_token_count"] == 12
    assert row["candidates_token_count"] == 4
    assert row["thoughts_token_count"] == 8
    assert row["cached_content_token_count"] is None
    assert row["total_token_count"] == 24
    assert row["status"] == "ok"


@pytest.mark.parametrize("text,reason,expected", [(None,"STOP","empty_response"),
                                                  ("途中","MAX_TOKENS","truncated")])
def test_empty_and_truncated_are_not_success(text, reason, expected):
    obj = response(text)
    obj.candidates[0].finish_reason.value = reason
    row = measure_once(Client([obj]), model="a", question=QUESTION, repeat=1,
                       sequence=1, max_output_tokens=50)
    assert row["status"] == expected
    summary = summarize([row])[0]
    assert summary["completed"] == 0
    assert summary["elapsed_seconds_median"] is None


def test_error_redacted_recorded_and_no_hidden_retry(tmp_path):
    secret = "AIza" + "x" * 35
    exc = RuntimeError("quota exhausted; key=" + secret)
    exc.code = 429
    client = Client([exc, response()])
    out = tmp_path / "run"
    rows = run_benchmark(client, models=["a"], questions=[QUESTION], repeats=3, seed=1,
                         output=out, interval=0, max_output_tokens=100, secret=secret)
    assert len(client.calls) == len(rows) == 1
    assert rows[0]["http_status"] == 429
    assert summarize(rows)[0]["rate_limited"] == 1
    for path in out.iterdir():
        assert secret not in path.read_text()
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["state"] == "stopped"
    assert manifest["planned_calls"] == 3
    assert manifest["completed_calls"] == 1
    with pytest.raises(FileExistsError):
        run_benchmark(client, models=["a"], questions=[QUESTION], repeats=1, seed=1,
                      output=out, interval=0, max_output_tokens=100)


def test_durable_outputs_and_success_statistics(tmp_path):
    out = tmp_path / "run"
    rows = run_benchmark(Client([response(prompt_token_count=10), response(prompt_token_count=20)]),
                         models=["a"], questions=[QUESTION], repeats=2, seed=1,
                         output=out, interval=0, max_output_tokens=100)
    assert len((out / "attempts.jsonl").read_text().splitlines()) == 2
    assert len((out / "results.csv").read_text().splitlines()) == 3
    assert json.loads((out / "manifest.json").read_text())["state"] == "complete"
    summary = summarize(rows)[0]
    assert summary["prompt_token_count_median"] == 15
    assert summary["candidates_token_count_median"] is None
    assert "N/A" in (out / "results.md").read_text()


def test_interval_measures_between_starts(tmp_path):
    ticks = iter([0,0,0, 0,15,15,15])
    sleeps = []
    run_benchmark(Client([response(),response()]), models=["a"], questions=[QUESTION],
                  repeats=2, seed=1, output=tmp_path / "run", interval=15,
                  max_output_tokens=100, clock=lambda:next(ticks), sleep=sleeps.append)
    assert sleeps == [15]


def test_questions_reject_duplicate_ids(tmp_path):
    path = tmp_path / "questions.json"
    path.write_text(json.dumps([QUESTION, QUESTION]))
    with pytest.raises(ValueError, match="unique"):
        load_questions(path)


def test_interrupt_preserves_finished_attempt(tmp_path):
    class InterruptedClient(Client):
        def generate_content(self, **kwargs):
            if self.calls:
                raise KeyboardInterrupt()
            return super().generate_content(**kwargs)
    out = tmp_path / "run"
    with pytest.raises(KeyboardInterrupt):
        run_benchmark(InterruptedClient([response()]), models=["a"], questions=[QUESTION],
                      repeats=3, seed=1, output=out, interval=0, max_output_tokens=100)
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["state"] == "stopped"
    assert manifest["completed_calls"] == 1
    assert manifest["stop_reason"] == "KeyboardInterrupt"
    assert len((out / "attempts.jsonl").read_text().splitlines()) == 1
