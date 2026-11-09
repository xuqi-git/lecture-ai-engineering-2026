# 第3回 解答

## 演習

- 第1回（素のLLM）とエージェントの回答の違い：
  - 同じ質問「AIE2026の講座の宿題にある「3レベル」とは何ですか？」を `app.ask`（素の LLM、gemini-3.5-flash-lite）に投げると、講座を知らないため「講座のテーマによって異なる」と前置きし、「レベル1 基礎・入門／レベル2 応用／レベル3 発展・創造」「AI活用の3段階」など一般論を2通り並べ、最後に「テーマを教えてほしい」と聞き返した。もっともらしいが、この講座の定義ではない。
  - `app.agent` は `search_glossary("3レベル")` で用語集を引いてから、「基礎（講義内容の確認）・実装（自分でコードを書く）・発展（調査や試行）、どれか1つで完了」と用語集どおりに答え、最後に（第1回）を付けた。
- `--trace` で見えたツール呼び出し（ツール名と引数）：
  - 「3レベル」：`search_glossary({'query': '3レベル'})` の1回。
  - 「LoRA とQLoRAの違いは？」：`search_glossary({'query': 'LoRA'})` と `search_glossary({'query': 'QLoRA'})` の2回。1回の応答でまとめて（並列に）呼ばれていた。docstring の「query には調べたい用語を1つだけ入れる」に従って用語ごとに分けている。
  - 「第2回の内容から確認問題を 1問出して」：`make_quiz({'lecture': 2})` の1回。
- 1つの質問での LLM 呼び出し回数（`requests`）：
  - 3問とも `requests=2`（ツール呼び出しを書く1回＋ツール結果を読んで回答する1回）。LoRA/QLoRA はツールを2回呼んだが、2つの呼び出しが同じ応答に入っていたので requests は2のまま（tool_calls=2）。
  - 入力トークンは 1,000〜1,430、費用表示は 1問あたり約 0.0004〜0.0009 ドル。
- 追加したツールと、docstring に書いた説明：
  - `make_quiz(lecture: int) -> str`：用語集から `lecture` が一致する用語を集めて `random.choice` で1つ選び、`{"question": "「用語」の意味は？", "answer": 定義, "lecture": 回}` を JSON 文字列で返す。用語が無い回（例：0）はエラーにせず「その回の用語は用語集にありません。用語がある回: 1, 2, 3, 5」と返す。
  - docstring：「指定した回（1始まりの整数）の用語から1つを選び、確認問題とその答えを返す。『第2回の確認問題を出して』『復習用の問題がほしい』のように、特定の回の復習問題を求められたときに使う。答えは用語集の定義そのもの。」
  - `app/agent.py` で `agent.tool_plain(tools.make_quiz)` として登録し、INSTRUCTIONS に「確認問題や復習問題を求められたら make_quiz を使う。」を1行足した。
  - `--list-tools` に make_quiz と docstring が表示され、`pytest -q` は 11 passed。
  - 気づき：make_quiz は答えも返しているが、エージェントは問題だけを出し、答えは書かなかった。INSTRUCTIONS の「宿題の答えそのものは書かず、考え方のヒントで導く」を、確認問題にも当てはめたように見える（推測）。

## 宿題

- 取り組んだレベル：発展（a）ADK で作り直す
- やったこと：
  - `adk_agent/glossary_agent/agent.py` と `__init__.py`（`from . import agent` の1行）を作った。`INSTRUCTIONS` は `app.agent` から、ツールは `app.tools` の `search_glossary`・`get_lecture_summary`・`make_quiz` をそのまま import し、`google.adk.agents.Agent(model="gemini-3.5-flash-lite", name="glossary_agent", instruction=INSTRUCTIONS, tools=[...])` で組み立てた。`app/` のファイルは変えていない。
  - `PYTHONPATH=. uv run --with google-adk adk run adk_agent/glossary_agent` で、演習と同じ3つの質問を1問ずつ新しいセッションで聞いた。
  - ADK の `adk run` には `--trace` が無いので、ツール呼び出しは ADK がセッションを保存する `adk_agent/glossary_agent/.adk/session.db`（SQLite）の events から読み出し、LLM の呼び出し回数は ADK のログ（`Sending out request` の行数）で数えた。ログは `lectures/03/logs/` に保存した。
