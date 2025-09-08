"""
Cloud Functions for Firebase - 歯科国試アプリ用ランキング更新システム

このファイルは以下の機能を提供します：
1. HTTP トリガーでランキングを更新
2. 毎日 3:00 AM JST に Cloud Scheduler から呼び出される
3. 既存の ranking_updater.py モジュールを使用

デプロイ方法:
```
cd functions
npm install
npm run build
firebase deploy --only functions
```

Cloud Scheduler 設定:
```
gcloud scheduler jobs create http dental-ranking-update \
    --schedule="0 3 * * *" \
    --uri="https://asia-northeast1-{PROJECT_ID}.cloudfunctions.net/updateRankings" \
    --http-method=GET \
    --time-zone="Asia/Tokyo" \
    --description="歯科国試アプリ ランキング更新 (毎日3時)"
```
"""

import json
import os
import sys
import traceback
from datetime import datetime
from typing import Any, Dict

import pytz
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud import logging as cloud_logging

# Cloud Functions Framework
import functions_framework
from flask import Request

# Firebase初期化（一度だけ実行）
if not firebase_admin._apps:
    # Cloud Functions環境では自動的にサービスアカウントが利用される
    firebase_admin.initialize_app()

# Cloud Loggingクライアント
logging_client = cloud_logging.Client()
logging_client.setup_logging()

# Pythonの標準ロギング
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# 日本時間設定
JST = pytz.timezone("Asia/Tokyo")


def setup_python_path():
    """Python パスを設定して my_llm_app モジュールをインポート可能にする"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    my_llm_app_path = os.path.join(parent_dir, 'my_llm_app')
    
    if my_llm_app_path not in sys.path:
        sys.path.insert(0, my_llm_app_path)
    
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)


def import_ranking_updater():
    """ranking_updater モジュールを動的にインポート"""
    try:
        setup_python_path()
        
        # my_llm_app モジュールからインポート
        from modules.ranking_updater import update_all_rankings, should_update_today
        return update_all_rankings, should_update_today
    except ImportError as e:
        logger.error(f"Failed to import ranking_updater: {e}")
        logger.error(f"Current sys.path: {sys.path}")
        raise


@functions_framework.http
def updateRankings(request: Request) -> Dict[str, Any]:
    """
    HTTP トリガー関数 - ランキング更新
    
    URL: https://asia-northeast1-{PROJECT_ID}.cloudfunctions.net/updateRankings
    
    クエリパラメータ:
    - force: "true" で強制実行（通常の3時チェックを無視）
    - dry_run: "true" でドライラン（実際の更新は行わない）
    
    Returns:
        JSON レスポンス with status, message, data
    """
    start_time = datetime.now(JST)
    logger.info(f"ランキング更新開始: {start_time.isoformat()}")
    
    try:
        # パラメータ取得
        force = request.args.get('force', '').lower() == 'true'
        dry_run = request.args.get('dry_run', '').lower() == 'true'
        
        logger.info(f"実行パラメータ: force={force}, dry_run={dry_run}")
        
        # モジュールインポート
        update_all_rankings, should_update_today = import_ranking_updater()
        
        # 更新要否チェック（force=true の場合はスキップ）
        if not force:
            if not should_update_today():
                message = "今日はすでに更新済みです。強制実行する場合は ?force=true を付けてください。"
                logger.info(message)
                return {
                    'status': 'skipped',
                    'message': message,
                    'timestamp': start_time.isoformat(),
                    'force': force,
                    'dry_run': dry_run
                }
        
        # ドライラン処理
        if dry_run:
            logger.info("ドライラン実行 - 実際の更新は行いません")
            # ダミーデータを返す
            result = {
                'status': 'success',
                'message': 'ドライラン実行完了（実際の更新は行っていません）',
                'data': {
                    'processed': 0,
                    'errors': 0,
                    'profiles': 0,
                    'dry_run': True
                },
                'timestamp': start_time.isoformat(),
                'execution_time_seconds': 0.1,
                'force': force,
                'dry_run': dry_run
            }
            logger.info(f"ドライラン結果: {result}")
            return result
        
        # 実際のランキング更新実行
        logger.info("ランキング更新実行中...")
        update_result = update_all_rankings()
        
        end_time = datetime.now(JST)
        execution_time = (end_time - start_time).total_seconds()
        
        result = {
            'status': 'success',
            'message': 'ランキング更新が正常に完了しました',
            'data': update_result,
            'timestamp': start_time.isoformat(),
            'execution_time_seconds': execution_time,
            'force': force,
            'dry_run': dry_run
        }
        
        logger.info(f"ランキング更新完了: {update_result}")
        logger.info(f"実行時間: {execution_time:.2f}秒")
        
        return result
        
    except Exception as e:
        error_msg = f"ランキング更新でエラーが発生しました: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        
        end_time = datetime.now(JST)
        execution_time = (end_time - start_time).total_seconds()
        
        return {
            'status': 'error',
            'message': error_msg,
            'error_details': str(e),
            'timestamp': start_time.isoformat(),
            'execution_time_seconds': execution_time,
            'force': request.args.get('force', '').lower() == 'true',
            'dry_run': request.args.get('dry_run', '').lower() == 'true'
        }, 500


@functions_framework.http
def healthCheck(request: Request) -> Dict[str, Any]:
    """
    ヘルスチェック用エンドポイント
    
    URL: https://asia-northeast1-{PROJECT_ID}.cloudfunctions.net/healthCheck
    """
    try:
        current_time = datetime.now(JST)
        
        # Firebase接続チェック
        db = firestore.client()
        test_doc = db.collection('_health_check').document('test').get()
        
        # モジュールインポートチェック
        try:
            update_all_rankings, should_update_today = import_ranking_updater()
            modules_ok = True
        except Exception as e:
            logger.warning(f"Module import test failed: {e}")
            modules_ok = False
        
        # 今日の更新要否チェック
        try:
            should_update = should_update_today() if modules_ok else None
        except Exception:
            should_update = None
        
        return {
            'status': 'healthy',
            'timestamp': current_time.isoformat(),
            'timezone': 'Asia/Tokyo',
            'firebase_connection': 'ok',
            'modules_import': 'ok' if modules_ok else 'error',
            'should_update_today': should_update,
            'function_name': 'dental-ranking-functions',
            'version': '1.0.0'
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now(JST).isoformat()
        }, 500


# デバッグ用のローカル実行関数
def main():
    """ローカルでのテスト実行用"""
    from flask import Flask
    app = Flask(__name__)
    
    @app.route('/update-rankings')
    def local_update():
        from flask import request
        return updateRankings(request)
    
    @app.route('/health')
    def local_health():
        from flask import request
        return healthCheck(request)
    
    print("Local server starting on http://localhost:8080")
    print("Endpoints:")
    print("  - GET /update-rankings?force=true&dry_run=true")
    print("  - GET /health")
    
    app.run(host='0.0.0.0', port=8080, debug=True)


if __name__ == '__main__':
    main()
