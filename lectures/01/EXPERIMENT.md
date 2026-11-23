# Day 1: 基礎・発展の実験手順

## 現在の状態

実測完了。2026-10-26 16:58:03〜16:58:46 JSTにDeepSeekの2モデル×3質問×3反復、計18回を実行し、全件正常終了しました。結果は `results/20261026T075803140900Z/`、分析は `answer.md` に保存しています。30件のオフラインテストとは区別します。Omnicampus提出済みのImplementation版は `day1-submitted-implementation` に保存し、フォームは変更していません。

## 比較するもの

| 項目 | 設計 |
|---|---|
| モデル | 一覧取得で確認した `deepseek-flash`、`deepseek-v4-pro` |
| 質問 | LoRA の知識説明、2期間の計算、講座固有情報の3種類 |
| 反復 | 各モデル・各質問を3回。計18リクエスト |
| 順序 | 各反復内で順序をシャッフル。乱数 seed を保存 |
| 出力設定 | 共通の上限2048 Token。DeepSeek は両モデルとも thinking を disabled に設定。temperature は既定値 |
| 間隔 | 実測は開始間隔2秒以上・同時実行1。CLI既定値は15秒。再実行時は対象APIの実際の制限に合わせる |
| リトライ | 自動リトライなし。API エラー発生時は保存して停止 |

## 実行

Python 3.12、既存の `uv.lock` を使います。キーは環境変数のみで渡します。
M4 で実行する場合の任意設定は `uv run python scripts/setup_api_key.py`。
本人が非表示入力したキーを、Git の対象外の `.env` に権限0600で保存します。
キーはチャット、GitHub、ログ、スクリーンショットに含めません。

```bash
uv sync --frozen --python 3.12
uv run pytest -q
# .env を使わず環境変数が設定済みの場合は --env-file .env を省略
uv run --env-file .env python -m app.benchmark --provider deepseek --list-models
# 新たな生成費用が発生する。既存結果を読むだけなら実行不要
uv run --env-file .env python -m app.benchmark --provider deepseek --models deepseek-flash deepseek-v4-pro --repeats 3 --seed 20261026 --interval 2 --max-output-tokens 2048
```

`--list-models` は利用モデルの一覧取得であり、残高・無料枠・制限の確認とは別です。
DeepSeek の場合は対象アカウントの残高・制限と今回の予算を確認します。Gemini の場合は AI Studio の課金状態と枠を確認します。
モデル名は教材の例をそのまま仮定せず、そのアカウントで利用可能な名前を使います。

実験は毎回新しい `lectures/01/results/<UTC時刻>/` に保存します。
同じ出力先は上書きしません。失敗後の再実行も別の実験として残します。

| 保存物 | 意味 |
|---|---|
| `manifest.json` | 実行計画、順序、設定、開始・終了時刻、コード指紋、実行状態 |
| `attempts.jsonl` | 1リクエストごとの完全な回答、Token、応答時間、失敗。各行を即時保存 |
| `results.csv` | 数量比較用。欠測値は空欄 |
| `summary.json` | 完了数・失敗数と正常終了分の中央値。欠測の観測数も保存 |
| `results.md` | 一覧表と回答原文。基礎課題の回答差異の確認に使用 |
| `review.json` | Codexによる原文確認と、空白・改行を含む文字数制約の判定 |
| `cost_estimate.json` | usageと公式料金表による推計。請求書による確定値ではない |
| `budget.json` | 実行時に用いた予算上限と保守的な予約額の記録 |
| `comparison.png` / `.svg` | 3実測点、中央値、範囲の図 |

図の再生成は `python scripts/plot_day1.py`。Matplotlibが必要ですがAPI呼び出しはありません（作成環境Matplotlib 3.10.8）。実測時は既存設定からキーをメモリ内だけで読み、18回・USD 0.25を上限とするローカルランナーを利用しました。上の一般コマンドには金額による停止機能はなく、18回の実行計画になります。対象アカウントの認証・予算管理は別途必要です。ローカルの認証設定パスやキーをリポジトリに公開しません。

## 結果の読み方と限界

- 時間は API 呼び出し開始から完全な応答受信まで。ネットワーク、待ち行列、生成を含み、純粋な推論時間や最初の Token までの時間ではありません。
- Token は API の usage_metadata を使います。入力・出力・思考・キャッシュ・合計を区別し、未取得値を0で埋めません。合計が入力＋可視出力と一致するとは限りません。
- `MAX_TOKENS` の回答は打ち切り、テキストがない回答は空応答として区別します。失敗を速い正常応答として集計しません。
- 出力の長さ、思考 Token、プロバイダ既定設定が異なるため、応答時間の差だけでモデルの計算効率や品質の優劣を断定しません。
- 各条件3回は記述的な比較です。統計的な優越性、一般的な速度、再現される順位は主張しません。
- 課題ごとの正確性・回答差異は `questions.json` の基準で原文を読み、別に記録します。基準と正解は API に渡しません。
- 講座固有情報が正しく出ても、資料を学習・記憶している証拠とは断定しません。確認不能との回答も評価対象です。
- 429 が起きなければ「制限なし」とは結論しません。DeepSeekの同時接続制限とGemini無料枠のRPM・TPM・RPDを区別します。今回Gemini無料枠や本人のAI Studio上限の実測確認はしていません。意図的な枠の使い切りは行いません。

## AI の利用と提出

設計・コード作成・オフライン検証・文章整理は Codex が補助します。
本人の理解・確認と AI の実行は区別します。実際のAPI結果を取得して `answer.md` を更新しました。
自分の公開 Fork の `lec01` から同じ Fork の `main` に PR を作成します。
Omnicampus の Q2 には公開リポジトリの URL を記入します。

## DeepSeek の使用条件

講座 README は他モデルや自前契約 API の利用を認めています。DeepSeek では `--provider deepseek` と `DEEPSEEK_API_KEY` を使用します。Gemini は `--provider gemini` と `GEMINI_API_KEY` で従来通り動作します。既存キーの複製、課金開始やチャージはこのコードでは行いません。

公式仕様確認日：2026-10-26。モデル名は実験前に本人のAPIアカウントで一覧取得して確認しました。DeepSeekの残高・同時実行制限とGeminiの無料枠のレート制限を同一視せず、実際に観察できた範囲だけを報告します。

- https://api-docs.deepseek.com/quick_start/pricing/
- https://api-docs.deepseek.com/api/create-chat-completion/
- https://api-docs.deepseek.com/guides/thinking_mode/
- https://api-docs.deepseek.com/quick_start/rate_limit/
- https://ai.google.dev/gemini-api/docs/rate-limits
