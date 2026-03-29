import os
from pathlib import Path
from dotenv import load_dotenv

# プロジェクトルート
BASE_DIR = Path(__file__).parent

# RawVault: ObsidianからコピーしたMarkdownファイルの置き場所
# Obsidianのディレクトリを直接参照しない設計
RAW_VAULT_PATH = BASE_DIR / "RawVault"

# データベース
DB_PATH = BASE_DIR / "db" / "yuuka.db"

# ChromaDB 永続化ディレクトリ
CHROMA_DIR = BASE_DIR / "chroma_db"

# ログ
LOG_PATH = BASE_DIR / "logs" / "pipeline.log"

# API Keys（環境変数から取得）
load_dotenv()
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# Claude モデル
CLAUDE_MODEL = "claude-haiku-4-5-20251001"  # タグ付け用（コスト抑制）

# Embedding モデル（Phase 1: OpenAI）
EMBEDDING_MODEL = "text-embedding-3-small"

# ChromaDB コレクション名
CHROMA_COLLECTION = "journal_entries"
