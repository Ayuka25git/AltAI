"""
pipeline.py - Phase 1 メインパイプライン

使い方:
    python pipeline.py               # 全ステップ実行
    python pipeline.py --parse-only  # パース・DB登録のみ
    python pipeline.py --tag-only    # タグ付けのみ（未タグのエントリ対象）
    python pipeline.py --embed-only  # Embeddingのみ（未Embeddingのエントリ対象）
    python pipeline.py --force       # 処理済みファイルも再処理
    python pipeline.py --limit 10    # 処理件数上限
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from config import LOG_PATH
from modules.scanner import (
    init_db,
    get_vault_files,
    get_unprocessed_files,
    register_file,
    mark_processed,
    mark_embedded,
    get_unembedded_entries,
)
from modules.parser import parse_file
from modules.tagger import auto_tag, save_tags
from modules.embedder import get_chroma_client, get_collection, embed_entry

# ─── ロギング設定 ──────────────────────────────────────────────
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(LOG_PATH), encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


# ─── ステップ関数 ──────────────────────────────────────────────

def step_parse(conn, files: list[Path]) -> int:
    """ファイルを解析してDBに保存"""
    count = 0
    for filepath in files:
        try:
            parsed = parse_file(filepath)
            entry_id = register_file(conn, filepath, parsed["date"])

            conn.execute(
                """
                UPDATE journal_entries SET
                    date            = ?,
                    raw_text        = ?,
                    has_frontmatter = ?
                WHERE id = ?
                """,
                (parsed["date"], parsed["raw_text"], int(parsed["has_frontmatter"]), entry_id)
            )
            conn.commit()
            logger.info(f"Parsed: {filepath.name}  date={parsed['date']}")
            count += 1
        except Exception as e:
            logger.error(f"Parse error {filepath.name}: {e}")
    return count


def step_tag(conn, limit: int | None = None) -> int:
    """未タグ付けエントリにClaude APIでタグを付ける"""
    cursor = conn.execute(
        """
        SELECT id, filename, raw_text FROM journal_entries
        WHERE raw_text IS NOT NULL
          AND topics IS NULL
        ORDER BY date
        """
    )
    entries = cursor.fetchall()
    if limit:
        entries = entries[:limit]

    count = 0
    for entry in entries:
        logger.info(f"Tagging: {entry['filename']}")
        tags = auto_tag(entry["raw_text"])
        if tags:
            save_tags(conn, entry["id"], tags)
            mark_processed(conn, entry["id"])
            logger.info(f"  topics={tags.get('topics')}, mood={tags.get('mood')}")
            count += 1
        else:
            logger.warning(f"  Tagging failed, skipping: {entry['filename']}")
    return count


def step_embed(conn, limit: int | None = None) -> int:
    """未Embeddingエントリを処理"""
    entries = get_unembedded_entries(conn)
    if limit:
        entries = entries[:limit]

    chroma = get_chroma_client()
    collection = get_collection(chroma)

    count = 0
    for entry in entries:
        logger.info(f"Embedding: {entry['filename']}")
        success = embed_entry(entry, collection)
        if success:
            mark_embedded(conn, entry["id"])
            count += 1
    return count


# ─── エントリポイント ──────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="yuuka-ai パイプライン — RawVaultのMarkdownを解析・タグ付け・Embeddingして検索可能にする",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
実行例:
  python pipeline.py                  # 全ステップ（Parse → Tag → Embed）を一括実行
  python pipeline.py --parse-only     # Parse のみ（DB登録まで）
  python pipeline.py --tag-only       # Tag のみ（未タグエントリを対象）
  python pipeline.py --embed-only     # Embed のみ（未Embeddingエントリを対象）
  python pipeline.py --limit 3        # 処理件数を3件に制限（動作確認用）
  python pipeline.py --force          # 処理済みファイルも含めて再処理
        """
    )
    parser.add_argument("--parse-only", action="store_true",
                        help="RawVaultのファイルを読み込んでSQLiteに保存するだけで止まる")
    parser.add_argument("--tag-only",   action="store_true",
                        help="Claude APIでタグ付けのみ実行（Parseは済んでいる前提）")
    parser.add_argument("--embed-only", action="store_true",
                        help="EmbeddingとChromaDB保存のみ実行（Tag済みが前提）")
    parser.add_argument("--force",      action="store_true",
                        help="processed_at済みのファイルも再度Parseして上書きする")
    parser.add_argument("--limit",      type=int, default=None,
                        help="処理するファイル・エントリ数の上限（精度確認や部分実行に使用）")
    args = parser.parse_args()

    conn = init_db()
    logger.info("=== Pipeline started ===")

    # ─── Parse ───
    if not args.tag_only and not args.embed_only:
        if args.force:
            files = get_vault_files()
        else:
            files = get_unprocessed_files(conn)

        if args.limit:
            files = files[:args.limit]

        if files:
            n = step_parse(conn, files)
            logger.info(f"Parse complete: {n} files")
        else:
            logger.info("No new files to parse")

        if args.parse_only:
            conn.close()
            return

    # ─── Tag ───
    if not args.embed_only:
        n = step_tag(conn, limit=args.limit)
        logger.info(f"Tag complete: {n} entries")

        if args.tag_only:
            conn.close()
            return

    # ─── Embed ───
    n = step_embed(conn, limit=args.limit)
    logger.info(f"Embed complete: {n} entries")

    conn.close()
    logger.info("=== Pipeline finished ===")


if __name__ == "__main__":
    main()
