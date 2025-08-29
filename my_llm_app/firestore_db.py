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
import tempfile
import os
import collections.abc
from typing import Dict, Any, Optional, List
import firebase_admin
from firebase_admin import credentials, firestore, storage
from google.cloud.firestore_v1 import FieldFilter


class FirestoreManager:
    """Firestoreデータベース操作を管理するクラス"""
    
    def __init__(self):
        self.db = None
        self.bucket = None
        self._initialize_firebase()
    
    def _initialize_firebase(self):
        """Firebase初期化"""
        if not hasattr(st.session_state, 'firebase_initialized'):
            firebase_creds = self._to_dict(st.secrets["firebase_credentials"])
            
            # 一時ファイルは後で必ず削除
            temp_path = None
            try:
                with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
                    json.dump(firebase_creds, f)
                    temp_path = f.name
                creds = credentials.Certificate(temp_path)

                storage_bucket = self._resolve_storage_bucket(firebase_creds)

                try:
                    app = firebase_admin.get_app()
                except ValueError:
                    app = firebase_admin.initialize_app(
                        creds,
                        {"storageBucket": storage_bucket}
                    )
                
                self.db = firestore.client(app=app)
                self.bucket = storage.bucket(app=app)
                st.session_state.firebase_initialized = True
                
            finally:
                # サービスアカウントの一時ファイルを確実に削除
                if temp_path:
                    try:
                        os.unlink(temp_path)
                    except Exception:
                        pass
        else:
            # 既に初期化済みの場合は既存のクライアントを取得
            self.db = firestore.client()
            self.bucket = storage.bucket()
    
    def _to_dict(self, obj):
        """オブジェクトを辞書に変換"""
        if isinstance(obj, collections.abc.Mapping):
            return {k: self._to_dict(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._to_dict(i) for i in obj]
        else:
            return obj
    
    def _resolve_storage_bucket(self, firebase_creds):
        """バケット名を正規化"""
        raw = st.secrets.get("firebase_storage_bucket") \
              or firebase_creds.get("storage_bucket") \
              or firebase_creds.get("storageBucket")

        if not raw:
            pid = firebase_creds.get("project_id") or firebase_creds.get("projectId") or "dent-ai-4d8d8"
            raw = f"{pid}.firebasestorage.app"

        b = str(raw).strip()
        b = b.replace("gs://", "").split("/")[0]
        return b
    
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
                print(f"[DEBUG] ユーザープロフィール読み込み成功: {time.time() - start:.3f}s")
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
                print(f"[DEBUG] 新規ユーザープロフィール作成: {uid}")
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
            
            print(f"[DEBUG] カードデータ読み込み完了: {len(cards)}枚, 時間: {time.time() - start:.3f}s")
            return cards
            
        except Exception as e:
            print(f"[ERROR] カードデータ読み込みエラー: {e}")
            return {}
    
    def load_session_state(self, uid: str) -> Dict[str, Any]:
        """セッション状態を読み込み（uid統一版）"""
        start = time.time()
        
        if not uid:
            return {
                "main_queue": [],
                "short_term_review_queue": [],
                "current_q_group": []
            }
        
        try:
            session_ref = self.db.collection("users").document(uid).collection("sessionState").document("current")
            session_doc = session_ref.get(timeout=5)
            
            if session_doc.exists:
                session_data = session_doc.to_dict()
                
                # Firestore対応：JSON文字列を元のリスト形式に復元
                def deserialize_queue(queue):
                    deserialized = []
                    for item in queue:
                        try:
                            if isinstance(item, str):
                                deserialized.append(json.loads(item))
                            elif isinstance(item, list):
                                deserialized.append(item)
                        except (json.JSONDecodeError, TypeError):
                            continue
                    return deserialized
                
                result = {
                    "current_q_group": deserialize_queue(session_data.get("current_q_group", [])),
                    "main_queue": deserialize_queue(session_data.get("main_queue", [])),
                    "short_term_review_queue": session_data.get("short_term_review_queue", [])
                }
                
                print(f"[DEBUG] セッション状態復元成功: {time.time() - start:.3f}s")
                return result
            else:
                return {
                    "main_queue": [],
                    "short_term_review_queue": [],
                    "current_q_group": []
                }
                
        except Exception as e:
            print(f"[ERROR] セッション状態読み込みエラー: {e}")
            return {
                "main_queue": [],
                "short_term_review_queue": [],
                "current_q_group": []
            }
    
    def get_user_cards(self, uid: str) -> Dict[str, Any]:
        """ユーザーの学習カードデータを取得（uid統一版）"""
        start = time.time()
        
        if not uid:
            return {}
        
        try:
            cards_collection = self.db.collection("users").document(uid).collection("userCards")
            cards_docs = cards_collection.get(timeout=10)
            
            cards = {}
            for doc in cards_docs:
                if doc.exists:
                    cards[doc.id] = self._to_dict(doc.to_dict())
            
            # 学習データの統計を計算
            learned_cards = len([card for card in cards.values() if card.get("level", -1) >= 0])
            mastered_cards = len([card for card in cards.values() if card.get("level", -1) >= 5])
            
            print(f"[DEBUG] 学習データ取得完了: 学習済み {learned_cards}問 / 習得済み {mastered_cards}問, 時間: {time.time() - start:.3f}s")
            return cards
            
        except Exception as e:
            print(f"[ERROR] ユーザーカード取得エラー: {e}")
            return {}
    
    def save_user_card(self, uid: str, question_id: str, card_data: Dict[str, Any]):
        """単一カードデータを保存（uid統一版）"""
        if not uid or not question_id:
            return
        
        try:
            card_ref = self.db.collection("users").document(uid).collection("userCards").document(question_id)
            card_ref.set(card_data, merge=True)
            print(f"[DEBUG] カード保存完了: {question_id}")
        except Exception as e:
            print(f"[ERROR] カード保存エラー: {e}")
    
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
                "last_updated": datetime.datetime.utcnow().isoformat()
            }
            
            session_ref = self.db.collection("users").document(uid).collection("sessionState").document("current")
            session_ref.set(serialized_data, merge=True)
            print(f"[DEBUG] セッション状態保存完了")
            
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
            print(f"[DEBUG] ユーザー設定更新完了")
        except Exception as e:
            print(f"[ERROR] ユーザー設定更新エラー: {e}")
    
    def check_user_permission(self, uid: str, permission_key: str) -> bool:
        """ユーザー権限をチェック（uid統一版）"""
        if not uid:
            return False
        
        try:
            doc_ref = self.db.collection("user_permissions").document(uid)
            doc = doc_ref.get()
            
            if doc.exists:
                data = doc.to_dict()
                result = bool(data.get(permission_key, False))
                print(f"[DEBUG] 権限チェック({permission_key}): {result}")
                return result
            else:
                return False
                
        except Exception as e:
            print(f"[ERROR] 権限チェックエラー: {e}")
            return False
    
    def fetch_ranking_data(self, limit: int = 100) -> List[Dict[str, Any]]:
        """ランキングデータを効率的に取得（実際のポイント計算）"""
        try:
            # 最新の週間ランキングデータを探す（週間ポイントがあるものを優先）
            ranking_refs = self.db.collection("weekly_rankings").order_by("week_start", direction=firestore.Query.DESCENDING).limit(10)
            ranking_docs = ranking_refs.stream()
            
            # 週間ポイントがあるランキングを優先して選択
            for doc in ranking_docs:
                ranking_data = doc.to_dict().get("rankings", [])
                if ranking_data:
                    # 週間ポイントがあるユーザーが存在するかチェック
                    has_weekly_activity = any(user.get("weekly_points", 0) > 0 for user in ranking_data)
                    if has_weekly_activity:
                        week_id = doc.id
                        print(f"[DEBUG] アクティブな週間ランキング使用: {week_id} ({len(ranking_data)}件)")
                        return ranking_data
            
            # 週間ポイントがない場合は最新のランキングを使用
            ranking_refs = self.db.collection("weekly_rankings").order_by("week_start", direction=firestore.Query.DESCENDING).limit(1)
            ranking_docs = ranking_refs.stream()
            
            for doc in ranking_docs:
                ranking_data = doc.to_dict().get("rankings", [])
                if ranking_data:
                    week_id = doc.id
                    print(f"[DEBUG] 最新週間ランキング使用: {week_id} ({len(ranking_data)}件)")
                    return ranking_data
            
            # 保存されたランキングがない場合は今週のリアルタイム計算
            print("[DEBUG] リアルタイムでランキング計算中...")
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
                    
                    # 習熟度計算
                    total_cards = len(cards)
                    mastered_cards = sum(1 for card in cards.values() if card.get("level", 0) >= 4)
                    mastery_rate = mastered_cards / total_cards * 100 if total_cards > 0 else 0
                    
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
            
            print(f"[DEBUG] リアルタイムランキング計算完了: {len(ranking_data)}件")
            return ranking_data
            
        except Exception as e:
            print(f"[ERROR] ランキングデータ取得エラー: {e}")
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


# グローバルインスタンス
@st.cache_resource
def get_firestore_manager():
    """FirestoreManagerのシングルトンインスタンスを取得"""
    return FirestoreManager()


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
    """学士試験アクセス権限をチェック（uid統一版）"""
    manager = get_firestore_manager()
    return manager.check_user_permission(uid, "can_access_gakushi")


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
        print(f"[DEBUG] プロファイル保存完了: {uid}")
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
