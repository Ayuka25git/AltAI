"""
scanner.py - RawVault内のMarkdownファイルを走査してDB管理するモジュール

Obsidianディレクトリは直接参照しない。
RawVaultにコピーされたファイルのみを対象とする。
"""

import sqlite3
import logging
from pathlib import Path
from datetime import datetime

from config import RAW_VAULT_PATH, DB_PATH

logger = logging.getLogger(__name__)


def init_db() -> sqlite3.Connection:
    """SQLiteデータベースを初期化してコネクションを返す"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    schema_path = Path(__file__).parent.parent / "db" / "schema.sql"
    with open(schema_path) as f:
        conn.executescript(f.read())
    conn.commit()
    return conn


def get_vault_files() -> list[Path]:
    """RawVault内の全Markdownファイルをリストアップ（日付順）"""
    if not RAW_VAULT_PATH.exists():
        logger.error(f"RawVault not found: {RAW_VAULT_PATH}")
        return []
    files = sorted(RAW_VAULT_PATH.glob("*.md"))
    logger.info(f"Found {len(files)} markdown files in RawVault")
    return files


def get_unprocessed_files(conn: sqlite3.Connection) -> list[Path]:
    """未処理（processed_at が NULL）のファイルを返す"""
    all_files = get_vault_files()
    cursor = conn.execute(
        "SELECT filename FROM journal_entries WHERE processed_at IS NOT NULL"
    )
    processed = {row["filename"] for row in cursor}

    unprocessed = [f for f in all_files if f.name not in processed]
    logger.info(f"{len(unprocessed)} unprocessed files found")
    return unprocessed


def register_file(conn: sqlite3.Connection, filepath: Path, date: str) -> int:
    """ファイルをDBに登録（未登録の場合のみ）してidを返す"""
    cursor = conn.execute(
        "SELECT id FROM journal_entries WHERE filename = ?",
        (filepath.name,)
    )
    row = cursor.fetchone()
    if row:
        return row["id"]

    conn.execute(
        "INSERT INTO journal_entries (filename, date) VALUES (?, ?)",
        (filepath.name, date)
    )
    conn.commit()
    cursor = conn.execute(
        "SELECT id FROM journal_entries WHERE filename = ?",
        (filepath.name,)
    )
    return cursor.fetchone()["id"]


def mark_processed(conn: sqlite3.Connection, entry_id: int):
    """エントリを処理済みとしてマーク"""
    conn.execute(
        "UPDATE journal_entries SET processed_at = ? WHERE id = ?",
        (datetime.now().isoformat(), entry_id)
    )
    conn.commit()


def mark_embedded(conn: sqlite3.Connection, entry_id: int):
    """エントリをEmbedding完了としてマーク"""
    conn.execute(
        "UPDATE journal_entries SET embedded_at = ? WHERE id = ?",
        (datetime.now().isoformat(), entry_id)
    )
    conn.commit()


def get_unembedded_entries(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """タグ付け済みだがEmbedding未完了のエントリを返す"""
    cursor = conn.execute(
        """
        SELECT * FROM journal_entries
        WHERE processed_at IS NOT NULL
          AND embedded_at IS NULL
          AND raw_text IS NOT NULL
        """
    )
    return cursor.fetchall()
