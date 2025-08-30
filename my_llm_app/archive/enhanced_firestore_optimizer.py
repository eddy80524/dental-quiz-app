"""
完全最適化版Firestoreマネージャー
移行前に実装すべき全ての最適化を統合

主な改善点:
1. バッチ処理による書き込み削減
2. 統計データの事前計算
3. キャッシュ機能の強化
4. クエリ効率化
5. コスト最適化
"""

import streamlit as st
import json
import datetime
import time
import tempfile
import os
from typing import Dict, Any, Optional, List
import firebase_admin
from firebase_admin import credentials, firestore, storage
from google.cloud.firestore_v1 import FieldFilter, Increment
import collections.abc


class EnhancedFirestoreOptimizer:
    """完全最適化版Firestoreマネージャー"""
    
    def __init__(self):
        self.db = None
        self.bucket = None
        self.cache = {}  # メモリキャッシュ
        self.batch_operations = []  # バッチ処理用
        self._initialize_firebase()
    
    def _initialize_firebase(self):
        """Firebase初期化"""
        try:
            if not firebase_admin._apps:
                firebase_creds = self._to_dict(st.secrets["firebase_credentials"])
                cred = credentials.Certificate(firebase_creds)
                firebase_admin.initialize_app(cred, {
                    'storageBucket': self._resolve_storage_bucket(firebase_creds)
                })
            
            self.db = firestore.client()
            self.bucket = storage.bucket()
            
        except Exception as e:
            print(f"Firebase初期化エラー: {e}")
    
    def _to_dict(self, secrets_obj):
        """Streamlitのsecrets処理"""
        if isinstance(secrets_obj, dict):
            return secrets_obj
        if isinstance(secrets_obj, collections.abc.Mapping):
            return {k: v for k, v in secrets_obj.items()}
        return dict(secrets_obj)
    
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

    # === 最適化された学習カード管理 ===
    
    def get_study_card_optimized(self, uid: str, question_id: str) -> Dict[str, Any]:
        """最適化された学習カード取得"""
        card_id = f"{uid}_{question_id}"
        
        # キャッシュ確認
        if card_id in self.cache:
            return self.cache[card_id]
        
        try:
            card_doc = self.db.collection("study_cards").document(card_id).get()
            if card_doc.exists:
                card_data = card_doc.to_dict()
                self.cache[card_id] = card_data  # キャッシュに保存
                return card_data
            else:
                # 新規カード作成
                return self._create_optimized_study_card(uid, question_id)
                
        except Exception as e:
            print(f"学習カード取得エラー: {e}")
            return self._create_optimized_study_card(uid, question_id)
    
    def _create_optimized_study_card(self, uid: str, question_id: str) -> Dict[str, Any]:
        """最適化された新規学習カード作成"""
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
    
    def update_study_card_batch(self, uid: str, question_id: str, sm2_data: Dict[str, Any], 
                               quality: int, is_correct: bool):
        """バッチ処理用学習カード更新"""
        card_id = f"{uid}_{question_id}"
        
        update_data = {
            "sm2_data": sm2_data,
            "performance.total_attempts": Increment(1),
            "performance.correct_attempts": Increment(1 if is_correct else 0),
            "performance.last_quality": quality,
            "metadata.updated_at": datetime.datetime.now()
        }
        
        # バッチ操作に追加
        self.batch_operations.append({
            "type": "update",
            "collection": "study_cards",
            "document_id": card_id,
            "data": update_data
        })
        
        # キャッシュを無効化
        if card_id in self.cache:
            del self.cache[card_id]
    
    def get_due_cards_optimized(self, uid: str, limit: int = 20) -> List[Dict[str, Any]]:
        """最適化された復習対象カード取得"""
        try:
            # 単一クエリで復習対象カードを取得
            due_query = self.db.collection("study_cards")\
                .where("uid", "==", uid)\
                .where("sm2_data.due_date", "<=", datetime.datetime.now())\
                .order_by("sm2_data.due_date")\
                .limit(limit)
            
            cards = []
            for doc in due_query.stream():
                card_data = doc.to_dict()
                cards.append(card_data)
            
            return cards
            
        except Exception as e:
            print(f"復習対象カード取得エラー: {e}")
            return []
    
    # === 統計データの事前計算 ===
    
    def calculate_user_statistics_batch(self, uid: str) -> Dict[str, Any]:
        """ユーザー統計の一括計算"""
        try:
            # 全学習カードを一括取得
            cards_query = self.db.collection("study_cards").where("uid", "==", uid)
            cards_docs = list(cards_query.stream())
            
            # 統計計算
            total_cards = len(cards_docs)
            mastered_cards = 0
            total_points = 0
            weekly_points = 0
            
            # 今週の開始日
            today = datetime.datetime.now(datetime.timezone.utc)
            week_start = today - datetime.timedelta(days=today.weekday())
            week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
            week_end = week_start + datetime.timedelta(days=7)
            
            for card_doc in cards_docs:
                card_data = card_doc.to_dict()
                
                # 習熟度判定（SM2のintervalが7日以上で習得済み）
                sm2_data = card_data.get("sm2_data", {})
                if sm2_data.get("interval", 0) >= 7:
                    mastered_cards += 1
                
                # パフォーマンスからポイント計算
                performance = card_data.get("performance", {})
                total_attempts = performance.get("total_attempts", 0)
                correct_attempts = performance.get("correct_attempts", 0)
                
                # 総ポイント（正解1回につき5ポイント）
                total_points += correct_attempts * 5
                
                # 週間ポイント（last_studiedが今週内の場合）
                last_studied = sm2_data.get("last_studied")
                if last_studied and isinstance(last_studied, datetime.datetime):
                    if week_start <= last_studied < week_end:
                        weekly_points += correct_attempts * 5
            
            stats = {
                "total_cards": total_cards,
                "mastered_cards": mastered_cards,
                "total_points": total_points,
                "weekly_points": weekly_points,
                "mastery_rate": (mastered_cards / total_cards * 100) if total_cards > 0 else 0,
                "last_updated": datetime.datetime.now()
            }
            
            return stats
            
        except Exception as e:
            print(f"統計計算エラー: {e}")
            return {
                "total_cards": 0,
                "mastered_cards": 0,
                "total_points": 0,
                "weekly_points": 0,
                "mastery_rate": 0,
                "last_updated": datetime.datetime.now()
            }
    
    def update_user_statistics_batch(self, uid: str):
        """ユーザー統計をバッチ更新"""
        stats = self.calculate_user_statistics_batch(uid)
        
        # バッチ操作に追加
        self.batch_operations.append({
            "type": "update",
            "collection": "users",
            "document_id": uid,
            "data": {"stats": stats}
        })
    
    # === バッチ処理管理 ===
    
    def commit_batch_operations(self):
        """バッチ操作をコミット"""
        if not self.batch_operations:
            return True
        
        try:
            batch = self.db.batch()
            
            for operation in self.batch_operations:
                if operation["type"] == "update":
                    doc_ref = self.db.collection(operation["collection"]).document(operation["document_id"])
                    batch.update(doc_ref, operation["data"])
                elif operation["type"] == "set":
                    doc_ref = self.db.collection(operation["collection"]).document(operation["document_id"])
                    batch.set(doc_ref, operation["data"])
            
            batch.commit()
            
            # 操作履歴をクリア
            self.batch_operations.clear()
            
            print(f"バッチ操作完了: {len(self.batch_operations)}件")
            return True
            
        except Exception as e:
            print(f"バッチ操作エラー: {e}")
            return False
    
    # === 最適化されたランキング取得 ===
    
    def get_weekly_ranking_optimized(self, limit: int = 100) -> List[Dict[str, Any]]:
        """最適化された週間ランキング取得"""
        try:
            # 統計データから直接取得（1回のクエリ）
            users_query = self.db.collection("users")\
                .where("stats.weekly_points", ">", 0)\
                .order_by("stats.weekly_points", direction=firestore.Query.DESCENDING)\
                .limit(limit)
            
            ranking_data = []
            
            for doc in users_query.stream():
                user_data = doc.to_dict()
                stats = user_data.get("stats", {})
                
                ranking_data.append({
                    "uid": doc.id,
                    "nickname": user_data.get("nickname", f"学習者{doc.id[:8]}"),
                    "weekly_points": stats.get("weekly_points", 0),
                    "total_points": stats.get("total_points", 0),
                    "mastery_rate": stats.get("mastery_rate", 0),
                    "total_cards": stats.get("total_cards", 0),
                    "mastered_cards": stats.get("mastered_cards", 0),
                    "last_updated": stats.get("last_updated")
                })
            
            print(f"最適化ランキング取得: {len(ranking_data)}件")
            return ranking_data
            
        except Exception as e:
            print(f"最適化ランキング取得エラー: {e}")
            return []
    
    # === 分析データの最適化 ===
    
    def update_analytics_summary_batch(self, uid: str, period: str, date: str, metrics: Dict[str, Any]):
        """分析サマリーのバッチ更新"""
        doc_id = f"{uid}_{period}_{date}"
        
        # バッチ操作に追加
        self.batch_operations.append({
            "type": "set",
            "collection": "analytics_summary",
            "document_id": doc_id,
            "data": {
                "uid": uid,
                "period": period,
                "date": date,
                "metrics": metrics,
                "updated_at": datetime.datetime.now()
            }
        })
    
    # === ユーティリティ ===
    
    def _get_subject_from_question_id(self, question_id: str) -> str:
        """問題IDから科目を推定"""
        # 実装: 問題IDのパターンから科目を判定
        if question_id.startswith("dent_"):
            return "歯科"
        elif question_id.startswith("oral_"):
            return "口腔外科"
        elif question_id.startswith("perio_"):
            return "歯周病"
        else:
            return "一般"
    
    def clear_cache(self):
        """キャッシュクリア"""
        self.cache.clear()
    
    def get_cache_size(self) -> int:
        """キャッシュサイズ取得"""
        return len(self.cache)


