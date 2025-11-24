"""
Firestore最適化とデータ移行スクリプト

主な改善点：
1. 構造の簡素化
2. 書き込み回数削減
3. クエリ効率化
4. コスト最適化
"""

import streamlit as st
import datetime
from typing import Dict, Any, List, Optional
from firestore_db import get_firestore_manager
from google.cloud.firestore_v1 import WriteBatch

class FirestoreOptimizer:
    """Firestore構造最適化とコスト削減クラス"""
    
    def __init__(self):
        self.manager = get_firestore_manager()
        self.db = self.manager.db
        
    def migrate_user_data(self, user_id: str) -> bool:
        """ユーザーデータを最適化構造に移行"""
        try:
            print(f"[MIGRATION] ユーザー {user_id[:8]} のデータ移行開始")
            
            # 既存データ取得
            user_doc = self.db.collection("users").document(user_id).get()
            if not user_doc.exists:
                print(f"[MIGRATION] ユーザー {user_id[:8]} が存在しません")
                return False
            
            user_data = user_doc.to_dict()
            
            # ユーザーカード取得
            cards_ref = self.db.collection("users").document(user_id).collection("userCards")
            cards_docs = cards_ref.stream()
            
            # 統計計算
            total_cards = 0
            mastered_cards = 0
            total_points = 0
            weekly_points = 0
            
            # 今週の開始日
            today = datetime.datetime.now(datetime.timezone.utc)
            week_start = today - datetime.timedelta(days=today.weekday())
            week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
            week_end = week_start + datetime.timedelta(days=7)
            
            # バッチ処理準備
            batch = self.db.batch()
            batch_count = 0
            
            for card_doc in cards_docs:
                card_data = card_doc.to_dict()
                total_cards += 1
                
                # 習熟度判定
                if card_data.get("level", 0) >= 4:
                    mastered_cards += 1
                
                # ポイント計算
                history = card_data.get("history", [])
                for record in history:
                    quality = record.get("quality", 0)
                    timestamp_str = record.get("timestamp", "")
                    
                    # ポイント計算
                    if quality >= 4:
                        points = 5
                    elif quality >= 2:
                        points = 2
                    else:
                        points = 0
                    
                    total_points += points
                    
                    # 週間ポイント
                    try:
                        timestamp = datetime.datetime.fromisoformat(timestamp_str)
                        if week_start <= timestamp < week_end:
                            weekly_points += points
                    except (ValueError, TypeError):
                        continue
                
                # 最適化されたカードデータ作成
                optimized_card = {
                    "user_id": user_id,
                    "question_id": card_doc.id,
                    "level": card_data.get("level", 0),
                    "last_reviewed": card_data.get("lastReviewed"),
                    "review_count": len(history),
                    "history": history[-5:]  # 最新5件のみ保持
                }
                
                # 新しい構造でカード保存
                new_card_ref = self.db.collection("user_cards").document(f"{user_id}_{card_doc.id}")
                batch.set(new_card_ref, optimized_card)
                
                batch_count += 1
                if batch_count >= 400:  # Firestoreの制限内
                    batch.commit()
                    batch = self.db.batch()
                    batch_count = 0
            
            # 最適化されたユーザーデータ作成
            optimized_user = {
                "email": user_data.get("email", ""),
                "nickname": user_data.get("nickname", user_data.get("email", "").split("@")[0]),
                "created_at": user_data.get("createdAt", datetime.datetime.utcnow()),
                "last_active": datetime.datetime.utcnow(),
                "settings": {
                    "new_cards_per_day": user_data.get("settings", {}).get("new_cards_per_day", 10),
                    "can_access_gakushi": True  # 既存ユーザーは全員有効
                },
                "stats": {
                    "total_cards": total_cards,
                    "mastered_cards": mastered_cards,
                    "total_points": total_points,
                    "weekly_points": weekly_points,
                    "last_updated": datetime.datetime.utcnow()
                }
            }
            
            # ユーザーデータ更新
            batch.set(self.db.collection("users").document(user_id), optimized_user)
            
            # バッチコミット
            if batch_count > 0:
                batch.commit()
            
            print(f"[MIGRATION] ユーザー {user_id[:8]} 移行完了: カード{total_cards}枚, 習熟度{mastered_cards/total_cards*100:.1f}%")
            return True
            
        except Exception as e:
            print(f"[ERROR] ユーザー {user_id[:8]} 移行失敗: {e}")
            return False
    
    def get_optimized_ranking_data(self, limit: int = 100) -> List[Dict[str, Any]]:
        """最適化されたランキングデータ取得"""
        try:
            print("[OPTIMIZED] 最適化されたランキングデータ取得開始")
            
            # 統計データから直接取得（クエリ1回）
            users_ref = self.db.collection("users").limit(limit)
            users_docs = users_ref.stream()
            
            ranking_data = []
            
            for doc in users_docs:
                user_data = doc.to_dict()
                stats = user_data.get("stats", {})
                
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
                    "mastered_cards": mastered_cards
                })
            
            # 週間ポイントでソート
            ranking_data.sort(key=lambda x: x["weekly_points"], reverse=True)
            
            print(f"[OPTIMIZED] 最適化ランキング取得完了: {len(ranking_data)}件")
            return ranking_data
            
        except Exception as e:
            print(f"[ERROR] 最適化ランキング取得エラー: {e}")
            return []
    
    def update_user_stats_batch(self, user_ids: List[str]):
        """ユーザー統計を一括更新（コスト削減）"""
        try:
            print(f"[BATCH] {len(user_ids)}人の統計一括更新開始")
            
            batch = self.db.batch()
            batch_count = 0
            
            for user_id in user_ids:
                # カード統計計算
                cards_query = self.db.collection("user_cards").where("user_id", "==", user_id)
                cards_docs = cards_query.stream()
                
                total_cards = 0
                mastered_cards = 0
                total_points = 0
                weekly_points = 0
                
                # 今週の範囲
                today = datetime.datetime.now(datetime.timezone.utc)
                week_start = today - datetime.timedelta(days=today.weekday())
                week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
                week_end = week_start + datetime.timedelta(days=7)
                
                for card_doc in cards_docs:
                    card_data = card_doc.to_dict()
                    total_cards += 1
                    
                    if card_data.get("level", 0) >= 4:
                        mastered_cards += 1
                    
                    # 履歴からポイント計算
                    history = card_data.get("history", [])
                    for record in history:
                        quality = record.get("quality", 0)
                        timestamp_str = record.get("timestamp", "")
                        
                        if quality >= 4:
                            points = 5
                        elif quality >= 2:
                            points = 2
                        else:
                            points = 0
                        
                        total_points += points
                        
                        try:
                            timestamp = datetime.datetime.fromisoformat(timestamp_str)
                            if week_start <= timestamp < week_end:
                                weekly_points += points
                        except (ValueError, TypeError):
                            continue
                
                # 統計更新
                stats_update = {
                    "stats.total_cards": total_cards,
                    "stats.mastered_cards": mastered_cards,
                    "stats.total_points": total_points,
                    "stats.weekly_points": weekly_points,
                    "stats.last_updated": datetime.datetime.utcnow(),
                    "last_active": datetime.datetime.utcnow()
                }
                
                user_ref = self.db.collection("users").document(user_id)
                batch.update(user_ref, stats_update)
                
                batch_count += 1
                if batch_count >= 400:
                    batch.commit()
                    batch = self.db.batch()
                    batch_count = 0
            
            if batch_count > 0:
                batch.commit()
            
            print(f"[BATCH] 統計一括更新完了")
            
        except Exception as e:
            print(f"[ERROR] 統計一括更新エラー: {e}")

# グローバル最適化インスタンス
@st.cache_resource
def get_firestore_optimizer():
    return FirestoreOptimizer()
