#!/usr/bin/env python3
"""
Crawl4AI MCP HTTP Server
FastMCPのStreamableHTTPプロトコルを使用してHTTPアクセス可能なMCPサーバーを起動
"""

import asyncio
import argparse
import logging
import os
import sys
from pathlib import Path

# プロジェクトルートをPythonパスに追加
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from crawl4ai_mcp.server import mcp


def setup_logging(log_level: str = "INFO"):
    """ログ設定をセットアップ"""
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


async def run_http_server(host: str = "127.0.0.1", port: int = 8000, log_level: str = "INFO"):
    """HTTPサーバーを起動"""
    setup_logging(log_level)
    
    logger = logging.getLogger(__name__)
    logger.info(f"🚀 Crawl4AI MCP HTTPサーバーを起動中...")
    logger.info(f"📡 ホスト: {host}")
    logger.info(f"🔌 ポート: {port}")
    logger.info(f"🌐 エンドポイント: http://{host}:{port}")
    
    try:
        # Streamable HTTP transport (FastMCP 3.0 API)
        await mcp.run(
            transport="http",
            host=host,
            port=port,
        )
    except KeyboardInterrupt:
        logger.info("📴 サーバーを停止しています...")
    except Exception as e:
        logger.error(f"❌ サーバーエラー: {e}")
        raise


def main():
    """メインエントリーポイント"""
    parser = argparse.ArgumentParser(
        description="Crawl4AI MCP HTTPサーバー",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  python run_http_server.py                    # デフォルト設定で起動 (127.0.0.1:8000)
  python run_http_server.py --host 0.0.0.0     # 外部アクセス可能で起動
  python run_http_server.py --port 8080        # ポート8080で起動
  python run_http_server.py --log-level DEBUG  # デバッグログレベルで起動

HTTPエンドポイント:
  GET  /                                        # サーバー情報
  POST /mcp/tools                              # ツール一覧取得
  POST /mcp/tools/{tool_name}                  # ツール実行
  POST /mcp/prompts                            # プロンプト一覧取得
  POST /mcp/prompts/{prompt_name}              # プロンプト実行
  POST /mcp/resources                          # リソース一覧取得
  POST /mcp/resources/{resource_uri}           # リソース取得

主要なツール:
  crawl_url                                    # Webページクローリング
  extract_youtube_transcript                  # YouTube字幕抽出
  search_google                               # Google検索
  process_file                                # ファイル処理
  extract_structured_data                     # 構造化データ抽出
        """
    )
    
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="バインドするホスト (デフォルト: 127.0.0.1, 外部アクセス許可: 0.0.0.0)"
    )
    
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="バインドするポート (デフォルト: 8000)"
    )
    
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="ログレベル (デフォルト: INFO)"
    )
    
    args = parser.parse_args()
    
    # セキュリティ警告
    if args.host == "0.0.0.0":
        print("⚠️  警告: 外部アクセス可能な設定で起動します")
        print("   適切なファイアウォール設定を確認してください")
        print()
    
    print("🎯 Crawl4AI MCP HTTPサーバー")
    print(f"📍 アドレス: http://{args.host}:{args.port}")
    print("📚 APIドキュメント: /docs (利用可能な場合)")
    print("🛑 停止: Ctrl+C")
    print()
    
    try:
        asyncio.run(run_http_server(
            host=args.host,
            port=args.port,
            log_level=args.log_level
        ))
    except KeyboardInterrupt:
        print("\n👋 サーバーを停止しました")
    except Exception as e:
        print(f"\n❌ エラー: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()