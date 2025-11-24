import os
import sys
import traceback
import firebase_admin
from firebase_admin import credentials, firestore
import datetime
import pytz
from typing import Dict, Any, List, Tuple
from collections import defaultdict
import logging
from google.cloud import logging as cloud_logging
import functions_framework
from flask import Request, Flask, request, jsonify, make_response
from firebase_admin import auth
import json

# --- グローバル変数の設定 ---
print("Initializing global variables...")

# Firebase初期化（一度だけ実行）
if not firebase_admin._apps:
    try:
        print("Attempting Firebase initialization...")
        # Cloud Functions環境では自動的にサービスアカウントが利用される
        cred = credentials.ApplicationDefault()
        firebase_admin.initialize_app(cred)
        print("Firebase initialized with ApplicationDefault")
    except Exception as e:
        print(f"Firebase init error (ApplicationDefault): {e}")
        try:
            # ローカル環境などでの代替初期化
            firebase_admin.initialize_app()
            print("Firebase initialized with default")
        except Exception as e2:
            print(f"Firebase init error (default): {e2}")

try:
    print("Initializing Firestore client...")
    db = firestore.client()
    print("Firestore client initialized")
except Exception as e:
    print(f"Firestore client init error: {e}")
    db = None

JST = pytz.timezone("Asia/Tokyo")

# Cloud Loggingクライアント設定
try:
    print("Initializing Cloud Logging...")
    client = cloud_logging.Client()
    client.setup_logging()
    print("Cloud Logging initialized")
except Exception as e:
    # ローカル実行などで権限がない場合、標準ロギングにフォールバック
    print(f"Cloud Logging init error: {e}")
    logging.basicConfig(level=logging.INFO)
    logging.warning(f"Cloud Loggingの初期化に失敗しました: {e}")

# Pythonの標準ロギング
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
print("Global initialization complete.")


# === ランキング計算ロジック（スタンドアロン版） ===

def calculate_weekly_points(cards: Dict, evaluation_logs: List[Dict] = None) -> int:
    """週間ポイントを計算"""
    try:
        one_week_ago = datetime.datetime.now(JST) - datetime.timedelta(days=7)
        weekly_points = 0
        
        for card in cards.values():
            history = card.get("history", [])
            for entry in history:
                try:
                    timestamp = entry.get("timestamp")
                    if isinstance(timestamp, str):
                        entry_time = datetime.datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        if entry_time.replace(tzinfo=None) > one_week_ago.replace(tzinfo=None):
                            quality = entry.get("quality", 0)
                            if quality >= 3:
                                weekly_points += max(1, quality - 2)
                except Exception:
                    continue
        
        return weekly_points
    except Exception:
        return 0

def calculate_total_points(cards: Dict, evaluation_logs: List[Dict] = None) -> Tuple[int, int, float]:
    """総合ポイント、問題数、正答率を計算"""
    try:
        total_points = 0
        total_problems = 0
        correct_answers = 0
        
        for card in cards.values():
            history = card.get("history", [])
            if history:
                total_problems += len(history)
                for entry in history:
                    quality = entry.get("quality", 0)
                    total_points += max(1, quality)
                    if quality >= 3:
                        correct_answers += 1
        
        accuracy_rate = (correct_answers / total_problems) if total_problems > 0 else 0.0
        return total_points, total_problems, accuracy_rate
    except Exception:
        return 0, 0, 0.0