# === 移行専用の最適化関数 ===

def migrate_to_optimized_structure(uid: str) -> bool:
    """ユーザーデータを最適化構造に移行"""
    try:
        optimizer = EnhancedFirestoreOptimizer()
        
        print(f"[MIGRATION] ユーザー {uid[:8]} の最適化移行開始")
        
        # 既存のuserCardsサブコレクションを取得
        old_cards_ref = optimizer.db.collection("users").document(uid).collection("userCards")
        old_cards_docs = list(old_cards_ref.stream())
        
        print(f"[MIGRATION] 既存カード数: {len(old_cards_docs)}")
        
        # 最適化されたstudy_cardsコレクションに移行
        for card_doc in old_cards_docs:
            old_card_data = card_doc.to_dict()
            
            # 最適化されたカード構造に変換
            optimized_card = {
                "uid": uid,
                "question_id": card_doc.id,
                "sm2_data": {
                    "n": old_card_data.get("n", 0),
                    "ef": old_card_data.get("ef", 2.5),
                    "interval": old_card_data.get("interval", 0),
                    "due_date": old_card_data.get("dueDate", datetime.datetime.now()),
                    "last_studied": old_card_data.get("lastReviewed")
                },
                "performance": {
                    "total_attempts": len(old_card_data.get("history", [])),
                    "correct_attempts": sum(1 for h in old_card_data.get("history", []) if h.get("quality", 0) >= 4),
                    "avg_quality": sum(h.get("quality", 0) for h in old_card_data.get("history", [])) / max(len(old_card_data.get("history", [])), 1),
                    "last_quality": old_card_data.get("history", [{}])[-1].get("quality", 0) if old_card_data.get("history") else 0
                },
                "metadata": {
                    "created_at": old_card_data.get("createdAt", datetime.datetime.now()),
                    "updated_at": datetime.datetime.now(),
                    "subject": optimizer._get_subject_from_question_id(card_doc.id),
                    "difficulty": "normal"
                }
            }
            
            # 新しい構造で保存
            new_card_id = f"{uid}_{card_doc.id}"
            optimizer.db.collection("study_cards").document(new_card_id).set(optimized_card)
        
        # ユーザー統計を計算・更新
        stats = optimizer.calculate_user_statistics_batch(uid)
        optimizer.db.collection("users").document(uid).update({"stats": stats})
        
        print(f"[MIGRATION] ユーザー {uid[:8]} 移行完了: カード{len(old_cards_docs)}枚")
        return True
        
    except Exception as e:
        print(f"[ERROR] ユーザー {uid[:8]} 移行失敗: {e}")
        return False


def migrate_all_users_to_optimized():
    """全ユーザーを最適化構造に移行"""
    try:
        optimizer = EnhancedFirestoreOptimizer()
        
        print("[MIGRATION] 全ユーザー最適化移行開始")
        
        # 全ユーザーを取得
        users_ref = optimizer.db.collection("users")
        users_docs = list(users_ref.stream())
        
        success_count = 0
        failure_count = 0
        
        for user_doc in users_docs:
            user_data = user_doc.to_dict()
            
            # 有効なユーザーのみ処理
            if user_data.get("email"):
                if migrate_to_optimized_structure(user_doc.id):
                    success_count += 1
                else:
                    failure_count += 1
        
        print(f"[MIGRATION] 全ユーザー移行完了: 成功{success_count}名, 失敗{failure_count}名")
        return True
        
    except Exception as e:
        print(f"[ERROR] 全ユーザー移行失敗: {e}")
        return False


# === キャッシュ管理 ===

@st.cache_data(ttl=300)  # 5分間キャッシュ
def get_cached_firestore_optimizer():
    """キャッシュされた最適化Firestoreマネージャー"""
    return EnhancedFirestoreOptimizer()
