"""
tagger.py - Claude APIを使った自動タグ付けモジュール

日記テキストを分析してtopics/mood/energy/locations/people/decisions/key_sentencesを生成。
API失敗時はスキップして後でリトライ可能にする。
"""

import json
import logging
import sqlite3
from typing import Any

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL

logger = logging.getLogger(__name__)

TAG_PROMPT = """\
以下の日記エントリを分析し、JSONのみで返してください（前置き・コードブロック不要）。

{raw_text}

出力フォーマット:
{{
  "topics": ["テーマ1", "テーマ2"],
  "mood": "感情トーン",
  "energy": "high|mid|low",
  "locations": ["場所1"],
  "people": ["人物1"],
  "decisions": ["決断・意図"],
  "key_sentences": ["文1", "文2"]
}}

ルール:
- topicsは3〜5個（日本語）
- moodは1語（日本語または英語）
- key_sentencesは思考の核心を表す原文を最大3文
- 該当なしの場合は空配列 []
- JSONのみ出力、他の文字は一切含めない\
"""


def auto_tag(raw_text: str) -> dict[str, Any] | None:
    """
    Claude APIで日記テキストを自動タグ付け

    Returns:
        タグdictまたはNone（失敗時）
    """
    if not ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY が設定されていません")
        return None

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    try:
        message = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": TAG_PROMPT.format(raw_text=raw_text)
                }
            ]
        )
        response_text = message.content[0].text.strip()

        # コードブロック記法を除去（```json ... ``` など）
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
            response_text = response_text.strip()

        # JSONパース
        tags = json.loads(response_text)
        logger.debug(f"Tagged: topics={tags.get('topics')}, mood={tags.get('mood')}")
        return tags

    except json.JSONDecodeError as e:
        logger.error(f"JSONパースエラー: {e}\nResponse: {response_text}")
        return None
    except anthropic.APIError as e:
        logger.error(f"Claude API エラー: {e}")
        return None


def save_tags(conn: sqlite3.Connection, entry_id: int, tags: dict[str, Any]):
    """タグ情報をDBに保存（JSON文字列として）"""
    conn.execute(
        """
        UPDATE journal_entries SET
            topics        = ?,
            mood          = ?,
            energy        = ?,
            locations     = ?,
            people        = ?,
            decisions     = ?,
            key_sentences = ?
        WHERE id = ?
        """,
        (
            json.dumps(tags.get("topics", []), ensure_ascii=False),
            tags.get("mood", ""),
            tags.get("energy", ""),
            json.dumps(tags.get("locations", []), ensure_ascii=False),
            json.dumps(tags.get("people", []), ensure_ascii=False),
            json.dumps(tags.get("decisions", []), ensure_ascii=False),
            json.dumps(tags.get("key_sentences", []), ensure_ascii=False),
            entry_id,
        )
    )
    conn.commit()
