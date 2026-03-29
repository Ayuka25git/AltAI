"""
parser.py - Markdownファイルのパーサー

frontmatter付き・プレーンテキスト両対応。
日付はファイル名（YYYYMMDD.md）またはfrontmatterから抽出。
"""

import re
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


def parse_file(filepath: Path) -> dict:
    """
    Markdownファイルを解析してdictを返す

    Returns:
        {
            "date": "YYYY-MM-DD",
            "filename": "20251202.md",
            "raw_text": "...",
            "has_frontmatter": bool,
            "frontmatter": {...}  # frontmatterがある場合のみ
        }
    """
    content = filepath.read_text(encoding="utf-8")

    result = {
        "filename": filepath.name,
        "raw_text": "",
        "date": None,
        "has_frontmatter": False,
        "frontmatter": {},
    }

    # frontmatterの検出とパース
    if content.startswith("---"):
        fm, body = _parse_frontmatter(content)
        if fm is not None:
            result["has_frontmatter"] = True
            result["frontmatter"] = fm
            result["raw_text"] = body.strip()

            # frontmatterからdate取得
            if "date" in fm:
                result["date"] = _normalize_date(str(fm["date"]))
        else:
            result["raw_text"] = content.strip()
    else:
        result["raw_text"] = content.strip()

    # ファイル名からdate取得（fallback）
    if not result["date"]:
        result["date"] = _date_from_filename(filepath.name)

    return result


def _parse_frontmatter(content: str) -> tuple[dict | None, str]:
    """
    YAMLフロントマターをシンプルにパース（依存ライブラリ最小化）

    Returns: (frontmatter_dict, body_text) or (None, content)
    """
    match = re.match(r"^---\n(.*?)\n---\n?(.*)", content, re.DOTALL)
    if not match:
        return None, content

    fm_text = match.group(1)
    body = match.group(2)

    fm = {}
    for line in fm_text.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()

            # リスト形式: [a, b] or []
            if val.startswith("[") and val.endswith("]"):
                inner = val[1:-1].strip()
                if inner:
                    fm[key] = [v.strip().strip('"\'') for v in inner.split(",")]
                else:
                    fm[key] = []
            elif val:
                fm[key] = val

    return fm, body


def _date_from_filename(filename: str) -> str | None:
    """YYYYMMDD.md 形式のファイル名から日付を抽出"""
    stem = Path(filename).stem
    match = re.match(r"^(\d{4})(\d{2})(\d{2})$", stem)
    if match:
        y, m, d = match.groups()
        return f"{y}-{m}-{d}"
    return None


def _normalize_date(date_str: str) -> str | None:
    """様々な日付形式を YYYY-MM-DD に統一"""
    formats = ["%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    logger.warning(f"Could not parse date: {date_str}")
    return None
