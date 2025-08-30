"""
最適化された週間ランキングシステム
移行後の管理を劇的に簡素化するための統合システム

主な改善点:
1. 統計データベースの事前計算ランキング
2. バッチ処理による効率的更新
3. キャッシュ機能の活用
4. コスト最適化クエリ
"""

import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import logging
from enhanced_firestore_optimizer import EnhancedFirestoreOptimizer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class OptimizedUserRanking:
    """最適化されたユーザーランキングデータ"""
    uid: str
    nickname: str
    weekly_points: int
    total_points: int
    mastery_rate: float
    total_cards: int
    mastered_cards: int
    last_updated: datetime.datetime
    rank: int = 0


class OptimizedWeeklyRankingSystem:
    """最適化された週間ランキングシステム"""
    
    def __init__(self):
        self.optimizer = EnhancedFirestoreOptimizer()
        self.db = self.optimizer.db
    
    def get_current_week_ranking(self, limit: int = 100) -> List[OptimizedUserRanking]:
        """現在の週間ランキングを取得（統計データベース使用）"""
        try:
            logger.info("最適化された週間ランキング取得開始")
            
            # 統計データから直接ランキング取得（1回のクエリ）
            ranking_data = self.optimizer.get_weekly_ranking_optimized(limit)
            
            # OptimizedUserRankingオブジェクトに変換
            rankings = []
            for rank, data in enumerate(ranking_data, 1):
                ranking = OptimizedUserRanking(
                    uid=data["uid"],
                    nickname=data["nickname"],
                    weekly_points=data["weekly_points"],
                    total_points=data["total_points"],
                    mastery_rate=data["mastery_rate"],
                    total_cards=data["total_cards"],
                    mastered_cards=data["mastered_cards"],
                    last_updated=data.get("last_updated", datetime.datetime.now()),
                    rank=rank
                )
                rankings.append(ranking)
            
            logger.info(f"最適化ランキング取得完了: {len(rankings)}名")
            return rankings
            
        except Exception as e:
            logger.error(f"最適化ランキング取得エラー: {e}")
            return []
    
    def update_all_user_statistics(self):
        """全ユーザーの統計データを一括更新"""
        try:
            logger.info("全ユーザー統計更新開始")
            
            # 全ユーザーを取得
            users_ref = self.db.collection("users")
            users_docs = list(users_ref.stream())
            
            update_count = 0
            
            for user_doc in users_docs:
                user_data = user_doc.to_dict()
                
                # 有効なユーザーのみ処理
                if user_data.get("email"):
                    # 統計をバッチ更新に追加
                    self.optimizer.update_user_statistics_batch(user_doc.id)
                    update_count += 1
                    
                    # 100件ごとにバッチコミット
                    if update_count % 100 == 0:
                        self.optimizer.commit_batch_operations()
                        logger.info(f"バッチコミット: {update_count}件完了")
            
            # 残りのバッチをコミット
            self.optimizer.commit_batch_operations()
            
            logger.info(f"全ユーザー統計更新完了: {update_count}名")
            return True
            
        except Exception as e:
            logger.error(f"統計更新エラー: {e}")
            return False
    
    def save_weekly_ranking_snapshot(self, week_start: datetime.datetime = None):
        """週間ランキングのスナップショットを保存"""
        if week_start is None:
            today = datetime.datetime.now(datetime.timezone.utc)
            week_start = today - datetime.timedelta(days=today.weekday())
            week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        
        try:
            logger.info(f"週間ランキングスナップショット保存: {week_start}")
            
            # 現在のランキングを取得
            rankings = self.get_current_week_ranking(50)  # 上位50位まで保存
            
            if not rankings:
                logger.warning("ランキングデータが空です")
                return False
            
            # スナップショット形式に変換
            week_id = week_start.strftime("%Y-%m-%d")
            ranking_snapshot = {
                "week_id": week_id,
                "week_start": week_start,
                "week_end": week_start + datetime.timedelta(days=7),
                "last_updated": datetime.datetime.now(datetime.timezone.utc),
                "total_participants": len(rankings),
                "rankings": []
            }
            
            for ranking in rankings:
                ranking_snapshot["rankings"].append({
                    "rank": ranking.rank,
                    "uid": ranking.uid,
                    "nickname": ranking.nickname,
                    "weekly_points": ranking.weekly_points,
                    "total_points": ranking.total_points,
                    "mastery_rate": ranking.mastery_rate,
                    "total_cards": ranking.total_cards,
                    "mastered_cards": ranking.mastered_cards
                })
            
            # Firestoreに保存
            snapshot_ref = self.db.collection("weekly_ranking_snapshots").document(week_id)
            snapshot_ref.set(ranking_snapshot)
            
            logger.info(f"週間ランキングスナップショット保存完了: {len(rankings)}名")
            return True
            
        except Exception as e:
            logger.error(f"スナップショット保存エラー: {e}")
            return False
    
    def get_historical_ranking(self, week_id: str) -> Optional[Dict[str, Any]]:
        """過去の週間ランキングを取得"""
        try:
            snapshot_ref = self.db.collection("weekly_ranking_snapshots").document(week_id)
            snapshot_doc = snapshot_ref.get()
            
            if snapshot_doc.exists:
                return snapshot_doc.to_dict()
            else:
                return None
                
        except Exception as e:
            logger.error(f"過去ランキング取得エラー: {e}")
            return None
    
    def reset_weekly_points(self):
        """週間ポイントをリセット"""
        try:
            logger.info("週間ポイントリセット開始")
            
            # 全ユーザーの週間ポイントを0にリセット
            users_ref = self.db.collection("users")
            users_docs = list(users_ref.stream())
            
            reset_count = 0
            
            for user_doc in users_docs:
                user_data = user_doc.to_dict()
                
                if user_data.get("email") and user_data.get("stats", {}).get("weekly_points", 0) > 0:
                    # バッチ更新に追加
                    self.optimizer.batch_operations.append({
                        "type": "update",
                        "collection": "users",
                        "document_id": user_doc.id,
                        "data": {
                            "stats.weekly_points": 0,
                            "stats.last_updated": datetime.datetime.now()
                        }
                    })
                    reset_count += 1
                    
                    # 100件ごとにバッチコミット
                    if reset_count % 100 == 0:
                        self.optimizer.commit_batch_operations()
                        logger.info(f"週間ポイントリセット: {reset_count}件完了")
            
            # 残りのバッチをコミット
            self.optimizer.commit_batch_operations()
            
            logger.info(f"週間ポイントリセット完了: {reset_count}名")
            return True
            
        except Exception as e:
            logger.error(f"週間ポイントリセットエラー: {e}")
            return False
    
    def get_user_ranking_position(self, uid: str) -> Optional[Dict[str, Any]]:
        """ユーザーの現在のランキング順位を取得"""
        try:
            # 全ランキングを取得
            rankings = self.get_current_week_ranking()
            
            # 該当ユーザーを検索
            for ranking in rankings:
                if ranking.uid == uid:
                    return {
                        "rank": ranking.rank,
                        "weekly_points": ranking.weekly_points,
                        "total_points": ranking.total_points,
                        "mastery_rate": ranking.mastery_rate,
                        "total_participants": len(rankings)
                    }
            
            return None
            
        except Exception as e:
            logger.error(f"ユーザーランキング取得エラー: {e}")
            return None
    
    def run_weekly_maintenance(self):
        """週次メンテナンス処理"""
        try:
            logger.info("週次メンテナンス開始")
            
            # 1. 現在の週間ランキングをスナップショットとして保存
            self.save_weekly_ranking_snapshot()
            
            # 2. 全ユーザーの統計データを更新
            self.update_all_user_statistics()
            
            # 3. 週間ポイントをリセット
            self.reset_weekly_points()
            
            # 4. キャッシュをクリア
            self.optimizer.clear_cache()
            
            logger.info("週次メンテナンス完了")
            return True
            
        except Exception as e:
            logger.error(f"週次メンテナンスエラー: {e}")
            return False


# === 使用例とテスト関数 ===

def test_optimized_ranking_system():
    """最適化ランキングシステムのテスト"""
    system = OptimizedWeeklyRankingSystem()
    
    print("=== 最適化ランキングシステムテスト ===")
    
    # 1. 現在のランキング取得
    rankings = system.get_current_week_ranking(10)
    print(f"現在のランキング: {len(rankings)}名")
    
    if rankings:
        print("上位5位:")
        for i, ranking in enumerate(rankings[:5], 1):
            print(f"  {i}位: {ranking.nickname} - 週間{ranking.weekly_points}pt, 習熟度{ranking.mastery_rate:.1f}%")
    
    # 2. 統計更新テスト
    print("\n=== 統計更新テスト ===")
    success = system.update_all_user_statistics()
    print(f"統計更新結果: {'成功' if success else '失敗'}")
    
    # 3. スナップショット保存テスト
    print("\n=== スナップショット保存テスト ===")
    success = system.save_weekly_ranking_snapshot()
    print(f"スナップショット保存結果: {'成功' if success else '失敗'}")
    
    return True


if __name__ == "__main__":
    test_optimized_ranking_system()
