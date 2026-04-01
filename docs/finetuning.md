# fine-tuning 設計ドキュメント
> 作成日: 2026-04-01 / ステータス: Draft v1 / 対象フェーズ: Phase 3

---

## 0. 基本方針

**fine-tuningのデータ源泉はSQLiteの`raw_text`であり、ChromaDBは使わない。**

```
SQLite (yuuka.db)
  └─ raw_text          ← fine-tuning の素材
  └─ topics / mood     ← 品質フィルタに使う

ChromaDB (chroma_db/)
  └─ key チャンク      ← RAG・検索専用
  └─ sentence_group    ← RAG・検索専用
```

Embeddingパイプライン（`embedder.py`）はRAG用であり、
fine-tuning用データ整形は**別スクリプト**として独立させる。

---

## 1. fine-tuningで達成したいこと

| 目標 | 説明 |
|------|------|
| 文体の再現 | 自分の話し言葉・語尾・テンポを学習させる |
| 思考パターンの再現 | 課題 → 考察 → 結論の構造を学習させる |
| 自分文脈での応答 | RAGなしでも「自分らしい回答」が返ってくる状態 |

---

## 2. fine-tuning用データセット設計

### 2-1. フォーマット（OpenAI形式 / JSONL）

```jsonl
{"messages": [{"role": "user", "content": "今日どうだった？"}, {"role": "assistant", "content": "今日は午前中にDX推進の振り返りをしていた。..."}]}
{"messages": [{"role": "user", "content": "最近何を考えてる？"}, {"role": "assistant", "content": "AIを使った業務最適化に関心があって..."}]}
```

`assistant`側に自分の日記テキストを入れることで文体・思考パターンを学習させる。

### 2-2. データ品質基準

fine-tuningに使うエントリの条件：

| 条件 | 理由 |
|------|------|
| `raw_text`が200文字以上 | 短すぎるエントリは文体学習に不向き |
| `key_sentences`が存在する | 思考の核心が抽出できているエントリのみ |
| `energy`が`mid`または`high` | 低エネルギー日は思考が浅い傾向がある |
| （将来）`status = reviewed` | 手動でレビュー済みのエントリのみ（精度最優先時） |

### 2-3. promptの設計方針

`user`側のpromptをどう作るかで学習の方向性が変わる。

**Option A: 日付ベース（シンプル）**
```
user: 2026年1月1日の日記を教えて
assistant: {raw_text}
```

**Option B: topicsベース（推奨）**
```
user: {topics[0]}について話して
assistant: {raw_text}
```
→ topicsが既にClaudeで抽出されているため、そのまま活用できる。

**Option C: key_sentencesをtriggerに（高精度向け）**
```
user: 「{key_sentences[0]}」と思ったのはなぜ？
assistant: {raw_text}
```
→ 思考の深掘りに強いモデルになる。

Phase 3では**Option B + Cのミックス**を試す。

---

## 3. エクスポートスクリプト設計（Phase 3で実装）

```
modules/
  └─ ft_exporter.py   ← 将来実装
```

処理フロー：

```
SQLite
  │ 品質フィルタ（文字数・key_sentences有無・energy）
  ▼
対象エントリ抽出
  │ prompt生成（topicsまたはkey_sentencesから）
  ▼
JSONL整形
  │
  ▼
data/ft_dataset_YYYYMMDD.jsonl
```

### スクリプトの基本インターフェース（案）

```bash
python -m modules.ft_exporter \
  --min-chars 200 \
  --prompt-type topics \  # topics | key | date
  --output data/ft_dataset.jsonl
```

---

## 4. fine-tuningモデル候補

| モデル | 用途 | 備考 |
|-------|------|------|
| `gpt-4o-mini` | Phase 3 最初の試行 | OpenAI fine-tuning API、コスト低 |
| `claude` (将来) | Anthropic fine-tuning解禁後 | 現時点では未対応 |
| ローカルLLM (Llama等) | M5 Mac Mini移行後 | MLXでの実行を想定 |

---

## 5. 注意事項

- fine-tuningデータに**他人の個人情報（人名・場所）**が含まれる場合は、  
  `people`フィールドを使ってマスク処理を検討する（`docs/design.md` 8章参照）。
- fine-tuned modelは**上書き・バージョン管理**が必要。  
  データセットのJSONLファイルは日付付きで`data/`に保存する。
- データ量の目安: OpenAI fine-tuningは最低50件から動作するが、  
  文体再現には**200件以上**を推奨。現在のRawVaultは十分な量がある。

---

*このドキュメントはPhase 3着手時に詳細化する。*
