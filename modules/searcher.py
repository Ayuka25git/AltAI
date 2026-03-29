"""
searcher.py - ベクトル検索インターフェース

ChromaDBに対して自然言語クエリで検索を実行する。
chunk_typeでフィルタ可能（full / key / topic）。
"""

import json
import logging
from typing import Any

import chromadb
from openai import OpenAI

from config import OPENAI_API_KEY, EMBEDDING_MODEL
from modules.embedder import get_chroma_client, get_collection

logger = logging.getLogger(__name__)


def search(
    query: str,
    n_results: int = 5,
    chunk_type: str | None = None,
) -> list[dict[str, Any]]:
    """
    自然言語クエリでジャーナルを検索

    Args:
        query:      検索クエリ（日本語OK）
        n_results:  返す結果数
        chunk_type: "full" / "key" / "topic" でフィルタ（Noneで全対象）

    Returns:
        [{"date", "filename", "chunk_type", "text", "distance", "topics", ...}, ...]
    """
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.embeddings.create(input=[query], model=EMBEDDING_MODEL)
    query_embedding = response.data[0].embedding

    chroma = get_chroma_client()
    collection = get_collection(chroma)

    where = {"chunk_type": chunk_type} if chunk_type else None

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    hits = []
    for i in range(len(results["ids"][0])):
        meta = results["metadatas"][0][i]
        hits.append({
            "date": meta.get("date", ""),
            "filename": meta.get("filename", ""),
            "chunk_type": meta.get("chunk_type", ""),
            "text": results["documents"][0][i],
            "distance": results["distances"][0][i],
            "topics": json.loads(meta.get("topics", "[]")),
            "mood": meta.get("mood", ""),
            "energy": meta.get("energy", ""),
        })

    return hits


def format_results(hits: list[dict[str, Any]]) -> str:
    """検索結果を読みやすい文字列にフォーマット"""
    if not hits:
        return "該当なし"

    lines = []
    for i, hit in enumerate(hits, 1):
        lines.append(f"{'─' * 50}")
        lines.append(f"[{i}] {hit['date']}  ({hit['chunk_type']})  distance={hit['distance']:.3f}")
        if hit["topics"]:
            lines.append(f"    topics: {', '.join(hit['topics'])}")
        if hit["mood"]:
            lines.append(f"    mood: {hit['mood']}  energy: {hit['energy']}")
        lines.append(f"    {hit['text'][:300]}{'...' if len(hit['text']) > 300 else ''}")

    return "\n".join(lines)
