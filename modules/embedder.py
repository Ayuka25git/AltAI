"""
embedder.py - Embedding生成とChromaDB保存モジュール

3種のチャンク戦略:
  - full:  raw_text全体（文体学習・fine-tuning用）
  - key:   key_sentences（思考検索・精度重視）
  - topic: topicsで分割した段落（テーマ別RAG）

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


def _build_chunks(entry: sqlite3.Row) -> list[dict[str, Any]]:
    """
    1エントリから3種のチャンクを生成

    Returns: [{"id": str, "text": str, "metadata": dict}, ...]
    """
    date = entry["date"] or "unknown"
    filename = entry["filename"]
    raw_text = entry["raw_text"] or ""
    topics = json.loads(entry["topics"] or "[]")
    key_sentences = json.loads(entry["key_sentences"] or "[]")

    chunks = []

    # 1. full チャンク
    if raw_text:
        chunks.append({
            "id": f"{filename}_full",
            "text": raw_text,
            "metadata": {
                "chunk_type": "full",
                "date": date,
                "filename": filename,
                "topics": json.dumps(topics, ensure_ascii=False),
                "mood": entry["mood"] or "",
                "energy": entry["energy"] or "",
            }
        })

    # 2. key チャンク（key_sentencesが存在する場合）
    if key_sentences:
        key_text = " ".join(key_sentences)
        chunks.append({
            "id": f"{filename}_key",
            "text": key_text,
            "metadata": {
                "chunk_type": "key",
                "date": date,
                "filename": filename,
                "topics": json.dumps(topics, ensure_ascii=False),
                "mood": entry["mood"] or "",
                "energy": entry["energy"] or "",
            }
        })

    # 3. topic チャンク（topicsが存在する場合、raw_textをtopic数で分割）
    if topics and raw_text:
        # シンプルに段落分割してtopicsのメタデータを付与
        paragraphs = [p.strip() for p in raw_text.split("\n\n") if p.strip()]
        for i, para in enumerate(paragraphs):
            chunks.append({
                "id": f"{filename}_topic_{i}",
                "text": para,
                "metadata": {
                    "chunk_type": "topic",
                    "date": date,
                    "filename": filename,
                    "topics": json.dumps(topics, ensure_ascii=False),
                    "mood": entry["mood"] or "",
                    "energy": entry["energy"] or "",
                    "para_index": i,
                }
            })

    return chunks


def embed_entry(entry: sqlite3.Row, collection: chromadb.Collection) -> bool:
    """
    1エントリをChromaDBに保存

    Returns: 成功時True、失敗時False
    """
    try:
        chunks = _build_chunks(entry)
        if not chunks:
            logger.warning(f"No chunks generated for {entry['filename']}")
            return False

        texts = [c["text"] for c in chunks]
        embeddings = _embed(texts)

        collection.upsert(
            ids=[c["id"] for c in chunks],
            documents=texts,
            embeddings=embeddings,
            metadatas=[c["metadata"] for c in chunks],
        )
        logger.info(f"Embedded {len(chunks)} chunks for {entry['filename']}")
        return True

    except Exception as e:
        logger.error(f"Embedding error for {entry['filename']}: {e}")
        return False
