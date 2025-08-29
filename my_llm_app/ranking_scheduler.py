#!/usr/bin/env python3
"""
週間ランキングバッチ処理のスケジューラー

このスクリプトはcronジョブとして毎日午前3時に実行されることを想定
- 週間ランキングの事前計算
- 上位20位のランキング更新
- ログファイルへの結果出力

使用方法:
1. crontabに追加:
   0 3 * * * /path/to/python /path/to/ranking_scheduler.py

2. 手動実行:
   python ranking_scheduler.py

3. systemdサービス化も可能
"""

import sys
import os
import logging
from datetime import datetime
import traceback

# プロジェクトのルートディレクトリをPATHに追加
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# ログファイルの設定
log_dir = os.path.join(current_dir, 'logs')
os.makedirs(log_dir, exist_ok=True)

log_file = os.path.join(log_dir, f'ranking_batch_{datetime.now().strftime("%Y%m")}.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


def main():
    """メイン処理"""
    try:
        logger.info("=== 週間ランキングバッチ処理開始 ===")
        logger.info(f"実行時刻: {datetime.now()}")
        
        # バッチ処理をインポート（遅延インポートでFirebase初期化を適切に行う）
        from weekly_ranking_batch import run_batch
        
        # バッチ処理実行
        success = run_batch()
        
        if success:
            logger.info("✅ 週間ランキングバッチ処理が正常に完了しました")
            return 0
        else:
            logger.error("❌ 週間ランキングバッチ処理でエラーが発生しました")
            return 1
            
    except ImportError as e:
        logger.error(f"モジュールインポートエラー: {e}")
        logger.error("Firebase設定またはPythonパスを確認してください")
        return 1
        
    except Exception as e:
        logger.error(f"予期しないエラーが発生しました: {e}")
        logger.error(f"トレースバック: {traceback.format_exc()}")
        return 1
    
    finally:
        logger.info("=== 週間ランキングバッチ処理終了 ===")


def test_connection():
    """Firebase接続テスト"""
    try:
        logger.info("Firebase接続テストを実行中...")
        
        from firestore_db import get_firestore_manager
        manager = get_firestore_manager()
        
        # 簡単なテストクエリ
        test_ref = manager.db.collection("users").limit(1)
        test_docs = test_ref.stream()
        
        doc_count = 0
        for _ in test_docs:
            doc_count += 1
        
        logger.info(f"✅ Firebase接続成功 (テストドキュメント数: {doc_count})")
        return True
        
    except Exception as e:
        logger.error(f"❌ Firebase接続エラー: {e}")
        return False


if __name__ == "__main__":
    # 引数処理
    if len(sys.argv) > 1:
        if sys.argv[1] == "--test":
            # 接続テストのみ実行
            success = test_connection()
            sys.exit(0 if success else 1)
        elif sys.argv[1] == "--help":
            print("週間ランキングバッチ処理スケジューラー")
            print("使用方法:")
            print("  python ranking_scheduler.py          # バッチ処理実行")
            print("  python ranking_scheduler.py --test   # 接続テスト")
            print("  python ranking_scheduler.py --help   # ヘルプ表示")
            sys.exit(0)
    
    # メイン処理実行
    exit_code = main()
    sys.exit(exit_code)
