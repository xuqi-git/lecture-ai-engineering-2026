"""第1回: 単発の質問、または会話履歴を保持する対話スクリプト。

使い方:
    uv run python -m app.ask "LoRAとは何ですか？"
    uv run python -m app.ask            # 質問を省略すると、講座に固有の質問をする

--chat を付けると会話履歴を保持。省略時は単発の呼び出し。
講座に固有のことを聞くと、「分からない」と答えるか、一般論でもっともらしく答える
（講座の実際とは違う）ことを確かめよう。
（第3回で、用語集を検索できるエージェントにして改善する）
"""

import argparse
import os

from app.deepseek_api import DeepSeekClient, DeepSeekAPIError

from google import genai
from google.genai import errors

from app.config import MODEL, api_error_message, get_api_key

# 講座に固有の質問。正しい答えは data/glossary.json の homework-levels にある
DEFAULT_QUESTION = "AIE2026の講座の宿題にある「3レベル」とは何ですか？"


def ask(question: str, *, history=None, provider="gemini", model=None) -> str:
    if provider == "deepseek":
        value = os.environ.get("DEEPSEEK_API_KEY")
        if not value:
            raise SystemExit("DEEPSEEK_API_KEY is missing")
        client = DeepSeekClient(value)
        selected_model = model or "deepseek-flash"
    else:
        client = genai.Client(api_key=get_api_key())
        selected_model = model or MODEL
    contents = question if history is None else [*history, {"role": "user", "parts": [{"text": question}]}]
    kwargs = dict(model=selected_model, contents=contents)
    if provider == "deepseek":
        from google.genai import types
        kwargs["config"] = types.GenerateContentConfig(max_output_tokens=2048)
    response = client.models.generate_content(**kwargs)

    usage = response.usage_metadata
    input_tokens = getattr(usage, "prompt_token_count", None)
    output_tokens = getattr(usage, "candidates_token_count", None)
    print(f"[tokens] input={input_tokens if input_tokens is not None else 'N/A'} "
          f"output={output_tokens if output_tokens is not None else 'N/A'}")

    answer = response.text or ""
    if history is not None and answer.strip():
        history.extend([{ "role": "user", "parts": [{"text": question}]},
                        { "role": "model", "parts": [{"text": answer}]}])
    return answer


def main() -> None:
    parser = argparse.ArgumentParser(description="素のLLMに質問する")
    parser.add_argument("question", nargs="?", default=DEFAULT_QUESTION)
    parser.add_argument("--chat", action="store_true", help="Keep conversation history for follow-up questions")
    parser.add_argument("--provider", choices=["gemini", "deepseek"], default="gemini")
    parser.add_argument("--model")
    args = parser.parse_args()

    print(f"[model] {args.model or ('deepseek-flash' if args.provider == 'deepseek' else MODEL)}")
    print(f"[質問] {args.question}\n")
    try:
        history = [] if args.chat else None
        question = args.question
        while True:
            print(ask(question, history=history, provider=args.provider, model=args.model))
            if not args.chat:
                break
            try:
                question = input("\n[次の質問 /exit で終了] ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if question in ("/exit", "/quit"):
                break
            if not question:
                break
    except (errors.APIError, DeepSeekAPIError) as e:
        print(api_error_message(e.code, getattr(e, "message", str(e))))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
