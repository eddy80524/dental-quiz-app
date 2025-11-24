"""
Firestoreデータベース関連の機能を提供するモジュール

主な変更点:
- 全てのFirestoreアクセスをuidベースに統一
- Firestoreの読み取り回数を最小化
- 複雑なデータ統合ロジックを削除（migrate_data.pyに移行）
- パフォーマンス最適化（キャッシュ、タイムアウト設定）
"""

import streamlit as st
import json
import datetime
import time
import os
import collections.abc
from typing import Dict, Any, Optional, List
import firebase_admin
from firebase_admin import credentials, firestore, storage
from google.cloud.firestore_v1 import FieldFilter
from google.cloud import firestore as gcp_firestore



@st.cache_data(ttl=300)
def cached_load_user_cards(uid: str) -> Dict[str, Any]:
    """ユーザーのカードデータをキャッシュ付きで読み込み"""
    if not uid:
        return {}
    
    try:
        # Firestoreクライアントを直接取得
        # 注意: firestore.client() はシングルトン的に動作するため再取得コストは低い
        db = firestore.client()
        
        # 最適化されたstudy_cardsコレクションから取得
        cards_query = db.collection("study_cards").where("uid", "==", uid)
        cards_docs = cards_query.get()
        
        cards = {}
        for doc in cards_docs:
            if doc.exists:
                card_data = doc.to_dict()
                
                # datetimeオブジェクトをISO文字列に変換（キャッシュシリアライズ対応）
                # 再帰的に変換するのはコストがかかるため、主要なフィールドのみ対応
                if "metadata" in card_data:
                    meta = card_data["metadata"]
                    if isinstance(meta.get("created_at"), datetime.datetime):
                        meta["created_at"] = meta["created_at"].isoformat()
                    if isinstance(meta.get("updated_at"), datetime.datetime):
                        meta["updated_at"] = meta["updated_at"].isoformat()
                
                if "history" in card_data and isinstance(card_data["history"], list):
                    for h in card_data["history"]:
                        if isinstance(h.get("timestamp"), datetime.datetime):
                            h["timestamp"] = h["timestamp"].isoformat()
                
                question_id = card_data.get("question_id")
                if not question_id:
                    # フォールバック
                    try:
                        doc_id = str(doc.id)
                        if "_" in doc_id:
                            question_id = doc_id.split("_", 1)[1]
                        else:
                            question_id = doc_id
                    except Exception:
                        question_id = None
                
                if question_id:
                    cards[question_id] = card_data
        
        return cards
        
    except Exception as e:
        print(f"[ERROR] キャッシュ付きカード読み込みエラー: {e}")
        return {}