def calculate_mastery_score(cards: Dict) -> Tuple[float, int, int, int, float]:
    """習熟度スコア、エキスパートカード数、上級カード数、総カード数、平均EFを計算"""
    try:
        expert_cards = 0
        advanced_cards = 0
        total_cards = len(cards)
        total_ef = 0
        ef_count = 0
        mastery_score = 0.0
        
        for card in cards.values():
            sm2_data = card.get("sm2_data", {})
            n = sm2_data.get("n", 0)
            ef = sm2_data.get("ef", 2.5)
            
            if ef > 0:
                total_ef += ef
                ef_count += 1
            
            performance = card.get("performance", {})
            avg_quality = performance.get("avg_quality", 0)
            
            # 習熟度判定
            if n >= 5 and avg_quality >= 4.0:
                expert_cards += 1
                mastery_score += 10
            elif n >= 3 and avg_quality >= 3.5:
                advanced_cards += 1
                mastery_score += 5
            elif n >= 1:
                mastery_score += max(1, avg_quality)
        
        avg_ef = total_ef / ef_count if ef_count > 0 else 2.5
        return mastery_score, expert_cards, advanced_cards, total_cards, avg_ef
    except Exception:
        return 0.0, 0, 0, 0, 2.5

def _is_duplicate_user(user1: Dict, user2: Dict) -> bool:
    """効率的な重複ユーザー判定"""
    try:
        # 簡易的な重複判定（必要に応じて強化）
        nickname1 = user1.get("nickname", "").strip().lower()
        nickname2 = user2.get("nickname", "").strip().lower()
        
        # ニックネームが同じかつ、どちらも意味のある名前の場合
        if nickname1 and nickname2 and len(nickname1) > 3 and nickname1 == nickname2:
            return True
        
        # その他の判定ロジック（メールアドレスなど）は必要に応じて追加
        return False
    except Exception:
        return False

def remove_duplicate_users(all_rankings: List[Dict]) -> List[Dict]:
    """重複ユーザーを効率的に除去"""
    try:
        # UIDをキーとしたマップを作成
        uid_map = {ranking["uid"]: ranking for ranking in all_rankings}
        
        # ニックネームベースの重複チェック（効率化版）
        nickname_groups = defaultdict(list)
        for ranking in all_rankings:
            nickname = ranking.get("nickname", "").strip().lower()
            if len(nickname) > 3:  # 意味のあるニックネームのみ
                nickname_groups[nickname].append(ranking)
        
        # 重複ユーザーを特定
        duplicates_to_remove = set()
        for nickname, group in nickname_groups.items():
            if len(group) > 1:
                # 最も活動的なユーザーを残し、他は除去
                group.sort(key=lambda x: x.get("total_points", 0), reverse=True)
                for duplicate in group[1:]:
                    duplicates_to_remove.add(duplicate["uid"])
        
        # 重複を除去したリストを返す
        filtered_rankings = [r for r in all_rankings if r["uid"] not in duplicates_to_remove]
        
        if duplicates_to_remove:
            logging.info(f"重複ユーザー {len(duplicates_to_remove)} 人を除去しました")
        
        return filtered_rankings
    except Exception as e:
        logging.error(f"重複ユーザー除去でエラー: {e}")
        return all_rankings

