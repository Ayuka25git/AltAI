# 自分AI 設計ドキュメント
> 作成日: 2026-03-29 / ステータス: Draft v1

---

## 0. コンセプト

**目的**: Obsidianに蓄積した日記・思考ログを、検索・学習・RAGに使える自分専用AIデータベースとして構築する。

**3つの用途**:
1. **思考検索** — 「あのときどう考えたか」を自然言語で引き出す
2. **RAG知識ベース** — AI会話時に自分のコンテキストを注入する
3. **文体・思考パターン学習** — 将来的なfine-tuning用データソース

**基本方針**:
- 既存のRawデータ（2025/12/02〜）は一切書き換えない
- 構造化はスクリプト側で行い、Obsidianでの記述負荷はゼロに近づける
- M1 Macで開発・検証 → M5 Mac Mini（購入後）に本番移行

---

## 1. 全体アーキテクチャ

```
┌─────────────────────────────────────────────────────┐
│  Layer 1: Raw Vault（Obsidian）                      │
│  - 日付ファイル: YYYYMMDD.md                         │
│  - プレーンテキスト形式（既存）                       │
│  - 新規ノート: frontmatter追加（任意）               │
└──────────────────────┬──────────────────────────────┘
                       │ Python バッチスクリプト（週1〜日次）
                       ▼
┌─────────────────────────────────────────────────────┐
│  Layer 2: Structured DB（SQLite → PostgreSQL）       │
│  - raw_textを保存                                    │
│  - LLM自動タグ付け（Claude API）                    │
│  - メタデータ管理                                    │
└──────────────────────┬──────────────────────────────┘
                       │ Embedding処理
                       ▼
┌─────────────────────────────────────────────────────┐
│  Layer 3: Vector Store（ChromaDB → pgvector）        │
│  - 3種のチャンク（後述）                             │
│  - メタデータフィルタ対応                            │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
              自分AI（RAG + 検索 + 学習）
```

---


## 3. Layer 2：構造化DB 設計

### 3-1. フェーズ別DB

| フェーズ | DB | 理由 |
|---------|-----|------|
| Phase 1（M1 Mac） | SQLite | ゼロ設定で即起動、ローカル完結 |
| Phase 2（M5 Mac Mini） | PostgreSQL + pgvector | ベクトル検索を内包、本番運用 |

### 3-2. テーブル定義

```sql
CREATE TABLE journal_entries (
    id              SERIAL PRIMARY KEY,
    date            DATE NOT NULL,
    filename        TEXT,
    raw_text        TEXT,           -- 原文そのまま

    -- LLMが自動生成するフィールド（Claude API）
    topics          TEXT[],         -- ['登山', '食', '都市vs自然']
    mood            TEXT,           -- 'reflective' / 'good' など
    energy          TEXT,           -- 'high' / 'mid' / 'low'
    locations       TEXT[],         -- ['市ケ原', '再度公園', '神戸']
    people          TEXT[],         -- ['人']
    decisions       TEXT[],         -- ['節約する', 'M5待つ']
    key_sentences   TEXT[],         -- 思考の核心文（最大3文）

    -- フラグ
    has_frontmatter BOOLEAN DEFAULT false,
    processed_at    TIMESTAMP,
    created_at      TIMESTAMP DEFAULT NOW()
);

-- 検索用インデックス
CREATE INDEX idx_date ON journal_entries(date);
CREATE INDEX idx_topics ON journal_entries USING GIN(topics);
```

### 3-3. LLM自動タグ付けプロンプト

```
以下の日記エントリを分析し、JSONのみで返してください（前置き・コードブロック不要）。

{raw_text}

出力フォーマット:
{
  "topics": ["テーマ1", "テーマ2"],      // 3〜5個
  "mood": "感情トーン",                   // 1語で
  "energy": "high|mid|low",
  "locations": ["場所1"],                 // 登場した場所
  "people": ["人物1"],                    // 登場した人物（いなければ[]）
  "decisions": ["決断・意図"],            // 何か決めたなら。なければ[]
  "key_sentences": ["文1", "文2"]         // 思考の核心を表す原文（最大3文）
}
```

---

## 4. Layer 3：Vector Store 設計

### 4-1. チャンク戦略

| チャンク種別 | 内容 | 用途 |
|------------|------|------|
| `key` | key_sentences（核心文、最大3文を結合） | 思考検索（精度重視） |
| `sentence_group` | 3文スライディングウィンドウ（overlap 1文） | 文脈付きRAG・汎用検索 |

**fine-tuningデータはChromaDBではなくSQLiteのraw_textが源泉。**  
Phase 3で別途エクスポートスクリプトを用意する（`docs/finetuning.md`参照）。

```python
# key チャンク例
{
    "id": "20260329.md_key",
    "chunk_type": "key",
    "date": "2026-03-29",
    "topics": ["登山", "都市vs自然", "食"],
    "text": "これまでやってきたことを信じて積み重ねていく。"
}

# sentence_group チャンク例（3文 window, 1文 overlap）
{
    "id": "20260329.md_sg_0",
    "chunk_type": "sentence_group",
    "date": "2026-03-29",
    "sentence_start": 0,
    "sentence_end": 2,
    "text": "今日は元旦。3時40分に起きて法多山に向かった。高速を使って1時間半で到着。"
}
```

