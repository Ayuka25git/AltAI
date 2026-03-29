"""
search_cli.py - ターミナルからのテスト検索インターフェース

使い方:
    python search_cli.py "登山について書いた日"
    python search_cli.py "登山" --type key --n 3
    python search_cli.py --interactive
"""

import argparse
import sys

from modules.searcher import search, format_results


def main():
    parser = argparse.ArgumentParser(
        description="yuuka-ai 検索CLI — ChromaDBに対して自然言語でベクトル検索を行う",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
実行例:
  python search_cli.py "登山について書いた日"        # 全チャンクから検索
  python search_cli.py "登山" --type key            # key（核心文）チャンクのみ検索
  python search_cli.py "登山" --type full --n 3     # full チャンクから上位3件
  python search_cli.py --interactive                 # 対話モードで繰り返し検索

チャンク種別:
  full  ... 日記のraw_text全体（文体・文脈を広く検索したいとき）
  key   ... Claude APIが抽出した核心文3文（思考・意図の検索に向く）
  topic ... 段落単位のチャンク（テーマ別に絞りたいとき）
        """
    )
    parser.add_argument("query", nargs="?",
                        help="検索クエリ（日本語可）。省略すると --help を表示")
    parser.add_argument("--type", choices=["full", "key", "topic"], default=None,
                        help="チャンク種別でフィルタ。省略すると全種別が対象")
    parser.add_argument("--n", type=int, default=5,
                        help="表示する検索結果の件数（デフォルト: 5）")
    parser.add_argument("--interactive", "-i", action="store_true",
                        help="対話モード。クエリを繰り返し入力できる（終了: q）")
    args = parser.parse_args()

    if args.interactive:
        print("yuuka-ai 検索 (終了: q または Ctrl+C)")
        print(f"chunk_type: {args.type or '全種別'}  件数: {args.n}")
        print()
        while True:
            try:
                query = input("検索 > ").strip()
                if not query or query.lower() == "q":
                    break
                hits = search(query, n_results=args.n, chunk_type=args.type)
                print(format_results(hits))
                print()
            except KeyboardInterrupt:
                print()
                break
        return

    if not args.query:
        parser.print_help()
        sys.exit(1)

    hits = search(args.query, n_results=args.n, chunk_type=args.type)
    print(format_results(hits))


if __name__ == "__main__":
    main()