- 結果：

| 質問 | Pydantic AI（演習） | ADK |
|---|---|---|
| 3レベル | `search_glossary('3レベル')`、requests=2、入力 1,017／出力 130 トークン | `search_glossary('3レベル')`、2 リクエスト、入力 510＋633＝1,143／出力 130 |
| LoRA と QLoRA | `search_glossary('LoRA')`・`('QLoRA')` を1回の応答で並列に、requests=2、入力 1,430／出力 187 | 同じ2回を1回の応答で並列に、2 リクエスト、入力 499＋1,055＝1,554／出力 174 |
| 第2回の確認問題 | `make_quiz(lecture=2)`、requests=2、入力 1,000／出力 51 | `make_quiz(lecture=2)`、2 リクエスト、入力 501＋586＝1,087／出力 49 |

  - ツールの選び方・引数・呼ぶ回数・LLM の呼び出し回数は、3問とも同じだった。回答の中身も用語集どおりで、最後に関係する回を付ける点も同じ。確認問題では、どちらも答えを書かずに問題だけを出した（出題された用語は random なので別の用語：Pydantic AI は QLoRA、ADK はランク）。
  - 違い①：入力トークンが ADK のほうが 1 割弱多い（+87〜+126）。同じ INSTRUCTIONS とツールを渡しているので、ADK が自分で足す指示（エージェント名など）やツール定義の書き方の差だと思う（ADK が実際に送った全文までは確かめていない）。
  - 違い②：ツールの戻り値の渡し方。Pydantic AI は関数が返した文字列をそのまま返すが、ADK は `{'result': '…'}` という辞書に包んでモデルに返していた。
- 書き方の違い：
  - Pydantic AI：`Agent(instructions=...)` を作ってから `agent.tool_plain(関数)` でツールを1つずつ登録し、モデルは `run_sync(..., model=...)` の実行時に渡す（テストでは API を呼ばない `TestModel` に差し替えられる）。ループ・ツール実行・ツール呼び出しの記録（`result.all_messages()`、`usage`）を自分のコードで表示する。
  - ADK：`Agent(model=..., name=..., instruction=..., tools=[関数のリスト])` にまとめて書き、モデルは定義のときに文字列で決める。`root_agent` という名前で置くと `adk run` が見つけて、対話の画面（REPL）・セッションの保存（SQLite）・ログを用意してくれる。代わりに、`--trace` のような呼び出しの表示は自分で作らないと見えない。
  - どちらも、関数名・型ヒント・docstring がそのまま「ツールの説明」になる点は同じ。
- 気づき・疑問：
  - 第3回の講義の「エージェント＝モデル＋ハーネス」を、モデル・指示・ツールを固定してハーネス（フレームワーク）だけを変えて確かめた形になった。この小さな課題では、ツールの使い方も回答もほとんど変わらず、差は入力トークン（費用）と、見えるもの（trace の取りやすさ、セッションの保存）に出た。講義の「同じモデルでもハーネスで費用と速さが変わる」の小さい版だと思う。
  - 疑問：入力トークンの差の中身（ADK が何を足しているか）を確かめるには、ADK が送ったリクエストの全文を見る必要がある。ADK の callback で見られるか、次に試したい。
  - 1回ずつしか実行していないので、回答の細かい違いは毎回の揺れの範囲かもしれない。比べるなら同じ質問を複数回ずつ実行する必要がある。
  - 実行と記録には AI アシスタント（Claude）を使った。数値はすべて `lectures/03/logs/` のログから取った。
