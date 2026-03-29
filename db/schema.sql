-- Phase 1: SQLite スキーマ
-- Phase 2では PostgreSQL + pgvector に移行

CREATE TABLE IF NOT EXISTS journal_entries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT NOT NULL,          -- YYYY-MM-DD
    filename        TEXT NOT NULL UNIQUE,   -- 元ファイル名（例: 20251202.md）
    raw_text        TEXT,                   -- 原文そのまま

    -- LLMが自動生成するフィールド（Claude API）
    -- SQLiteはARRAY非対応のためJSON文字列で保存
    topics          TEXT,                   -- JSON: ["登山", "食"]
    mood            TEXT,                   -- 'reflective' / 'good' など
    energy          TEXT,                   -- 'high' / 'mid' / 'low'
    locations       TEXT,                   -- JSON: ["場所①", "場所②"]
    people          TEXT,                   -- JSON: ["人名"]
    decisions       TEXT,                   -- JSON: ["概要"]
    key_sentences   TEXT,                   -- JSON: ["文1", "文2"]

    -- フラグ
    has_frontmatter INTEGER DEFAULT 0,      -- BOOLEAN（0/1）
    processed_at    TEXT,                   -- ISO8601 タイムスタンプ
    embedded_at     TEXT,                   -- Embedding完了時刻
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_date ON journal_entries(date);
CREATE INDEX IF NOT EXISTS idx_processed ON journal_entries(processed_at);