def update_rankings(request):
    """高性能ランキング更新のメイン処理"""
    try:
        # ドライランモードチェック
        dry_run = request.args.get('dry_run', 'false').lower() == 'true'
        
        logging.info("=== 高性能ランキング更新処理を開始します ===")
        start_time = datetime.datetime.now()
        
        # 1. 全ユーザープロフィールを一括取得
        logging.info("全ユーザープロフィールを取得中...")
        profiles_query = db.collection("users").stream()
        profiles = {}
        for doc in profiles_query:
            try:
                profiles[doc.id] = doc.to_dict()
            except Exception as e:
                logging.warning(f"プロフィール取得エラー (UID: {doc.id}): {e}")
                continue
        
        logging.info(f"{len(profiles)}件のプロフィールを取得しました")
        
        # 2. 全study_cardsを一括取得し、UIDごとにグループ化
        logging.info("全学習カードデータを取得・集計中...")
        cards_query = db.collection("study_cards").stream()
        user_cards = defaultdict(dict)
        total_cards_processed = 0
        
        for doc in cards_query:
            try:
                card_data = doc.to_dict()
                uid = card_data.get("uid")
                if uid and uid in profiles:  # プロフィールが存在するユーザーのみ
                    question_id = card_data.get("question_id", doc.id)
                    
                    # 既存の形式に変換
                    card = {
                        "history": card_data.get("history", []),
                        "performance": card_data.get("performance", {}),
                        "sm2_data": card_data.get("sm2_data", {})
                    }
                    user_cards[uid][question_id] = card
                    total_cards_processed += 1
            except Exception as e:
                logging.warning(f"カードデータ処理エラー (Doc: {doc.id}): {e}")
                continue
        
        logging.info(f"{len(user_cards)}人分、{total_cards_processed}枚の学習カードデータを集計しました")
        
        # 3. 各ユーザーのスコアを並列計算
        logging.info("各ユーザーのランキングスコアを計算中...")
        all_rankings = []
        processed_users = 0
        error_users = 0
        
        for uid, user_profile in profiles.items():
            try:
                nickname = user_profile.get("nickname", f"ユーザー{uid[:8]}")
                cards = user_cards.get(uid, {})
                
                # 学習データがないユーザーはスキップ
                if not cards:
                    continue
                
                # スコア計算
                weekly_points = calculate_weekly_points(cards)
                total_points, total_problems, accuracy_rate = calculate_total_points(cards)
                mastery_score, expert_cards, advanced_cards, total_cards, avg_ef = calculate_mastery_score(cards)
                
                # 最低条件チェック（データ品質担保）
                if total_problems < 3:  # 最低3問は解答している必要がある
                    continue
                
                ranking_data = {
                    "uid": uid,
                    "nickname": nickname,
                    "weekly_points": weekly_points,
                    "total_points": total_points,
                    "total_problems": total_problems,
                    "accuracy_rate": accuracy_rate,
                    "mastery_score": mastery_score,
                    "expert_cards": expert_cards,
                    "advanced_cards": advanced_cards,
                    "total_cards": total_cards,
                    "avg_ef": avg_ef,
                    "last_updated": firestore.SERVER_TIMESTAMP
                }
                
                all_rankings.append(ranking_data)
                processed_users += 1
                
            except Exception as e:
                error_users += 1
                logging.warning(f"ユーザー {uid} のスコア計算エラー: {e}")
                continue
        
        logging.info(f"スコア計算完了: 成功 {processed_users}人、エラー {error_users}人")
        
        # 4. 重複ユーザーの除去
        logging.info("重複ユーザーを除去中...")
        all_rankings = remove_duplicate_users(all_rankings)
        logging.info(f"重複除去後: {len(all_rankings)}人")
        
        # 5. ランキングをソートし、順位を付与
        logging.info("ランキングを計算中...")
        
        # 週間ランキング（週間ポイント > 0 かつ 最低5問）
        weekly_ranking = sorted(
            [u for u in all_rankings if u["weekly_points"] > 0 and u["total_problems"] >= 5],
            key=lambda x: x["weekly_points"], reverse=True
        )
        
        # 総合ランキング（総ポイント > 0 かつ 最低10問）
        total_ranking = sorted(
            [u for u in all_rankings if u["total_points"] > 0 and u["total_problems"] >= 10],
            key=lambda x: x["total_points"], reverse=True
        )
        
        # 習熟度ランキング（習熟度スコア > 0 かつ 最低30問）
        mastery_ranking = sorted(
            [u for u in all_rankings if u["mastery_score"] > 0 and u["total_cards"] >= 30],
            key=lambda x: x["mastery_score"], reverse=True
        )
        
        logging.info(f"ランキング人数 - 週間: {len(weekly_ranking)}, 総合: {len(total_ranking)}, 習熟度: {len(mastery_ranking)}")
        
        # 6. ドライランチェック
        if dry_run:
            logging.info("=== ドライランモード: データベース更新をスキップ ===")
            processing_time = (datetime.datetime.now() - start_time).total_seconds()
            return {
                "status": "success (dry_run)",
                "message": "ランキング計算が正常に完了しました（ドライラン）",
                "stats": {
                    "total_users": len(profiles),
                    "processed_users": processed_users,
                    "error_users": error_users,
                    "weekly_ranking_users": len(weekly_ranking),
                    "total_ranking_users": len(total_ranking),
                    "mastery_ranking_users": len(mastery_ranking),
                    "processing_time_seconds": processing_time
                }
            }, 200
        
        # 7. Firestoreへ効率的なバッチ書き込み
        logging.info("Firestoreへバッチ書き込み中...")
        
        # Firestoreのバッチサイズ制限（500操作）を考慮した分割処理
        def batch_write_rankings(collection_name: str, rankings: List[Dict], batch_size: int = 400):
            """バッチサイズを考慮した効率的な書き込み"""
            total_written = 0
            
            # 書き込むデータがない場合はスキップ
            if not rankings:
                return 0
            
            for i in range(0, len(rankings), batch_size):
                batch = db.batch()
                chunk = rankings[i:i + batch_size]
                
                for rank, data in enumerate(chunk, start=i + 1):
                    doc_ref = db.collection(collection_name).document(data["uid"])
                    batch.set(doc_ref, {**data, "rank": rank})
                
                batch.commit()
                total_written += len(chunk)
                logging.info(f"{collection_name}: {total_written}/{len(rankings)} 件書き込み完了")
            
            return total_written
        
        # 各ランキングを書き込み
        weekly_written = batch_write_rankings("weekly_ranking", weekly_ranking)
        total_written = batch_write_rankings("total_ranking", total_ranking)
        mastery_written = batch_write_rankings("mastery_ranking", mastery_ranking)
        
        # 更新ステータスを記録
        status_ref = db.collection("ranking_status").document("daily")
        status_ref.set({
            "updated_at": firestore.SERVER_TIMESTAMP,
            "updated_at_jst": datetime.datetime.now(JST).isoformat(),
            "total_users": len(profiles),
            "processed_users": processed_users,
            "weekly_ranking_users": weekly_written,
            "total_ranking_users": total_written,
            "mastery_ranking_users": mastery_written,
            "processing_time_seconds": (datetime.datetime.now() - start_time).total_seconds()
        })
        
        processing_time = (datetime.datetime.now() - start_time).total_seconds()
        
        logging.info("=== ランキング更新処理が正常に完了しました ===")
        logging.info(f"処理時間: {processing_time:.2f}秒")
        
        # UIステータス保存（ドライランでも実行）
        try:
            status_doc = {
                'updated_at_jst': datetime.datetime.now(JST),
                'total_users': total_written,
                'mastery_users': mastery_written,
                'processing_time_seconds': processing_time,
                'dry_run': dry_run,
                'status': 'success'
            }
            db.collection('ranking_status').document('daily').set(status_doc)
            logging.info("UI更新ステータスを保存しました（ドライランモード）")
        except Exception as e:
            logging.error(f"UI更新ステータス保存エラー（ドライランモード）: {e}")
        
        return {
            "status": "success",
            "message": "ランキング更新が正常に完了しました",
            "stats": {
                "total_users": len(profiles),
                "processed_users": processed_users,
                "error_users": error_users,
                "weekly_ranking_users": weekly_written,
                "total_ranking_users": total_written,
                "mastery_ranking_users": mastery_written,
                "processing_time_seconds": processing_time
            }
        }, 200
        
    except Exception as e:
        logging.error(f"ランキング更新処理全体でエラーが発生しました: {e}")
        logging.error(traceback.format_exc()) # スタックトレースをログに出力
        return {
            "status": "error",
            "message": f"内部サーバーエラーが発生しました: {e}"
        }, 500