class FirestoreManager:
    """Firestoreデータベース操作を管理するクラス"""
    
    def __init__(self):
        self.db = None
        self.bucket = None
        self._initialize_firebase()
    
    def _initialize_firebase(self):
        """Firebase初期化"""
        if not hasattr(st.session_state, 'firebase_initialized'):
            firebase_creds = self._load_service_account_config()

            project_id = self._resolve_project_id(firebase_creds)
            storage_bucket = self._resolve_storage_bucket(firebase_creds, project_id)
            options = {}
            if storage_bucket:
                options["storageBucket"] = storage_bucket
            if project_id:
                options["projectId"] = project_id

            creds = credentials.Certificate(firebase_creds)

            try:
                app = firebase_admin.get_app()
            except ValueError:
                app = firebase_admin.initialize_app(
                    creds,
                    options or None
                )

            self.db = firestore.client(app=app)
            try:
                self.bucket = storage.bucket(app=app)
            except Exception:
                self.bucket = None
            st.session_state.firebase_initialized = True
        else:
            # 既に初期化済みの場合は既存のクライアントを取得
            self.db = firestore.client()
            try:
                self.bucket = storage.bucket()
            except Exception:
                self.bucket = None
    
    def _to_dict(self, obj):
        """オブジェクトを辞書に変換"""
        if isinstance(obj, collections.abc.Mapping):
            return {k: self._to_dict(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._to_dict(i) for i in obj]
        else:
            return obj
    
    def _load_service_account_config(self) -> Dict[str, Any]:
        """st.secrets からサービスアカウント情報を取得"""
        firebase_config: Optional[Dict[str, Any]] = None
        try:
            firebase_config = self._to_dict(st.secrets.get("firebase", {}))
            if not firebase_config:
                firebase_config = self._to_dict(st.secrets.get("firebase_credentials", {}))
        except Exception:
            firebase_config = None

        if not self._is_service_account(firebase_config):
            raise RuntimeError(
                "Firebase service account credentials are not configured. "
                "Please set the full service account JSON under [firebase] in secrets.toml."
            )

        return firebase_config

    def _resolve_project_id(self, firebase_creds):
        """プロジェクトIDを多段階で解決"""
        candidates: List[Optional[str]] = []

        if firebase_creds:
            candidates.extend([
                firebase_creds.get("project_id"),
                firebase_creds.get("projectId"),
            ])

        try:
            candidates.append(st.secrets.get("firebase_project_id"))
            candidates.append(st.secrets.get("project_id"))
        except Exception:
            pass

        candidates.append(os.environ.get("FIREBASE_PROJECT_ID"))
        candidates.append(os.environ.get("GOOGLE_CLOUD_PROJECT"))
        candidates.append(os.environ.get("GCLOUD_PROJECT"))
        candidates.append("dent-ai-4d8d8")

        for candidate in candidates:
            if candidate:
                pid = str(candidate).strip()
                if pid:
                    return pid
        return None

    def _resolve_storage_bucket(self, firebase_creds, project_id):
        """バケット名を正規化"""
        raw = None
        try:
            raw = st.secrets.get("firebase_storage_bucket")
        except Exception:
            raw = None

        if not raw and firebase_creds:
            raw = firebase_creds.get("storage_bucket") \
                  or firebase_creds.get("storageBucket")

        if not raw:
            raw = os.environ.get("FIREBASE_STORAGE_BUCKET")

        if not raw:
            pid = project_id or (firebase_creds or {}).get("project_id") \
                  or (firebase_creds or {}).get("projectId") \
                  or "dent-ai-4d8d8"
            raw = f"{pid}.firebasestorage.app"

        b = str(raw).strip()
        b = b.replace("gs://", "").split("/")[0]
        return b

    def _is_service_account(self, firebase_config: Optional[Dict[str, Any]]) -> bool:
        """サービスアカウント形式かを判定"""
        if not firebase_config or not isinstance(firebase_config, dict):
            return False

        required_fields = ["client_email", "private_key", "token_uri"]
        for field in required_fields:
            value = firebase_config.get(field)
            if not value or not str(value).strip():
                return False

        # private_key の整形: 改行がエスケープされているケースに対応
        private_key = firebase_config.get("private_key")
        if isinstance(private_key, str) and "\\n" in private_key:
            firebase_config["private_key"] = private_key.replace("\\n", "\n")

        return True
    
    def load_user_profile(self, uid: str) -> Dict[str, Any]:
        """ユーザーの基本プロフィール情報のみを高速読み込み（uid統一版）"""
        start = time.time()
        
        if not uid:
            return {"email": "", "settings": {"new_cards_per_day": 10}}
        
        try:
            # /users/{uid} から基本プロフィールのみ読み込み
            doc_ref = self.db.collection("users").document(uid)
            doc = doc_ref.get(timeout=5)
            
            if doc.exists:
                data = doc.to_dict()
                return data
            else:
                # 新規ユーザーのデフォルトプロフィール作成
                email = st.session_state.get("email", "")
                default_profile = {
                    "email": email,
                    "uid": uid,  # UIDを明示的に保存
                    "createdAt": datetime.datetime.utcnow().isoformat(),
                    "settings": {"new_cards_per_day": 10}
                }
                doc_ref.set(default_profile)
                return default_profile
                
        except Exception as e:
            print(f"[ERROR] ユーザープロフィール読み込みエラー: {e}")
            return {"email": "", "settings": {"new_cards_per_day": 10}}
    
    def load_user_cards(self, uid: str) -> Dict[str, Any]:
        """ユーザーのカードデータを読み込み（uid統一版）"""
        start = time.time()
        
        if not uid:
            return {}
        
        try:
            cards_ref = self.db.collection("users").document(uid).collection("userCards")
            cards_docs = cards_ref.stream()
            
            cards = {}
            for doc in cards_docs:
                cards[doc.id] = doc.to_dict()
            
            return cards
            
        except Exception as e:
            print(f"[ERROR] カードデータ読み込みエラー: {e}")
            return {}
    
    def load_session_state(self, uid: str) -> Dict[str, Any]:
        """セッション状態を読み込み（uid統一版）（詳細デバッグ強化版）"""
        start = time.time()
        
        if not uid:
            return {
                "main_queue": [],
                "question_queue": [],
                "short_term_review_queue": [],
                "current_q_group": []
            }
        
        try:
            session_ref = self.db.collection("users").document(uid).collection("sessionState").document("current")
            session_doc = session_ref.get(timeout=5)
            
            if session_doc.exists:
                session_data = session_doc.to_dict()
                
                # メタデータの詳細確認
                session_metadata = session_data.get("session_metadata", {})
                
                # 各キューの詳細確認
                main_queue_raw = session_data.get("main_queue", [])
                current_q_group_raw = session_data.get("current_q_group", [])
                question_queue_raw = session_data.get("question_queue", [])
                short_term_raw = session_data.get("short_term_review_queue", [])
                
                # Firestore対応：JSON文字列を元のリスト形式に復元
                def deserialize_queue(queue, queue_name="unknown"):
                    deserialized = []
                    for i, item in enumerate(queue):
                        try:
                            if isinstance(item, str):
                                parsed_item = json.loads(item)
                                deserialized.append(parsed_item)
                            elif isinstance(item, list):
                                deserialized.append(item)
                            else:
                                deserialized.append(item)
                        except (json.JSONDecodeError, TypeError) as e:
                            continue
                    return deserialized
                
                result = {
                    "current_q_group": deserialize_queue(current_q_group_raw, "current_q_group"),
                    "main_queue": deserialize_queue(main_queue_raw, "main_queue"),
                    "question_queue": deserialize_queue(question_queue_raw, "question_queue"),
                    "short_term_review_queue": short_term_raw,
                    
                    # セッションメタデータを追加
                    "session_metadata": session_metadata,
                    "session_type": session_metadata.get("session_type", ""),
                    "session_start_time": session_metadata.get("session_start_time", ""),
                    "current_question_index": session_metadata.get("current_question_index", 0),
                    "total_questions_answered": session_metadata.get("total_questions_answered", 0),
                    "is_active_session": session_metadata.get("is_active_session", False),
                    "last_activity_time": session_metadata.get("last_activity_time", "")
                }
                
                return result
            else:
                return {
                    "main_queue": [],
                    "question_queue": [],
                    "short_term_review_queue": [],
                    "current_q_group": []
                }
                
        except Exception as e:
            print(f"[ERROR] セッション状態読み込みエラー: {e}")
            print(f"[ERROR] エラータイプ: {type(e)}")
            import traceback
            print(f"[ERROR] スタックトレース:\n{traceback.format_exc()}")
            return {
                "main_queue": [],
                "short_term_review_queue": [],
                "current_q_group": []
            }
    
    def get_user_cards(self, uid: str) -> Dict[str, Any]:
        """ユーザーの学習カードデータを取得（キャッシュ対応版）"""
        try:
            # キャッシュされたデータを取得
            raw_cards = cached_load_user_cards(uid)
            
            cards = {}
            for question_id, card_data in raw_cards.items():
                try:
                    # 最適化後のデータ構造を旧形式に変換
                    converted_card = self._convert_optimized_card_to_legacy(card_data)
                    cards[question_id] = converted_card
                except Exception as conv_error:
                    continue
            
            return cards
            
        except Exception as e:
            print(f"[ERROR] ユーザーカード取得エラー: {e}")
            # フォールバック：旧構造も試行
            return self._get_user_cards_legacy(uid)
    
    def _convert_optimized_card_to_legacy(self, optimized_card: Dict[str, Any]) -> Dict[str, Any]:
        """最適化後のカードデータを旧形式に変換"""
        legacy_card = {}
        
        # 基本情報
        legacy_card["question_id"] = optimized_card.get("question_id")
        
        # レベル情報（metadata.original_levelから取得）
        metadata = optimized_card.get("metadata", {})
        legacy_card["level"] = metadata.get("original_level", -1)
        
        # SM2データ（sm2_dataからsm2に変換）
        sm2_data = optimized_card.get("sm2_data", {})
        legacy_card["sm2"] = {
            "n": sm2_data.get("n", 0),
            "ef": sm2_data.get("ef", 2.5),
            "interval": sm2_data.get("interval", 1),
            "due_date": sm2_data.get("due_date"),
            "last_studied": sm2_data.get("last_studied")
        }
        
        # パフォーマンスデータ
        performance = optimized_card.get("performance", {})
        legacy_card["performance"] = {
            "correct_attempts": performance.get("correct_attempts", 0),
            "total_attempts": performance.get("total_attempts", 0),
            "avg_quality": performance.get("avg_quality", 0),
            "last_quality": performance.get("last_quality", 0)
        }
        
        # 履歴データ
        legacy_card["history"] = optimized_card.get("history", [])
        
        # メタデータ
        legacy_card["difficulty"] = metadata.get("difficulty")
        legacy_card["subject"] = metadata.get("subject")
        legacy_card["updated_at"] = metadata.get("updated_at")
        legacy_card["created_at"] = metadata.get("created_at")
        
        return legacy_card
    
    def _get_user_cards_legacy(self, uid: str) -> Dict[str, Any]:
        """旧構造からの学習カードデータ取得（フォールバック用）"""
        try:
            cards_collection = self.db.collection("users").document(uid).collection("userCards")
            cards_docs = cards_collection.get(timeout=10)
            
            cards = {}
            for doc in cards_docs:
                if doc.exists:
                    cards[doc.id] = self._to_dict(doc.to_dict())
            
            return cards
            
        except Exception as e:
            print(f"[ERROR] レガシー構造からの取得も失敗: {e}")
            return {}
    
    def get_cards(self, uid: str) -> Dict[str, Any]:
        """ユーザーの学習カードデータを取得（get_user_cardsのエイリアス）"""
        return self.get_user_cards(uid)
    
    def save_user_card(self, uid: str, question_id: str, card_data: Dict[str, Any]):
        """単一カードデータを保存（最適化後構造対応版）"""
        if not uid or not question_id:
            return
        
        try:
            # 旧形式のcard_dataを最適化後の構造に変換
            optimized_card = self._convert_legacy_card_to_optimized(uid, question_id, card_data)
            
            # study_cardsコレクションに保存
            card_ref = self.db.collection("study_cards").document(f"{uid}_{question_id}")
            card_ref.set(optimized_card, merge=True)
        except Exception as e:
            print(f"[ERROR] カード保存エラー: {e}")
    
    def _convert_legacy_card_to_optimized(self, uid: str, question_id: str, legacy_card: Dict[str, Any]) -> Dict[str, Any]:
        """旧形式のカードデータを最適化後の構造に変換"""
        optimized_card = {
            "uid": uid,
            "question_id": question_id,
            "metadata": {
                "original_level": legacy_card.get("level", -1),
                "difficulty": legacy_card.get("difficulty"),
                "subject": legacy_card.get("subject"),
                "updated_at": legacy_card.get("updated_at"),
                "created_at": legacy_card.get("created_at", firestore.SERVER_TIMESTAMP)
            },
            "sm2_data": {},
            "performance": {
                "correct_attempts": 0,
                "total_attempts": 0,
                "avg_quality": 0,
                "last_quality": 0
            },
            "history": legacy_card.get("history", [])
        }
        
        # SM2データの変換
        sm2_data = legacy_card.get("sm2", {})
        if sm2_data:
            optimized_card["sm2_data"] = {
                "n": sm2_data.get("n", 0),
                "ef": sm2_data.get("ef", 2.5),
                "interval": sm2_data.get("interval", 1),
                "due_date": sm2_data.get("due_date"),
                "last_studied": sm2_data.get("last_studied")
            }
        
        # パフォーマンスデータの変換
        performance_data = legacy_card.get("performance", {})
        if performance_data:
            optimized_card["performance"] = {
                "correct_attempts": performance_data.get("correct_attempts", 0),
                "total_attempts": performance_data.get("total_attempts", 0),
                "avg_quality": performance_data.get("avg_quality", 0),
                "last_quality": performance_data.get("last_quality", 0)
            }
        
        return optimized_card
    
    def save_session_state(self, uid: str, session_data: Dict[str, Any]):
        """セッション状態を保存（uid統一版）"""
        if not uid:
            return
        
        try:
            # Firestore対応：ネストした配列をJSON文字列に変換
            def serialize_queue(queue):
                return [json.dumps(group) for group in queue]

            serialized_data = {
                "current_q_group": serialize_queue(session_data.get("current_q_group", [])),
                "main_queue": serialize_queue(session_data.get("main_queue", [])),
                "short_term_review_queue": session_data.get("short_term_review_queue", []),
                "result_log": session_data.get("result_log", {}),
                "last_updated": datetime.datetime.utcnow().isoformat(),
                
                # 演習セッション継続のための情報を追加
                "session_metadata": {
                    "session_type": session_data.get("session_metadata", {}).get("session_type", session_data.get("session_type", "")),
                    "session_start_time": session_data.get("session_metadata", {}).get("session_start_time", session_data.get("session_start_time", "")),
                    "current_question_index": session_data.get("session_metadata", {}).get("current_question_index", session_data.get("current_question_index", 0)),
                    "total_questions_answered": session_data.get("session_metadata", {}).get("total_questions_answered", session_data.get("total_questions_answered", 0)),
                    "is_active_session": session_data.get("session_metadata", {}).get("is_active_session", session_data.get("is_active_session", True)),
                    "last_activity_time": datetime.datetime.utcnow().isoformat()
                }
            }
            
            session_ref = self.db.collection("users").document(uid).collection("sessionState").document("current")
            session_ref.set(serialized_data, merge=True)
            
        except Exception as e:
            print(f"[ERROR] セッション状態保存エラー: {e}")
    
    def update_user_settings(self, uid: str, settings: Dict[str, Any]):
        """ユーザー設定を更新（uid統一版）"""
        if not uid:
            return
        
        try:
            user_ref = self.db.collection("users").document(uid)
            settings_update = {
                "settings": settings,
                "lastUpdated": datetime.datetime.utcnow().isoformat()
            }
            user_ref.update(settings_update)
        except Exception as e:
            print(f"[ERROR] ユーザー設定更新エラー: {e}")
    
    def check_user_permission(self, uid: str, permission_key: str) -> bool:
        """ユーザー権限をチェック（user_permissions コレクション使用）"""
        if not uid:
            return False
        
        try:
            # user_permissions コレクションから権限を取得
            doc_ref = self.db.collection("user_permissions").document(uid)
            doc = doc_ref.get()
            
            if doc.exists:
                data = doc.to_dict()
                result = bool(data.get(permission_key, False))
                return result
            else:
                return False
                
        except Exception as e:
            print(f"[ERROR] 権限チェックエラー: {e}")
            return False
    
    def grant_user_permission(self, uid: str, permission_key: str, value: bool = True):
        """ユーザーに権限を付与または剥奪"""
        if not uid:
            return False
        
        try:
            doc_ref = self.db.collection("user_permissions").document(uid)
            doc_ref.set({permission_key: value}, merge=True)
            return True
        except Exception as e:
            print(f"[ERROR] 権限設定エラー: {e}")
            return False
    
    def get_user_permissions(self, uid: str) -> Dict[str, bool]:
        """ユーザーの全権限を取得"""
        if not uid:
            return {}
        
        try:
            doc_ref = self.db.collection("user_permissions").document(uid)
            doc = doc_ref.get()
            
            if doc.exists:
                return doc.to_dict() or {}
            else:
                return {}
        except Exception as e:
            print(f"[ERROR] 権限取得エラー: {e}")
            return {}
    
    def list_all_user_permissions(self) -> Dict[str, Dict[str, bool]]:
        """全ユーザーの権限一覧を取得"""
        try:
            permissions_ref = self.db.collection("user_permissions")
            permissions_docs = list(permissions_ref.stream())
            
            result = {}
            for doc in permissions_docs:
                result[doc.id] = doc.to_dict() or {}
            
            return result
        except Exception as e:
            print(f"[ERROR] 全権限取得エラー: {e}")
            return {}
    
    def fetch_ranking_data_optimized(self, limit: int = 100) -> List[Dict[str, Any]]:
        """最適化されたランキングデータ取得（統計データ使用）"""
        try:
            # 統計データから直接取得（1回のクエリ）
            users_ref = self.db.collection("users").limit(limit)
            users_docs = users_ref.stream()
            
            ranking_data = []
            
            for doc in users_docs:
                user_data = doc.to_dict()
                stats = user_data.get("stats", {})
                
                # 統計データが存在しない場合はスキップ
                if not stats:
                    continue
                
                # 習熟度計算
                total_cards = stats.get("total_cards", 0)
                mastered_cards = stats.get("mastered_cards", 0)
                mastery_rate = mastered_cards / total_cards * 100 if total_cards > 0 else 0
                
                ranking_data.append({
                    "uid": doc.id,
                    "nickname": user_data.get("nickname", f"学習者{doc.id[:8]}"),
                    "weekly_points": stats.get("weekly_points", 0),
                    "total_points": stats.get("total_points", 0),
                    "mastery_rate": mastery_rate,
                    "total_cards": total_cards,
                    "mastered_cards": mastered_cards,
                    "last_updated": stats.get("last_updated")
                })
            
            # 週間ポイントでソート
            ranking_data.sort(key=lambda x: x["weekly_points"], reverse=True)
            
            return ranking_data
            
        except Exception as e:
            print(f"[ERROR] 最適化ランキング取得エラー: {e}")
            return []

    def fetch_ranking_data(self, limit: int = 100) -> List[Dict[str, Any]]:
        """ランキングデータ取得（最適化版を優先使用）"""
        try:
            # まず最適化版を試行
            optimized_data = self.fetch_ranking_data_optimized(limit)
            if optimized_data:
                return optimized_data
            
            # フォールバック：リアルタイム計算は重すぎるため廃止（空リストを返す）
            # フォールバック：リアルタイム計算は重すぎるため廃止（空リストを返す）
            return []
            
            # 旧フォールバックコード（無効化）
            # print("[FALLBACK] 統計データが不完全なため、リアルタイム計算実行")
            # return self.fetch_ranking_data_realtime(limit)
            
        except Exception as e:
            print(f"[ERROR] ランキングデータ取得エラー: {e}")
            return []

    def fetch_ranking_data_realtime(self, limit: int = 100) -> List[Dict[str, Any]]:
        """リアルタイムランキング計算（フォールバック用）"""
        try:
            today = datetime.datetime.now(datetime.timezone.utc)
            week_start = today - datetime.timedelta(days=today.weekday())
            week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
            week_end = week_start + datetime.timedelta(days=7)
            
            users_ref = self.db.collection("users").limit(limit)
            users_docs = users_ref.stream()
            
            ranking_data = []
            
            for doc in users_docs:
                try:
                    user_data = doc.to_dict()
                    if not user_data.get("email"):  # 有効なユーザーのみ
                        continue
                    
                    # ユーザーカードを取得してポイント計算
                    cards = self.load_user_cards(doc.id)
                    total_points = 0
                    weekly_points = 0
                    
                    for card in cards.values():
                        history = card.get("history", [])
                        for record in history:
                            quality = record.get("quality", 0)
                            timestamp_str = record.get("timestamp", "")
                            
                            # ポイント計算（正解で5点、部分正解で2点）
                            if quality >= 4:
                                points = 5
                            elif quality >= 2:
                                points = 2
                            else:
                                points = 0
                            
                            total_points += points
                            
                            # 週間ポイント計算
                            try:
                                timestamp = datetime.datetime.fromisoformat(timestamp_str)
                                if week_start <= timestamp < week_end:
                                    weekly_points += points
                            except (ValueError, TypeError):
                                continue
                    
                    # 習熟度計算（全期間の学習データから）
                    total_cards = len(cards)
                    if total_cards > 0:
                        # レベル4以上を習得済みとして計算
                        mastered_cards = sum(1 for card in cards.values() if card.get("level", 0) >= 4)
                        mastery_rate = mastered_cards / total_cards * 100
                    else:
                        mastery_rate = 0.0
                    
                    ranking_data.append({
                        "uid": doc.id,
                        "weekly_points": weekly_points,
                        "total_points": total_points,
                        "mastery_rate": mastery_rate
                    })
                    
                
                except Exception as e:
                    print(f"[ERROR] ユーザー {doc.id} のポイント計算エラー: {e}")
                    continue
            
            # 週間ポイントでソート
            ranking_data.sort(key=lambda x: x["weekly_points"], reverse=True)
            
            return ranking_data
            
        except Exception as e:
            print(f"[ERROR] リアルタイムランキング計算エラー: {e}")
            return []
    
    def get_secure_image_url(self, image_path: str, expires_in: int = 3600) -> Optional[str]:
        """Firebase Storageから署名付きURLを取得"""
        try:
            if not self.bucket:
                return None
            
            blob = self.bucket.blob(image_path)
            if not blob.exists():
                return None
            
            # 署名付きURLを生成（1時間有効）
            url = blob.generate_signed_url(
                expiration=datetime.datetime.utcnow() + datetime.timedelta(seconds=expires_in),
                method='GET'
            )
            return url
            
        except Exception as e:
            print(f"[ERROR] 画像URL取得エラー: {e}")
            return None

    def has_resumable_session(self, uid: str) -> bool:
        """ユーザーが再開可能な演習セッションを持っているかチェック"""
        if not uid:
            return False
        
        try:
            session_data = self.load_session_state(uid)
            # セッションメタデータから継続可能性をチェック
            session_metadata = session_data.get('session_metadata', {})
            
            # アクティブなセッションかつ問題キューが存在するかチェック
            is_active = session_metadata.get('is_active_session', False)
            
            # 複数の問題キューをチェック（後方互換性も考慮）
            has_questions = bool(
                session_data.get('question_queue', []) or 
                session_data.get('main_queue', []) or 
                session_data.get('current_q_group', [])
            )
            
            # 最終活動時間をチェック（24時間以内）
            last_activity = session_metadata.get('last_activity_time')
            if last_activity:
                try:
                    if isinstance(last_activity, str):
                        last_activity_dt = datetime.datetime.fromisoformat(last_activity.replace('Z', '+00:00'))
                    else:
                        last_activity_dt = last_activity
                    
                    # 24時間以内の活動かチェック
                    time_diff = datetime.datetime.now(datetime.timezone.utc) - last_activity_dt.replace(tzinfo=datetime.timezone.utc)
                    is_recent = time_diff.total_seconds() < 24 * 3600
                    
                    result = is_active and has_questions and is_recent
                    return result
                except Exception as e:
                    result = is_active and has_questions
                    return result
            
            result = is_active and has_questions
            return result
            
        except Exception as e:
            print(f"[ERROR] セッション継続確認エラー: {e}")
            return False

    def clear_session_state(self, uid: str) -> bool:
        """ユーザーのセッション状態をクリア"""
        if not uid:
            return False
        
        try:
            session_data = {
                'session_metadata': {
                    'is_active_session': False,
                    'session_type': None,
                    'last_activity_time': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    'session_cleared': True
                },
                'question_queue': [],
                'current_question_index': 0,
                'total_questions': 0,
                'session_answers': []
            }
            
            # セッション状態を保存
            result = self.save_session_state(uid, session_data)
            
            if result:
                pass
            
            return result
            
        except Exception as e:
            print(f"[ERROR] セッション状態クリアエラー: {e}")
            return False


# グローバルインスタンス
@st.cache_resource  # キャッシュを再有効化
def get_firestore_manager():
    """FirestoreManagerのシングルトンインスタンスを取得"""
    manager = FirestoreManager()
    return manager


# 後方互換性のための関数
def get_db():
    """Firestoreクライアントを取得（後方互換性）"""
    try:
        manager = get_firestore_manager()
        return manager.db
    except Exception as e:
        print(f"[ERROR] Firebase DB取得エラー: {e}")
        return None


def get_bucket():
    """Firebase Storageバケットを取得（後方互換性）"""
    try:
        manager = get_firestore_manager()
        return manager.bucket
    except Exception as e:
        print(f"[ERROR] Firebase Storage取得エラー: {e}")
        return None


def load_user_data_minimal(uid: str) -> Dict[str, Any]:
    """ユーザーの基本データを読み込み（uid統一版）"""
    manager = get_firestore_manager()
    profile = manager.load_user_profile(uid)
    cards = manager.load_user_cards(uid)
    
    return {
        **profile,
        "cards": cards
    }


def load_user_data_full(uid: str, cache_buster: int = 0) -> Dict[str, Any]:
    """ユーザーの全データを読み込み（uid統一版）"""
    manager = get_firestore_manager()
    
    profile = manager.load_user_profile(uid)
    cards = manager.load_user_cards(uid)
    session_state = manager.load_session_state(uid)
    
    return {
        "cards": cards,
        "main_queue": session_state["main_queue"],
        "short_term_review_queue": session_state["short_term_review_queue"],
        "current_q_group": session_state["current_q_group"],
        "new_cards_per_day": profile.get("settings", {}).get("new_cards_per_day", 10),
    }


def save_user_data(uid: str, question_id: str = None, updated_card_data: Dict[str, Any] = None, session_state: Dict[str, Any] = None):
    """ユーザーデータを保存（uid統一版・最適化）"""
    manager = get_firestore_manager()
    
    # 単一カードデータの更新
    if question_id and updated_card_data:
        manager.save_user_card(uid, question_id, updated_card_data)
    
    # セッション状態保存
    if session_state:
        manager.save_session_state(uid, session_state)
        
        # 設定の更新
        if session_state.get("settings_changed", False):
            settings = {
                "new_cards_per_day": session_state.get("new_cards_per_day", 10)
            }
            manager.update_user_settings(uid, settings)


def check_gakushi_permission(uid: str) -> bool:
    """学士試験アクセス権限をチェック（uid統一版・キャッシュ対応）"""
    try:
        # Streamlitのキャッシュを使用して権限データを保存（表示なし）
        @st.cache_data(ttl=300, show_spinner=False)  # 5分間キャッシュ、スピナー非表示
        def _cached_permission_check(uid: str) -> bool:
            manager = get_firestore_manager()
            return manager.check_user_permission(uid, "can_access_gakushi")
        
        return _cached_permission_check(uid)
    except Exception as e:
        # エラー時は安全側に倒してTrueを返す
        return True


def grant_gakushi_permission(uid: str, granted: bool = True) -> bool:
    """学士試験権限を付与または剥奪"""
    manager = get_firestore_manager()
    return manager.grant_user_permission(uid, "can_access_gakushi", granted)


def get_user_permissions(uid: str) -> Dict[str, bool]:
    """ユーザーの全権限を取得"""
    manager = get_firestore_manager()
    return manager.get_user_permissions(uid)


def list_all_permissions() -> Dict[str, Dict[str, bool]]:
    """全ユーザーの権限リストを取得（管理者用）"""
    manager = get_firestore_manager()
    
    try:
        users_collection = manager.db.collection("users")
        docs = users_collection.get()
        
        permissions = {}
        for doc in docs:
            user_data = doc.to_dict()
            uid = doc.id
            email = user_data.get("email", "Unknown")
            
            permissions[uid] = {
                "email": email,
                "has_gakushi_permission": user_data.get("has_gakushi_permission", False)
            }
        
        return permissions
    except Exception as e:
        print(f"[ERROR] 権限リスト取得エラー: {e}")
        return {}


# グローバル関数
def check_user_permission(uid: str, permission: str = "can_access_gakushi") -> bool:
    """ユーザー権限をチェック"""
    manager = get_firestore_manager()
    return manager.check_user_permission(uid, permission)


def fetch_ranking_data(limit: int = 100) -> List[Dict[str, Any]]:
    """ランキングデータを取得（最適化版）"""
    manager = get_firestore_manager()
    return manager.fetch_ranking_data(limit)


def get_secure_image_url(image_path: str, expires_in: int = 3600) -> Optional[str]:
    """Firebase Storageから署名付きURLを取得"""
    manager = get_firestore_manager()
    return manager.get_secure_image_url(image_path, expires_in)


def get_user_profile_for_ranking(uid: str) -> Optional[Dict[str, Any]]:
    """ランキング用ユーザープロファイルを取得"""
    if not uid:
        return None
    
    try:
        manager = get_firestore_manager()
        doc_ref = manager.db.collection("users").document(uid)
        doc = doc_ref.get()
        
        if doc.exists:
            data = doc.to_dict()
            return {
                "nickname": data.get("nickname", data.get("email", "").split("@")[0]),
                "show_on_leaderboard": data.get("show_on_leaderboard", True),
                "email": data.get("email", ""),
                "lastUpdated": data.get("lastUpdated")
            }
        else:
            return None
            
    except Exception as e:
        print(f"[ERROR] プロファイル取得エラー: {e}")
        return None


def get_user_profiles_bulk(uids: List[str]) -> Dict[str, Dict[str, Any]]:
    """複数のユーザープロファイルを一括取得（N+1問題対策）"""
    if not uids:
        return {}
    
    try:
        manager = get_firestore_manager()
        profiles = {}
        
        # Firestoreのバッチ読み取りを使用（最大500件まで）
        batch_size = 100  # 安全のため100件ずつ処理
        
        for i in range(0, len(uids), batch_size):
            batch_uids = uids[i:i + batch_size]
            
            # バッチ読み取りを作成
            batch = manager.db.batch()
            doc_refs = [manager.db.collection("users").document(uid) for uid in batch_uids]
            
            # ドキュメントを一括取得
            docs = manager.db.get_all(doc_refs)
            
            for doc in docs:
                if doc.exists:
                    data = doc.to_dict()
                    profiles[doc.id] = {
                        "nickname": data.get("nickname", data.get("email", "").split("@")[0] if data.get("email") else f"学習者{doc.id[:8]}"),
                        "show_on_leaderboard": data.get("show_on_leaderboard", True),  # デフォルトTrue
                        "email": data.get("email", ""),
                        "lastUpdated": data.get("lastUpdated")
                    }
                else:
                    # ドキュメントが存在しない場合のデフォルト値
                    profiles[doc.id] = {
                        "nickname": f"学習者{doc.id[:8]}",
                        "show_on_leaderboard": True,  # デフォルトTrue
                        "email": "",
                        "lastUpdated": None
                    }
        
        # 見つからなかったuidに対してはデフォルト値を設定
        for uid in uids:
            if uid not in profiles:
                profiles[uid] = {
                    "nickname": f"学習者{uid[:8]}",
                    "show_on_leaderboard": True,
                    "email": "",
                    "lastUpdated": None
                }
        
        return profiles
        
    except Exception as e:
        print(f"[ERROR] 一括プロファイル取得エラー: {e}")
        # エラー時はデフォルト値を返す
        return {uid: {
            "nickname": f"学習者{uid[:8]}",
            "show_on_leaderboard": True,
            "email": "",
            "lastUpdated": None
        } for uid in uids}


def save_user_profile(uid: str, nickname: str, show_on_leaderboard: bool) -> bool:
    """ユーザープロファイルを保存"""
    if not uid:
        return False
    
    try:
        manager = get_firestore_manager()
        doc_ref = manager.db.collection("users").document(uid)
        
        update_data = {
            "nickname": nickname,
            "show_on_leaderboard": show_on_leaderboard,
            "lastUpdated": firestore.SERVER_TIMESTAMP
        }
        
        # merge=Trueで既存のデータを保持
        doc_ref.set(update_data, merge=True)
        return True
        
    except Exception as e:
        print(f"[ERROR] プロファイル保存エラー: {e}")
        return False


def get_weekly_ranking(week_id: str) -> Optional[Dict[str, Any]]:
    """週間ランキングデータを取得"""
    try:
        manager = get_firestore_manager()
        ranking_ref = manager.db.collection("weekly_rankings").document(week_id)
        ranking_doc = ranking_ref.get()
        
        if ranking_doc.exists:
            return ranking_doc.to_dict()
        else:
            return None
            
    except Exception as e:
        print(f"[ERROR] 週間ランキング取得エラー: {e}")
        return None


def get_user_weekly_ranking(week_id: str, uid: str) -> Optional[Dict[str, Any]]:
    """ユーザーの週間ランキング情報を取得"""
    try:
        manager = get_firestore_manager()
        user_ranking_ref = manager.db.collection("user_rankings").document(f"{week_id}_{uid}")
        user_ranking_doc = user_ranking_ref.get()
        
        if user_ranking_doc.exists:
            return user_ranking_doc.to_dict()
        else:
            return None
            
    except Exception as e:
        print(f"[ERROR] ユーザー週間ランキング取得エラー: {e}")
        return None


def save_weekly_ranking_data(week_id: str, ranking_data: Dict[str, Any]) -> bool:
    """週間ランキングデータを保存"""
    try:
        manager = get_firestore_manager()
        ranking_ref = manager.db.collection("weekly_rankings").document(week_id)
        ranking_ref.set(ranking_data)
        return True
        
    except Exception as e:
        print(f"[ERROR] 週間ランキング保存エラー: {e}")
        return False


def save_user_ranking_data(week_id: str, uid: str, ranking_data: Dict[str, Any]) -> bool:
    """ユーザーランキングデータを保存"""
    try:
        manager = get_firestore_manager()
        user_ranking_ref = manager.db.collection("user_rankings").document(f"{week_id}_{uid}")
        user_ranking_ref.set(ranking_data)
        return True
        
    except Exception as e:
        print(f"[ERROR] ユーザーランキング保存エラー: {e}")
        return False


def save_llm_feedback(uid: str, question_id: str, generated_text: str, user_rating: int, metadata: Dict[str, Any]) -> bool:
    """
    LLMフィードバックデータをFirestoreに保存
    
    Args:
        uid (str): ユーザーID
        question_id (str): 問題ID
        generated_text (str): LLMが生成したフィードバックテキスト
        user_rating (int): ユーザーの評価（例: 1 または -1）
        metadata (Dict[str, Any]): 追加のメタデータ
    
    Returns:
        bool: 保存が成功した場合True、失敗した場合False
    """
    try:
        manager = get_firestore_manager()
        
        # 新しいドキュメントのデータを準備
        feedback_data = {
            "uid": uid,
            "question_id": question_id,
            "generated_text": generated_text,
            "user_rating": user_rating,
            "metadata": metadata,
            "created_at": gcp_firestore.SERVER_TIMESTAMP,
            "updated_at": gcp_firestore.SERVER_TIMESTAMP
        }
        
        # llm_feedbackコレクションに新しいドキュメントを追加
        feedback_ref = manager.db.collection("llm_feedback").document()
        feedback_ref.set(feedback_data)
        
        return True
        
    except Exception as e:
        print(f"[ERROR] LLMフィードバック保存エラー: {e}")
        return False
