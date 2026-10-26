"""Day 1: reproducible latency/token comparison; real API only, no simulated results.

Run ``uv run python -m app.benchmark --help`` for usage. API keys come only
from GEMINI_API_KEY. SDK retries are disabled; every explicit attempt is logged.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import random
import re
import statistics
import subprocess
import time
from datetime import datetime, timezone
from typing import Any

from google import genai
from google.genai import types

from app.config import get_api_key
from app.deepseek_api import DeepSeekClient

TOKEN_FIELDS = (
    "prompt_token_count", "candidates_token_count", "thoughts_token_count",
    "cached_content_token_count", "total_token_count",
)
CSV_FIELDS = (
    "sequence", "repeat", "model", "model_version", "question_id", "started_at",
    "elapsed_seconds", "status", "http_status", "finish_reasons", "answer_chars",
    *TOKEN_FIELDS, "error",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def redact(text: str, secret: str = "") -> str:
    if secret:
        text = text.replace(secret, "[REDACTED]")
    return re.sub(r"AIza[0-9A-Za-z_-]{20,}", "[REDACTED]", text)


def load_questions(path: Path) -> list[dict[str, Any]]:
    questions = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(questions, list) or not questions:
        raise ValueError("Questions must be a nonempty JSON list.")
    ids = []
    for question in questions:
        if not isinstance(question, dict):
            raise ValueError("Each question must be an object.")
        for field in ("id", "prompt"):
            if not isinstance(question.get(field), str) or not question[field].strip():
                raise ValueError(f"Each question requires nonempty {field}.")
        ids.append(question["id"])
    if len(set(ids)) != len(ids):
        raise ValueError("Question IDs must be unique.")
    return questions


def build_schedule(models: list[str], questions: list[dict[str, Any]],
                   repeats: int, seed: int) -> list[tuple[int, str, dict[str, Any]]]:
    """Shuffle within each repeat to distribute order/time effects."""
    if repeats < 1 or not models or len(set(models)) != len(models):
        raise ValueError("Use positive repeats and distinct model names.")
    rng = random.Random(seed)
    schedule = []
    for repeat in range(1, repeats + 1):
        block = [(repeat, model, q) for model in models for q in questions]
        rng.shuffle(block)
        schedule.extend(block)
    return schedule


def measure_once(client: Any, *, model: str, question: dict[str, Any],
                 repeat: int, sequence: int, max_output_tokens: int,
                 secret: str = "", clock=time.perf_counter) -> dict[str, Any]:
    record = dict.fromkeys(CSV_FIELDS)
    record.update(sequence=sequence, repeat=repeat, model=model,
                  question_id=question["id"], prompt=question["prompt"],
                  started_at=utc_now(), status="error", answer="", error="")
    start = clock()
    try:
        response = client.models.generate_content(
            model=model, contents=question["prompt"],
            config=types.GenerateContentConfig(max_output_tokens=max_output_tokens),
        )
    except Exception as exc:
        # Include failed latency; never leak a key through exception text.
        record["elapsed_seconds"] = round(clock() - start, 6)
        record["http_status"] = getattr(exc, "code", None)
        record["error"] = redact(f"{type(exc).__name__}: {exc}", secret)
        return record
    record["elapsed_seconds"] = round(clock() - start, 6)
    record["model_version"] = getattr(response, "model_version", None)
    usage = getattr(response, "usage_metadata", None)
    for field in TOKEN_FIELDS:
        record[field] = getattr(usage, field, None) if usage else None
    reasons = []
    for candidate in getattr(response, "candidates", None) or []:
        reason = getattr(candidate, "finish_reason", None)
        reasons.append(str(getattr(reason, "value", reason)))
    record["finish_reasons"] = ",".join(reasons)
    record["answer"] = redact(getattr(response, "text", None) or "", secret)
    record["answer_chars"] = len(record["answer"])
    if not record["answer"].strip():
        record["status"] = "empty_response"
    elif "MAX_TOKENS" in reasons:
        record["status"] = "truncated"
    else:
        record["status"] = "ok"
    return record


def summarize(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Failures/truncation are counted, never treated as successful fast answers."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for record in records:
        groups.setdefault((record["model"], record["question_id"]), []).append(record)
    result = []
    for (model, question_id), rows in sorted(groups.items()):
        good = [row for row in rows if row["status"] == "ok"]
        item = dict(model=model, question_id=question_id, attempts=len(rows),
                    completed=len(good), errors=sum(r["status"] == "error" for r in rows),
                    rate_limited=sum(r.get("http_status") == 429 for r in rows),
                    truncated=sum(r["status"] == "truncated" for r in rows),
                    empty=sum(r["status"] == "empty_response" for r in rows))
        for field in ("elapsed_seconds", *TOKEN_FIELDS):
            values = [r[field] for r in good if isinstance(r.get(field), (int, float))]
            item[f"{field}_n"] = len(values)
            item[f"{field}_median"] = statistics.median(values) if values else None
            if field == "elapsed_seconds":
                item["elapsed_seconds_min"] = min(values) if values else None
                item["elapsed_seconds_max"] = max(values) if values else None
        result.append(item)
    return result


def atomic_json(path: Path, data: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def write_outputs(output: Path, records: list[dict[str, Any]]) -> None:
    with (output / "results.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    summary = summarize(records)
    atomic_json(output / "summary.json", summary)
    lines = ["# Day 1 実測結果", "", "このファイルは実際の API 応答から生成。",
             "", "| モデル | 質問 | 完了 / 試行 | 応答時間中央値（秒） | 入力 Token 中央値 | 出力 Token 中央値 |",
             "|---|---|---:|---:|---:|---:|"]
    def fmt(value: Any) -> str:
        return "N/A" if value is None else f"{value:.3f}" if isinstance(value, float) else str(value)
    for row in summary:
        lines.append(f"| {row['model']} | {row['question_id']} | {row['completed']} / {row['attempts']} | "
                     f"{fmt(row['elapsed_seconds_median'])} | {fmt(row['prompt_token_count_median'])} | "
                     f"{fmt(row['candidates_token_count_median'])} |")
    lines += ["", "## 回答の原文（基礎課題の比較用）", ""]
    for row in records:
        lines += [f"### {row['sequence']}. {row['model']} / {row['question_id']} / repeat {row['repeat']}",
                  "", f"状態: `{row['status']}` / {row['elapsed_seconds']} 秒", "",
                  row["answer"] or row["error"] or "テキストなし", ""]
    (output / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_benchmark(client: Any, *, models: list[str], questions: list[dict[str, Any]],
                  repeats: int, seed: int, output: Path, interval: float,
                  max_output_tokens: int, secret: str = "", clock=time.perf_counter,
                  sleep=time.sleep, metadata: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    if interval < 0 or max_output_tokens < 1:
        raise ValueError("Invalid interval or output limit.")
    schedule = build_schedule(models, questions, repeats, seed)
    output.mkdir(parents=True, exist_ok=False)  # Never overwrite an earlier experiment.
    manifest = dict(metadata or {}, started_at=utc_now(), state="running", models=models,
                    repeats=repeats, seed=seed, interval_seconds=interval,
                    max_output_tokens=max_output_tokens, temperature="provider default",
                    sdk_max_attempts=1, planned_calls=len(schedule), completed_calls=0,
                    measurement="request start to complete response; network included",
                    questions=questions,
                    schedule=[dict(repeat=r, model=m, question_id=q['id']) for r,m,q in schedule])
    atomic_json(output / "manifest.json", manifest)
    records = []
    previous_start = None
    log = output / "attempts.jsonl"
    stop_reason = None
    try:
        for sequence, (repeat, model, question) in enumerate(schedule, 1):
            if previous_start is not None:
                remaining = interval - (clock() - previous_start)
                if remaining > 0:
                    sleep(remaining)
            previous_start = clock()
            record = measure_once(client, model=model, question=question, repeat=repeat,
                                  sequence=sequence, max_output_tokens=max_output_tokens,
                                  secret=secret, clock=clock)
            with log.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            records.append(record)
            write_outputs(output, records)
            print(f"[{sequence}/{len(schedule)}] {model} {question['id']}: "
                  f"{record['status']} {record['elapsed_seconds']}s", flush=True)
            manifest["completed_calls"] = len(records)
            atomic_json(output / "manifest.json", manifest)
            if record["status"] == "error":
                # Pause on quota/auth/model/server failure. Explicit later runs can
                # investigate it; no hidden retries or repeated quota consumption.
                stop_reason = f"request_error_http_{record['http_status']}"
                break
    except BaseException as exc:
        stop_reason = type(exc).__name__
        raise
    finally:
        manifest.update(finished_at=utc_now(), completed_calls=len(records),
                        state="complete" if len(records) == len(schedule) and not stop_reason else "stopped",
                        stop_reason=stop_reason)
        atomic_json(output / "manifest.json", manifest)
        write_outputs(output, records)
    return records


def provenance() -> dict[str, Any]:
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                                text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    files = [Path(__file__), Path("lectures/01/questions.json")]
    return dict(python=platform.python_version(),
                google_genai=importlib.metadata.version("google-genai"), git_commit=commit,
                source_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in files if p.is_file()})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=["deepseek", "gemini"], default="deepseek")
    parser.add_argument("--models", nargs="+")
    parser.add_argument("--questions", type=Path, default=Path("lectures/01/questions.json"))
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20261026)
    parser.add_argument("--interval", type=float, default=15.0,
                        help="Minimum seconds between request starts; check your actual quota.")
    parser.add_argument("--max-output-tokens", type=int, default=2048)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--list-models", action="store_true")
    args = parser.parse_args()
    if not args.list_models and not args.models:
        parser.error("Pass --models with names verified in your own API project.")
    questions = load_questions(args.questions)
    if not args.list_models:
        build_schedule(args.models, questions, args.repeats, args.seed)
        if args.interval < 0 or args.max_output_tokens < 1:
            parser.error("Use a nonnegative interval and positive output limit.")
    if args.provider == "deepseek":
        key = os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            raise SystemExit("DEEPSEEK_API_KEY is missing. Set it locally; never paste it in chat or Git.")
        client_context = DeepSeekClient(key)
    else:
        key = get_api_key()
        client_context = genai.Client(api_key=key, http_options=types.HttpOptions(
            timeout=90000, retry_options=types.HttpRetryOptions(attempts=1),
        ))
    with client_context as client:
        if args.list_models:
            for model in client.models.list():
                actions = getattr(model, "supported_actions", None) or []
                if "generateContent" in actions:
                    print(model.name)
            return
        output = args.output or Path("lectures/01/results") / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        metadata = provenance()
        metadata.update(provider=args.provider,
                        thinking="disabled" if args.provider == "deepseek" else "provider default")
        records = run_benchmark(client, models=args.models, questions=questions,
                                repeats=args.repeats, seed=args.seed, output=output,
                                interval=args.interval, max_output_tokens=args.max_output_tokens,
                                secret=key, metadata=metadata)
    print(f"Saved: {output}")
    if any(row["status"] != "ok" for row in records):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