### 4-2. 会話インターフェースでのRAG設計（2段階RAG）

会話形式でユーザーの質問に答える場合、以下の2段階でチャンクを活用する。

```
ユーザーの質問
    ↓
① sentence_group で検索（文脈ベース）→ 候補チャンクを5〜10件取得
    ↓
② 同日付の key チャンクを補完取得（思考の核心を補う）
    ↓
③ Claude API に投げる
    prompt:
      「以下は自分の日記から抜粋した文章です。
       [sentence_group チャンク]
       [同日の key チャンク（あれば）]
       質問: {ユーザーの質問}
       自分の言葉・文体で答えてください。」
    ↓
回答出力
```

**sentence_groupが主軸、keyが補完**という役割分担にすることで、
文脈の豊かさと思考の核心を両立させる。

実装はPhase 2のRAGインターフェース（FastAPI）で行う（`modules/searcher.py`を拡張）。

---

### 4-3. Embeddingモデル候補

| モデル | 用途 | 備考 |
|-------|------|------|
| `text-embedding-3-small` | Phase 1 | OpenAI API、コスト低 |
| `mlx-community/bge-m3` | Phase 2 | ローカル実行、多言語対応 |
| `nomic-embed-text` | Phase 2 | Ollama経由、軽量 |

日本語を含むため、**多言語対応モデル推奨**（Phase 2以降）。

---

## 5. パイプライン設計

### 5-1. 処理フロー

```
[Obsidian vault] md files
        │
        ▼ scan_new_files()
  未処理ファイル検出（processed_atがNULLのもの）
        │
        ▼ parse_file()
  date抽出（filename or frontmatter）
  raw_text保存
  has_frontmatter判定
        │
        ▼ auto_tag() ← Claude API
  topics / mood / energy / locations /
  people / decisions / key_sentences 生成
        │
        ▼ upsert_db()
  SQLite（Phase 1）または PostgreSQL（Phase 2）にINSERT
        │
        ▼ embed_and_store()
  2種チャンク生成（key + sentence_group）→ Embedding → ChromaDB / pgvector
        │
        ▼ mark_processed()
  processed_at を更新
```

### 5-2. バッチ実行方針

- **Phase 1**: 手動実行（`python pipeline.py`）で十分
- **Phase 2**: `launchd`（macOS）でスケジュール実行（日次・深夜）

### 5-3. エラーハンドリング方針

- Claude API失敗時: raw_textのみ保存してスキップ、後でリトライ
- Embeddingエラー: ログ記録してスキップ
- 既存ファイル再処理: `--force`フラグで上書き可能にする

---

## 6. 実装フェーズ計画

### Phase 1（M1 Mac・即開始可能）

**目標**: パイプラインの基本動作確認

- [ ] `scan_and_parse.py`: vaultを走査してSQLiteに保存
- [ ] `auto_tag.py`: Claude APIで自動タグ付け（まず10件で精度確認）
- [ ] `embed.py`: ChromaDB + text-embedding-3-small
- [ ] `search_cli.py`: ターミナルからのテスト検索

**成功基準**: 「登山について書いた日を検索して」が意図通りヒットする

### Phase 2（M5 Mac Mini・購入後）

**目標**: 本番環境への移行と検索品質向上

- [ ] PostgreSQL + pgvector 環境構築（Docker Compose）
- [ ] Phase 1データの移行スクリプト
- [ ] ローカルEmbeddingモデルへの切り替え（MLX / Ollama）
- [ ] RAGインターフェース（FastAPI）

### Phase 3（本格運用）

**目標**: 自分AIとして実用化

- [ ] fine-tuning用データセット整形（`status: reviewed`のみ使用）
- [ ] 会話インターフェース設計
- [ ] 定期レポート機能（「今月の思考傾向」など）

---

## 7. ディレクトリ構成（実装側）

```
yuuka-ai/
├── README.md
├── config.py          # vault_path, db_path, API keys
├── pipeline.py        # エントリポイント（全体実行）
├── modules/
│   ├── scanner.py     # vault走査・ファイル読み込み
│   ├── parser.py      # frontmatter/プレーンテキスト両対応
│   ├── tagger.py      # Claude API自動タグ付け
│   ├── embedder.py    # Embedding + Vector Store保存
│   └── searcher.py    # 検索インターフェース
├── db/
│   ├── schema.sql
│   └── yuuka.db       # SQLite（Phase 1）
├── chroma_db/         # ChromaDB永続化ディレクトリ
└── logs/
    └── pipeline.log
```

---

## 8. 未決事項・メモ

- [ ] 会社ノートを同一vaultに入れるか別vaultにするか検討
- [ ] `reviewed`フラグを付ける基準・タイミングの運用ルール
- [ ] プライバシー観点での除外キーワード設定（人名マスクなど）
- [ ] Phase 2のRAGインターフェースをCLIにするかWebUIにするか

---

*このドキュメントはClaude Codeでの実装作業と並走して随時更新する。*