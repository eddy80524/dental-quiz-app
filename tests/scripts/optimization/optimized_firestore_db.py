"""
Optimized Firestore Database Manager
最適化されたFirestoreデータベース管理

主な変更点:
- Native App対応のスキーマ構造
- 効率的なデータアクセスパターン
- 学士権限管理の維持
- 拡張性を考慮した設計
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
from google.cloud.firestore import Increment


class OptimizedFirestoreManager:
    """最適化されたFirestoreデータベース操作管理クラス"""
    
    def __init__(self):
        self.db = None
        self.bucket = None
        self._initialize_firebase()
    
    def _initialize_firebase(self):
        """Firebase初期化"""
        if not hasattr(st.session_state, 'firebase_initialized'):
            firebase_creds = self._to_dict(st.secrets["firebase_credentials"])
            
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
                if temp_path:
                    try:
                        os.unlink(temp_path)
                    except Exception:
                        pass
        else:
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
    
    # === ユーザー管理 ===
    
    def get_user_profile(self, uid: str) -> Dict[str, Any]:
        """最適化されたユーザープロフィール取得"""
        if not uid:
            return self._get_default_user_profile()
        
        try:
            user_doc = self.db.collection("users").document(uid).get()
            if user_doc.exists:
                return user_doc.to_dict()
            else:
                # ユーザーが存在しない場合は作成
                return self._create_user_profile(uid)
                
        except Exception as e:
            print(f"Error loading user profile: {e}")
            return self._get_default_user_profile()
    
    def _get_default_user_profile(self) -> Dict[str, Any]:
        """デフォルトユーザープロフィール"""
        return {
            "profile": {
                "email": "",
                "display_name": "匿名ユーザー",
                "created_at": datetime.datetime.now(),
                "last_login": datetime.datetime.now(),
                "permissions": {
                    "gakushi_access": False,
                    "admin": False
                },
                "preferences": {
                    "new_cards_per_day": 10,
                    "study_reminder": True,
                    "analytics_opt_in": True
                }
            },
            "statistics": {
                "total_questions_answered": 0,
                "total_correct_answers": 0,
                "study_streak_days": 0,
                "last_study_date": None,
                "mastery_level": 0
            }
        }
    
    def _create_user_profile(self, uid: str) -> Dict[str, Any]:
        """新規ユーザープロフィール作成"""
        profile = self._get_default_user_profile()
        
        # 学士権限チェック（既存の仕組みを維持）
        profile["profile"]["permissions"]["gakushi_access"] = self._check_gakushi_permission_legacy(uid)
        
        try:
            self.db.collection("users").document(uid).set(profile)
        except Exception as e:
            print(f"Error creating user profile: {e}")
        
        return profile
    
    def _check_gakushi_permission_legacy(self, uid: str) -> bool:
        """既存の学士権限チェック（レガシー対応）"""
        try:
            # 既存のロジックを維持
            gakushi_user_ref = self.db.collection("gakushi_users").document(uid)
            doc = gakushi_user_ref.get()
            return doc.exists and doc.to_dict().get("allowed", False)
        except:
            return False
    
    def update_user_last_login(self, uid: str):
        """ユーザーの最終ログイン時刻を更新"""
        try:
            self.db.collection("users").document(uid).update({
                "profile.last_login": datetime.datetime.now()
            })
        except Exception as e:
            print(f"Error updating last login: {e}")
    
    # === 学習カード管理 ===
    
    def get_study_card(self, uid: str, question_id: str) -> Dict[str, Any]:
        """個別学習カード取得"""
        card_id = f"{uid}_{question_id}"
        
        try:
            card_doc = self.db.collection("study_cards").document(card_id).get()
            if card_doc.exists:
                return card_doc.to_dict()
            else:
                # カードが存在しない場合は新規作成
                return self._create_new_study_card(uid, question_id)
                
        except Exception as e:
            print(f"Error loading study card: {e}")
            return self._create_new_study_card(uid, question_id)
    
    def _create_new_study_card(self, uid: str, question_id: str) -> Dict[str, Any]:
        """新規学習カード作成"""
        card = {
            "uid": uid,
            "question_id": question_id,
            "sm2_data": {
                "n": 0,
                "ef": 2.5,
                "interval": 0,
                "due_date": datetime.datetime.now(),
                "last_studied": None
            },
            "performance": {
                "total_attempts": 0,
                "correct_attempts": 0,
                "avg_quality": 0.0,
                "last_quality": 0
            },
            "metadata": {
                "created_at": datetime.datetime.now(),
                "updated_at": datetime.datetime.now(),
                "subject": self._get_subject_from_question_id(question_id),
                "difficulty": "normal"
            }
        }
        
        return card
    
    def update_study_card(self, uid: str, question_id: str, sm2_data: Dict[str, Any], 
                         quality: int, is_correct: bool):
        """学習カードの更新"""
        card_id = f"{uid}_{question_id}"
        
        try:
            card_ref = self.db.collection("study_cards").document(card_id)
            card_doc = card_ref.get()
            
            if card_doc.exists:
                card_data = card_doc.to_dict()
                performance = card_data["performance"]
                
                # パフォーマンス更新
                new_performance = {
                    "total_attempts": performance["total_attempts"] + 1,
                    "correct_attempts": performance["correct_attempts"] + (1 if is_correct else 0),
                    "last_quality": quality,
                    "avg_quality": (performance["avg_quality"] * performance["total_attempts"] + quality) / (performance["total_attempts"] + 1)
                }
                
                # SM2データとパフォーマンスを更新
                card_ref.update({
                    "sm2_data": sm2_data,
                    "performance": new_performance,
                    "metadata.updated_at": datetime.datetime.now()
                })
            else:
                # 新規カード作成
                card = self._create_new_study_card(uid, question_id)
                card["sm2_data"] = sm2_data
                card["performance"]["total_attempts"] = 1
                card["performance"]["correct_attempts"] = 1 if is_correct else 0
                card["performance"]["last_quality"] = quality
                card["performance"]["avg_quality"] = quality
                
                card_ref.set(card)
                
        except Exception as e:
            print(f"Error updating study card: {e}")
    
    def get_due_cards(self, uid: str, limit: int = 20) -> List[Dict[str, Any]]:
        """復習対象カード取得"""
        try:
            today = datetime.datetime.now()
            
            cards_query = self.db.collection("study_cards")\
                .where("uid", "==", uid)\
                .where("sm2_data.due_date", "<=", today)\
                .order_by("sm2_data.due_date")\
                .limit(limit)
            
            return [doc.to_dict() for doc in cards_query.get()]
            
        except Exception as e:
            print(f"Error loading due cards: {e}")
            return []
    
    def get_user_cards_summary(self, uid: str) -> Dict[str, Any]:
        """ユーザーの学習カード概要"""
        try:
            # 今日の復習対象
            today = datetime.datetime.now()
            due_query = self.db.collection("study_cards")\
                .where("uid", "==", uid)\
                .where("sm2_data.due_date", "<=", today)
            
            due_count = len(due_query.get())
            
            # 全カード数
            all_query = self.db.collection("study_cards").where("uid", "==", uid)
            total_count = len(all_query.get())
            
            return {
                "total_cards": total_count,
                "due_cards": due_count,
                "mastery_cards": 0  # 習得済みカード数（実装は後で）
            }
            
        except Exception as e:
            print(f"Error loading cards summary: {e}")
            return {"total_cards": 0, "due_cards": 0, "mastery_cards": 0}
    
    # === 学習セッション管理 ===
    
    def create_study_session(self, uid: str, session_data: Dict[str, Any]) -> str:
        """学習セッション作成"""
        try:
            session_doc = {
                "uid": uid,
                "session_id": session_data.get("session_id", f"session_{int(time.time())}"),
                "start_time": session_data.get("start_time", datetime.datetime.now()),
                "end_time": session_data.get("end_time"),
                "session_type": session_data.get("session_type", "manual"),
                "questions": session_data.get("questions", []),
                "summary": session_data.get("summary", {})
            }
            
            doc_ref = self.db.collection("study_sessions").add(session_doc)
            return doc_ref[1].id  # ドキュメントID返却
            
        except Exception as e:
            print(f"Error creating study session: {e}")
            return ""
    
    def get_recent_sessions(self, uid: str, limit: int = 10) -> List[Dict[str, Any]]:
        """最近の学習セッション取得"""
        try:
            sessions_query = self.db.collection("study_sessions")\
                .where("uid", "==", uid)\
                .order_by("start_time", direction=firestore.Query.DESCENDING)\
                .limit(limit)
            
            return [doc.to_dict() for doc in sessions_query.get()]
            
        except Exception as e:
            print(f"Error loading recent sessions: {e}")
            return []
    
    # === 分析データ管理 ===
    
    def update_analytics_summary(self, uid: str, period: str, date: str, metrics: Dict[str, Any]):
        """分析サマリー更新"""
        try:
            doc_id = f"{uid}_{period}_{date}"
            summary_ref = self.db.collection("analytics_summary").document(doc_id)
            
            summary_doc = summary_ref.get()
            if summary_doc.exists:
                # 既存データの増分更新
                updates = {}
                for key, value in metrics.items():
                    if isinstance(value, (int, float)):
                        updates[f"metrics.{key}"] = Increment(value)
                    else:
                        updates[f"metrics.{key}"] = value
                
                updates["updated_at"] = datetime.datetime.now()
                summary_ref.update(updates)
            else:
                # 新規作成
                summary = {
                    "uid": uid,
                    "period": period,
                    "date": date,
                    "metrics": metrics,
                    "weak_subjects": [],
                    "strong_subjects": [],
                    "updated_at": datetime.datetime.now()
                }
                summary_ref.set(summary)
                
        except Exception as e:
            print(f"Error updating analytics summary: {e}")
    
    def get_analytics_summary(self, uid: str, period: str, days: int = 30) -> List[Dict[str, Any]]:
        """分析サマリー取得"""
        try:
            end_date = datetime.date.today()
            start_date = end_date - datetime.timedelta(days=days)
            
            summaries_query = self.db.collection("analytics_summary")\
                .where("uid", "==", uid)\
                .where("period", "==", period)\
                .where("date", ">=", start_date.isoformat())\
                .where("date", "<=", end_date.isoformat())\
                .order_by("date")
            
            return [doc.to_dict() for doc in summaries_query.get()]
            
        except Exception as e:
            print(f"Error loading analytics summary: {e}")
            return []
    
    # === ユーティリティ ===
    
    def _get_subject_from_question_id(self, question_id: str) -> str:
        """問題IDから科目を推定"""
        try:
            from data import load_data
            all_data = load_data()
            for q in all_data["questions"]:
                if q["number"] == question_id:
                    return q.get("subject", "未分類")
            return "未分類"
        except:
            return "未分類"
    
    # === 統計更新 ===
    
    def update_user_statistics(self, uid: str, session_summary: Dict[str, Any]):
        """ユーザー統計の更新"""
        try:
            total_questions = session_summary.get("total_questions", 0)
            correct_answers = session_summary.get("correct_answers", 0)
            
            self.db.collection("users").document(uid).update({
                "statistics.total_questions_answered": Increment(total_questions),
                "statistics.total_correct_answers": Increment(correct_answers),
                "statistics.last_study_date": datetime.date.today()
            })
            
            # 日次分析サマリーも更新
            today = datetime.date.today().isoformat()
            self.update_analytics_summary(uid, "daily", today, {
                "questions_answered": total_questions,
                "correct_answers": correct_answers,
                "accuracy": (correct_answers / total_questions * 100) if total_questions > 0 else 0,
                "study_time_minutes": session_summary.get("duration_minutes", 0),
                "sessions_count": 1
            })
            
        except Exception as e:
            print(f"Error updating user statistics: {e}")


# === レガシー互換性のための関数 ===

_optimized_manager = None

def get_optimized_firestore_manager() -> OptimizedFirestoreManager:
    """最適化されたFirestoreマネージャーのシングルトン取得"""
    global _optimized_manager
    if _optimized_manager is None:
        _optimized_manager = OptimizedFirestoreManager()
    return _optimized_manager

def check_gakushi_permission(uid: str) -> bool:
    """学士権限チェック（レガシー互換）"""
    manager = get_optimized_firestore_manager()
    user_profile = manager.get_user_profile(uid)
    return user_profile["profile"]["permissions"]["gakushi_access"]

def save_user_data(uid: str, question_id: str, card_data: Dict[str, Any]):
    """学習データ保存（レガシー互換）"""
    manager = get_optimized_firestore_manager()
    
    # 旧形式から新形式への変換
    sm2_data = {
        "n": card_data.get("n", 0),
        "ef": card_data.get("EF", 2.5),
        "interval": card_data.get("interval", 0),
        "due_date": card_data.get("due") or datetime.datetime.now(),
        "last_studied": datetime.datetime.now()
    }
    
    # 最後の履歴から品質と正誤を取得
    history = card_data.get("history", [])
    if history:
        last_entry = history[-1]
        quality = last_entry.get("quality", 3)
        is_correct = quality >= 3
    else:
        quality = 3
        is_correct = True
    
    manager.update_study_card(uid, question_id, sm2_data, quality, is_correct)

# 既存のFirestoreManagerとの互換性のためのエイリアス
def get_firestore_manager():
    """既存コードとの互換性のため"""
    return get_optimized_firestore_manager()
