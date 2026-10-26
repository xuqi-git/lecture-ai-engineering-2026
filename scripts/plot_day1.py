"""Recreate the figure from saved measurements; no API calls."""
import json
from pathlib import Path
from statistics import median

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "lectures/01/results/20261026T075803140900Z"
rows = [json.loads(line) for line in (RUN / "attempts.jsonl").read_text().splitlines()]
models = ["deepseek-flash", "deepseek-v4-pro"]
questions = ["lora", "budget", "course"]
colors = ["#087e8b", "#d56335"]
fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), layout="constrained")
for ax, metric, title, ylabel in zip(
    axes,
    ["elapsed_seconds", "candidates_token_count"],
    ["Request to full response", "Reported output tokens"],
    ["Seconds (network included)", "Output tokens"],
):
    for j, model in enumerate(models):
        for i, question in enumerate(questions):
            values = [r[metric] for r in rows if r["model"] == model and r["question_id"] == question and r["status"] == "ok"]
            x = i + (-0.17 if j == 0 else 0.17)
            ax.vlines(x, min(values), max(values), color=colors[j], alpha=0.5, linewidth=2)
            ax.scatter([x - 0.035, x, x + 0.035], values, s=30, color=colors[j], alpha=0.7)
            ax.plot([x - 0.09, x + 0.09], [median(values)] * 2, color=colors[j], linewidth=3,
                    label=model if i == 0 else None)
    ax.set(title=title, ylabel=ylabel, xticks=range(3), xticklabels=["LoRA", "Budget calculation", "Course (no source)"])
    ax.set_ylim(bottom=0)
    ax.grid(axis="y", alpha=0.18)
    ax.spines[["top", "right"]].set_visible(False)
axes[0].legend(frameon=False, loc="upper left")
fig.suptitle("Day 1: two DeepSeek models, three prompts, three repeats", fontsize=14)
fig.supxlabel("Dots: individual requests | Bar: median | Line: observed range | thinking disabled | 18/18 successful", fontsize=9)
for extension in ["png", "svg"]:
    fig.savefig(RUN / f"comparison.{extension}", dpi=180)