# === モジュールインポート関連 ===

def setup_python_path():
    """Python パスを設定して my_llm_app モジュールをインポート可能にする"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    my_llm_app_path = os.path.join(current_dir, 'my_llm_app')
    
    if my_llm_app_path not in sys.path:
        sys.path.insert(0, my_llm_app_path)
    
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)


def import_ranking_updater():
    """ranking_updater モジュールを動的にインポート"""
    try:
        setup_python_path()
        
        # my_llm_app モジュールからインポート
        from modules.ranking_updater import update_all_rankings, should_update_today  # type: ignore
        return update_all_rankings, should_update_today
    except ImportError as e:
        logger.error(f"Failed to import ranking_updater: {e}")
        logger.error(f"Current sys.path: {sys.path}")
        raise

# === Firebase Callable Function Helpers ===

def handle_cors(request: Request):
    """CORSヘッダーを処理する"""
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization',
            'Access-Control-Max-Age': '3600'
        }
        return ('', 204, headers)
    
    headers = {
        'Access-Control-Allow-Origin': '*'
    }
    return headers

def verify_auth_and_get_data(request: Request) -> Tuple[str, Dict[str, Any]]:
    """
    認証トークンを検証し、リクエストデータを取得する
    Returns: (uid, data)
    Raises: ValueError if auth fails or data is invalid
    """
    # Authorizationヘッダーの確認
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        raise ValueError("Unauthenticated: No token provided")
    
    id_token = auth_header.split('Bearer ')[1]
    
    try:
        decoded_token = auth.verify_id_token(id_token)
        uid = decoded_token['uid']
    except Exception as e:
        raise ValueError(f"Unauthenticated: Invalid token - {e}")
    
    # リクエストデータの取得 (Callable形式: {"data": ...})
    try:
        request_json = request.get_json(silent=True)
        if request_json and 'data' in request_json:
            data = request_json['data']
        else:
            data = request_json or {}
    except Exception:
        data = {}
        
    return uid, data

def create_callable_response(result: Any) -> Tuple[Any, int, Dict[str, str]]:
    """Callable形式のレスポンスを作成する ({"result": ...})"""
    return (
        jsonify({"result": result}),
        200,
        {'Access-Control-Allow-Origin': '*'}
    )

def create_error_response(code: str, message: str, status: int = 500) -> Tuple[Any, int, Dict[str, str]]:
    """エラーレスポンスを作成する"""
    return (
        jsonify({
            "error": {
                "status": code,
                "message": message
            }
        }),
        status,
        {'Access-Control-Allow-Origin': '*'}
    )


# === Cloud Functions エンドポイント ===

@functions_framework.http
def updateRankings(request: Request) -> Dict[str, Any]:
    """
    HTTP トリガー関数 - ランキング更新
    
    クエリパラメータ:
    - force: "true" で強制実行（通常の3時チェックを無視）
    - dry_run: "true" でドライラン（実際の更新は行わない）
    """
    start_time = datetime.datetime.now(JST)
    dry_run = request.args.get('dry_run', 'false').lower() == 'true'
    force = request.args.get('force', '').lower() == 'true'
    
    logger.info(f"ランキング更新リクエスト受信: force={force}, dry_run={dry_run}")
    
    if dry_run:
        # ドライランモードではこのファイル内の計算ロジックを直接使用
        logger.info("ドライランモードで実行します。")
        return update_rankings(request)
        
    # 通常モードでは外部モジュールを使用
    try:
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
                    'timestamp': start_time.isoformat()
                }
        
        # 実際のランキング更新実行
        logger.info("ランキング更新実行中 (module: ranking_updater)...")
        update_result = update_all_rankings()
        
        end_time = datetime.datetime.now(JST)
        execution_time = (end_time - start_time).total_seconds()
        
        # UI用の更新ステータスをFirestoreに保存
        try:
            status_doc = {
                "updated_at_jst": start_time.strftime("%Y年%m月%d日 %H:%M"),
                "total_users": update_result.get("processed", 0),
                "processing_time_seconds": execution_time,
                "updated_at": start_time.isoformat(),
                "last_update_date": start_time.strftime("%Y-%m-%d")
            }
            db.collection("ranking_status").document("daily").set(status_doc, merge=True)
            logger.info("ランキング更新ステータスをFirestoreに保存しました")
        except Exception as e:
            logger.error(f"ステータス保存エラー: {e}")
        
        result = {
            'status': 'success',
            'message': 'ランキング更新が正常に完了しました',
            'data': update_result,
            'timestamp': start_time.isoformat(),
            'execution_time_seconds': execution_time
        }
        
        logger.info(f"ランキング更新完了: {update_result}")
        logger.info(f"実行時間: {execution_time:.2f}秒")
        
        return result
        
    except Exception as e:
        error_msg = f"ランキング更新でエラーが発生しました: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        
        return {
            'status': 'error',
            'message': error_msg,
            'error_details': str(e),
            'timestamp': start_time.isoformat()
        }, 500

@functions_framework.http
def healthCheck(request: Request) -> Dict[str, Any]:
    """ヘルスチェック用エンドポイント"""
    current_time = datetime.datetime.now(JST)
    try:
        # Firebase接続チェック
        db.collection('_health_check').document('test').get()
        firebase_ok = 'ok'
    except Exception as e:
        firebase_ok = f'error: {e}'

    # モジュールインポートチェック
    modules_ok = 'ok'
    should_update = None
    try:
        _, should_update_today_func = import_ranking_updater()
        should_update = should_update_today_func()
    except Exception as e:
        logger.warning(f"Module import test failed: {e}")
        modules_ok = 'error'

    return {
        'status': 'healthy' if firebase_ok == 'ok' else 'unhealthy',
        'timestamp': current_time.isoformat(),
        'timezone': 'Asia/Tokyo',
        'firebase_connection': firebase_ok,
        'modules_import': modules_ok,
        'should_update_today': should_update,
        'function_name': os.environ.get('K_SERVICE', 'dental-ranking-functions'),
        'version': '1.0.2' # バージョンを更新
    }

@functions_framework.http
def getDailyQuiz(request: Request) -> Any:
    """
    復習対象のカードを取得する (Callable)
    """
    # CORS対応
    cors_res = handle_cors(request)
    if isinstance(cors_res, tuple):
        return cors_res
    
    try:
        # 認証とデータ取得
        uid, _ = verify_auth_and_get_data(request)
        logger.info(f"Processing getDailyQuiz for user: {uid}")
        
        # 復習対象カード取得
        now = datetime.datetime.now(datetime.timezone.utc)
        
        # Firestoreクエリ
        # sm2_data.due_date <= now
        cards_ref = db.collection("study_cards")
        query = cards_ref.where("uid", "==", uid)\
                         .where("sm2_data.due_date", "<=", now)\
                         .order_by("sm2_data.due_date")\
                         .limit(20)
        
        docs = query.stream()
        
        review_question_ids = []
        for doc in docs:
            data = doc.to_dict()
            if 'question_id' in data:
                review_question_ids.append(data['question_id'])
                
        # 新規問題（今回は簡易実装で空リスト）
        new_question_ids = []
        
        all_question_ids = review_question_ids + new_question_ids
        
        logger.info(f"User {uid}: Returning {len(all_question_ids)} questions")
        
        return create_callable_response({
            "success": True,
            "questionIds": all_question_ids,
            "reviewCount": len(review_question_ids),
            "newCount": len(new_question_ids),
            "reviewCards": review_question_ids,
            "newCards": new_question_ids
        })
        
    except ValueError as e:
        logger.warning(f"Auth error in getDailyQuiz: {e}")
        return create_error_response("unauthenticated", str(e), 401)
    except Exception as e:
        logger.error(f"Error in getDailyQuiz: {e}")
        logger.error(traceback.format_exc())
        return create_error_response("internal", "An error occurred while fetching the quiz")


        return create_error_response("internal", "An error occurred while fetching the quiz")

@functions_framework.http
def logStudyActivity(request: Request) -> Any:
    """
    学習活動を記録する (Callable)
    """
    cors_res = handle_cors(request)
    if isinstance(cors_res, tuple):
        return cors_res
        
    try:
        uid, data = verify_auth_and_get_data(request)
        logger.info(f"Processing logStudyActivity for user: {uid}")
        
        question_id = data.get('questionId')
        quality = data.get('quality')
        is_correct = data.get('isCorrect', False)
        
        if not question_id or quality is None:
            return create_error_response("invalid-argument", "questionId and quality are required", 400)
            
        # SM2アルゴリズムのインポート
        setup_python_path()
        from my_llm_app.utils import SM2Algorithm
        
        # カード取得
        card_ref = db.collection("study_cards").document(f"{uid}_{question_id}")
        card_doc = card_ref.get()
        
        now = datetime.datetime.now(datetime.timezone.utc)
        
        if card_doc.exists:
            card_data = card_doc.to_dict()
        else:
            # 新規カード作成
            card_data = {
                "uid": uid,
                "question_id": question_id,
                "sm2_data": {
                    "n": 0,
                    "ef": 2.5,
                    "interval": 0,
                    "due_date": now
                },
                "performance": {
                    "total_attempts": 0,
                    "correct_attempts": 0,
                    "avg_quality": 0.0,
                    "last_quality": 0
                },
                "metadata": {
                    "created_at": now,
                    "updated_at": now,
                    "subject": "未分類"
                },
                "history": []
            }
            
        # SM2更新のためのデータ準備（スキーマ変換）
        sm2_data = card_data.get("sm2_data", {})
        
        # Python utils.py は EF, n, I を期待する
        # TS/Firestore は ef, n, interval を持っている
        sm2_params = {
            "EF": sm2_data.get("ef", 2.5),
            "n": sm2_data.get("n", 0),
            "I": sm2_data.get("interval", 0),
            "history": card_data.get("history", [])
        }
        
        # SM2更新実行
        # utils.pyのsm2_updateは辞書を更新して返す
        updated_params = SM2Algorithm.sm2_update(sm2_params, quality, now)
        
        # 結果をFirestoreスキーマに戻す
        new_ef = updated_params.get("EF", 2.5)
        new_n = updated_params.get("n", 0)
        new_interval = updated_params.get("I", 0)
        next_review_iso = updated_params.get("next_review")
        
        if next_review_iso:
            next_review_dt = datetime.datetime.fromisoformat(next_review_iso)
        else:
            next_review_dt = now + datetime.timedelta(days=new_interval)
            
        # sm2_data更新
        card_data["sm2_data"] = {
            "n": new_n,
            "ef": new_ef,
            "interval": new_interval,
            "due_date": next_review_dt,
            "last_studied": now
        }
        
        # history更新
        card_data["history"] = updated_params.get("history", [])
        
        # performance更新
        perf = card_data.get("performance", {})
        total_attempts = perf.get("total_attempts", 0) + 1
        correct_attempts = perf.get("correct_attempts", 0) + (1 if is_correct else 0)
        avg_quality = perf.get("avg_quality", 0)
        # 平均品質の更新
        new_avg_quality = ((avg_quality * (total_attempts - 1)) + quality) / total_attempts
        
        card_data["performance"] = {
            "total_attempts": total_attempts,
            "correct_attempts": correct_attempts,
            "avg_quality": new_avg_quality,
            "last_quality": quality
        }
        
        card_data["metadata"]["updated_at"] = now
        
        # 保存
        card_ref.set(card_data)
        
        # 日次分析サマリー更新 (analytics_summary)
        today_str = now.astimezone(JST).strftime("%Y-%m-%d")
        summary_ref = db.collection("analytics_summary").document(f"{uid}_daily_{today_str}")
        
        summary_ref.set({
            "uid": uid,
            "period": "daily",
            "date": today_str,
            "metrics": {
                "questions_answered": firestore.Increment(1),
                "correct_answers": firestore.Increment(1 if is_correct else 0),
                "study_time_minutes": firestore.Increment(1)
            },
            "updated_at": now
        }, merge=True)
        
        # ユーザー統計更新
        db.collection("users").document(uid).set({
            "statistics": {
                "total_questions_answered": firestore.Increment(1),
                "total_correct_answers": firestore.Increment(1 if is_correct else 0),
                "last_study_date": today_str
            }
        }, merge=True)
        
        return create_callable_response({
            "success": True,
            "updatedCard": card_data
        })
        
    except ValueError as e:
        return create_error_response("unauthenticated", str(e), 401)
    except Exception as e:
        logger.error(f"Error in logStudyActivity: {e}")
        logger.error(traceback.format_exc())
        return create_error_response("internal", "An error occurred while logging study activity")

@functions_framework.http
def submitStudySession(request: Request) -> Any:
    """
    学習セッションを記録する (Callable)
    """
    cors_res = handle_cors(request)
    if isinstance(cors_res, tuple):
        return cors_res
        
    try:
        uid, data = verify_auth_and_get_data(request)
        
        session_id = data.get('sessionId')
        responses = data.get('responses', [])
        start_time = data.get('startTime')
        end_time = data.get('endTime')
        
        if not session_id:
            return create_error_response("invalid-argument", "sessionId is required", 400)
            
        now = datetime.datetime.now(datetime.timezone.utc)
        
        # セッションデータ保存
        session_data = {
            "uid": uid,
            "session_id": session_id,
            "start_time": datetime.datetime.fromisoformat(start_time.replace('Z', '+00:00')) if start_time else now,
            "end_time": datetime.datetime.fromisoformat(end_time.replace('Z', '+00:00')) if end_time else now,
            "total_questions": len(responses),
            "correct_answers": sum(1 for r in responses if r.get('isCorrect')),
            "responses": responses,
            "created_at": now
        }
        
        db.collection("study_sessions").document(session_id).set(session_data)
        
        # 個別の回答処理は logStudyActivity で行われるため、ここではセッション記録のみ
        
        return create_callable_response({
            "success": True,
            "sessionId": session_id,
            "processed": len(responses)
        })
        
    except ValueError as e:
        return create_error_response("unauthenticated", str(e), 401)
    except Exception as e:
        logger.error(f"Error in submitStudySession: {e}")
        return create_error_response("internal", "Failed to submit study session")
# === ローカルでのテスト実行用 ===
def main():
    """ローカルでのテスト実行用"""
    app = Flask(__name__)
    
    @app.route('/update-rankings')
    def local_update():
        return updateRankings(Request(environ=request.environ))
    
    @app.route('/health')
    def local_health():
        return healthCheck(Request(environ=request.environ))
        
    @app.route('/getDailyQuiz', methods=['POST'])
    def local_get_quiz():
        return getDailyQuiz(Request(environ=request.environ))
        
    @app.route('/logStudyActivity', methods=['POST'])
    def local_log_activity():
        return logStudyActivity(Request(environ=request.environ))
        
    @app.route('/submitStudySession', methods=['POST'])
    def local_submit_session():
        return submitStudySession(Request(environ=request.environ))
        
    print("ローカルテストサーバーを起動します: http://localhost:8080")
    print("エンドポイント:")
    print("  - http://localhost:8080/health")
    print("  - POST http://localhost:8080/getDailyQuiz")
    
    # Flaskアプリを直接実行
    app.run(host='localhost', port=8080, debug=True, use_reloader=False)

if __name__ == '__main__':
    print("Starting main with app.run()...")
    main()
