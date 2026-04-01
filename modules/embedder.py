"""
embedder.py - Embedding生成とChromaDB保存モジュール

2種のチャンク戦略:
  - key:            key_sentences（思考検索・精度重視）
  - sentence_group: 3文スライディングウィンドウ（文脈付きRAG）

fine-tuning用データはChromaDBではなくSQLiteのraw_textが源泉。
Phase 1: OpenAI text-embedding-3-small
Phase 2: ローカルモデル（MLX / Ollama）に移行予定
"""

import json
import logging
import sqlite3
from typing import Any

import chromadb
from openai import OpenAI

from config import OPENAI_API_KEY, EMBEDDING_MODEL, CHROMA_DIR, CHROMA_COLLECTION

logger = logging.getLogger(__name__)


def get_chroma_client() -> chromadb.PersistentClient:
    """ChromaDBクライアントを返す（永続化）"""
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(CHROMA_DIR))


def get_collection(client: chromadb.PersistentClient) -> chromadb.Collection:
    return client.get_or_create_collection(
        name=CHROMA_COLLECTION,
        metadata={"hnsw:space": "cosine"}
    )


def _embed(texts: list[str]) -> list[list[float]]:
    """OpenAI APIでEmbeddingを生成"""
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.embeddings.create(
        input=texts,
        model=EMBEDDING_MODEL
    )
    return [item.embedding for item in response.data]


def _split_sentences(text: str) -> list[str]:
    """日本語テキストを「。」で文単位に分割し、空文字を除去して返す"""
    sentences = [s.strip() for s in text.split("。") if s.strip()]
    # 末尾に「。」を復元
    return [s + "。" for s in sentences]


def _sentence_group_chunks(
    filename: str,
    date: str,
    raw_text: str,
    metadata_base: dict[str, Any],
    window: int = 3,
    overlap: int = 1,
) -> list[dict[str, Any]]:
    """
    3文スライディングウィンドウでチャンクを生成

    - window:  1チャンクに含める文数
    - overlap: 前チャンクと共有する末尾文数
    """
    sentences = _split_sentences(raw_text)
    if not sentences:
        return []

    chunks = []
    step = window - overlap
    i = 0
    while i < len(sentences):
        group = sentences[i: i + window]
        # 最後の小さい断片は前のチャンクに吸収済みなのでスキップ
        if len(group) < window and i > 0:
            break
        chunks.append({
            "id": f"{filename}_sg_{i}",
            "text": "".join(group),
            "metadata": {
                **metadata_base,
                "chunk_type": "sentence_group",
                "sentence_start": i,
                "sentence_end": i + len(group) - 1,
            }
        })
        i += step

    return chunks


def _build_chunks(entry: sqlite3.Row) -> list[dict[str, Any]]:
    """
    1エントリから2種のチャンクを生成

    Returns: [{"id": str, "text": str, "metadata": dict}, ...]
    """
    date = entry["date"] or "unknown"
    filename = entry["filename"]
    raw_text = entry["raw_text"] or ""
    topics = json.loads(entry["topics"] or "[]")
    key_sentences = json.loads(entry["key_sentences"] or "[]")

    metadata_base = {
        "date": date,
        "filename": filename,
        "topics": json.dumps(topics, ensure_ascii=False),
        "mood": entry["mood"] or "",
        "energy": entry["energy"] or "",
    }

    chunks = []

    # 1. key チャンク（key_sentencesが存在する場合）
    if key_sentences:
        chunks.append({
            "id": f"{filename}_key",
            "text": "".join(key_sentences),
            "metadata": {**metadata_base, "chunk_type": "key"},
        })

    # 2. sentence_group チャンク
    if raw_text:
        chunks.extend(_sentence_group_chunks(filename, date, raw_text, metadata_base))

    return chunks


def embed_entry(entry: sqlite3.Row, collection: chromadb.Collection) -> bool:
    """
    1エントリをChromaDBに保存

    upsert前に同ファイルの既存チャンクを全削除することで、
    チャンク戦略変更後もゴーストデータが残らないようにする。

    Returns: 成功時True、失敗時False
    """
    try:
        filename = entry["filename"]

        # 同ファイルの既存チャンクを削除（chunk戦略変更時のゴーストデータ防止）
        existing = collection.get(where={"filename": filename})
        if existing["ids"]:
            collection.delete(ids=existing["ids"])
            logger.debug(f"Deleted {len(existing['ids'])} old chunks for {filename}")

        chunks = _build_chunks(entry)
        if not chunks:
            logger.warning(f"No chunks generated for {filename}")
            return False

        texts = [c["text"] for c in chunks]
        embeddings = _embed(texts)

        collection.upsert(
            ids=[c["id"] for c in chunks],
            documents=texts,
            embeddings=embeddings,
            metadatas=[c["metadata"] for c in chunks],
        )
        logger.info(f"Embedded {len(chunks)} chunks for {filename}")
        return True

    except Exception as e:
        logger.error(f"Embedding error for {entry['filename']}: {e}")
        return False
