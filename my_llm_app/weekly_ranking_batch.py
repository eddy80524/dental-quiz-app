"""
週間ランキング用バッチ処理システム

毎日特定の時間（例：午前3時）に実行されるバッチ処理で、
全ユーザーの週間ランキングデータを事前計算して保存する。

主な機能:
- 週間ポイント計算と保存
- 上位20位までのランキング更新
- 効率的なデータアクセス
"""

import datetime
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from firestore_db import get_firestore_manager
import logging

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class UserRankingData:
    """ユーザーランキングデータクラス"""
    uid: str
    nickname: str
    weekly_points: int
    total_points: int
    study_days: int
    mastery_level: str
    mastery_rate: float
    last_updated: datetime.datetime
    show_on_leaderboard: bool = True


class WeeklyRankingBatch:
    """週間ランキングバッチ処理クラス"""
    
    def __init__(self):
        self.firestore_manager = get_firestore_manager()
        self.db = self.firestore_manager.db
        
    def calculate_user_weekly_points(self, uid: str, week_start: datetime.datetime) -> Dict[str, int]:
        """ユーザーの週間ポイントを計算"""
        try:
            cards = self.firestore_manager.load_user_cards(uid)
            
            total_points = 0
            weekly_points = 0
            week_end = week_start + datetime.timedelta(days=7)
            
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
            
            return {
                "total_points": total_points,
                "weekly_points": weekly_points
            }
            
        except Exception as e:
            logger.error(f"ポイント計算エラー (uid: {uid}): {e}")
            return {"total_points": 0, "weekly_points": 0}
    
    def calculate_user_study_stats(self, uid: str) -> Dict[str, Any]:
        """ユーザーの学習統計を計算"""
        try:
            cards = self.firestore_manager.load_user_cards(uid)
            study_dates = set()
            
            for card in cards.values():
                for record in card.get("history", []):
                    timestamp_str = record.get("timestamp", "")
                    try:
                        timestamp = datetime.datetime.fromisoformat(timestamp_str)
                        study_dates.add(timestamp.date())
                    except (ValueError, TypeError):
                        continue
            
            # 習熟度計算
            total_cards = len(cards)
            mastered_cards = sum(1 for card in cards.values() if card.get("level", 0) >= 4)
            mastery_rate = mastered_cards / total_cards * 100 if total_cards > 0 else 0
            
            if mastery_rate >= 80:
                mastery_level = "上級"
            elif mastery_rate >= 50:
                mastery_level = "中級"
            elif mastery_rate >= 20:
                mastery_level = "初級"
            else:
                mastery_level = "入門"
            
            return {
                "study_days": len(study_dates),
                "mastery_level": mastery_level,
                "mastery_rate": mastery_rate
            }
            
        except Exception as e:
            logger.error(f"学習統計計算エラー (uid: {uid}): {e}")
            return {
                "study_days": 0,
                "mastery_level": "入門",
                "mastery_rate": 0.0
            }
    
    def get_user_profile_info(self, uid: str) -> Optional[Dict[str, Any]]:
        """ユーザープロフィール情報を取得"""
        try:
            # user_profilesコレクションから取得
            profile_ref = self.db.collection("user_profiles").document(uid)
            profile_doc = profile_ref.get()
            
            if profile_doc.exists:
                return profile_doc.to_dict()
            else:
                # プロフィールが存在しない場合はデフォルト作成
                default_profile = {
                    "nickname": f"ユーザー{uid[:8]}",
                    "show_on_leaderboard": True,
                    "created_at": datetime.datetime.now(datetime.timezone.utc)
                }
                profile_ref.set(default_profile)
                return default_profile
                
        except Exception as e:
            logger.error(f"プロフィール取得エラー (uid: {uid}): {e}")
            return None
    
    def get_all_active_users(self) -> List[str]:
        """アクティブなユーザーのUID一覧を取得"""
        try:
            # 過去30日間にアクティビティがあるユーザーを取得
            thirty_days_ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)
            
            users_ref = self.db.collection("users")
            users_docs = users_ref.stream()
            
            active_uids = []
            for doc in users_docs:
                user_data = doc.to_dict()
                last_updated = user_data.get("lastUpdated")
                
                if last_updated and isinstance(last_updated, datetime.datetime):
                    if last_updated >= thirty_days_ago:
                        active_uids.append(doc.id)
                elif user_data.get("email"):  # emailがあれば有効なユーザー
                    active_uids.append(doc.id)
            
            logger.info(f"アクティブユーザー数: {len(active_uids)}")
            return active_uids
            
        except Exception as e:
            logger.error(f"アクティブユーザー取得エラー: {e}")
            return []
    
    def calculate_weekly_ranking(self, week_start: datetime.datetime = None) -> List[UserRankingData]:
        """週間ランキングを計算"""
        if week_start is None:
            # 今週の月曜日を取得
            today = datetime.datetime.now(datetime.timezone.utc)
            week_start = today - datetime.timedelta(days=today.weekday())
            week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        
        logger.info(f"週間ランキング計算開始: {week_start}")
        
        active_uids = self.get_all_active_users()
        ranking_data = []
        
        for uid in active_uids:
            try:
                # プロフィール情報取得
                profile_info = self.get_user_profile_info(uid)
                if not profile_info:
                    continue
                
                # ランキング非表示設定の場合はスキップ
                if not profile_info.get("show_on_leaderboard", True):
                    continue
                
                # ポイント計算
                points = self.calculate_user_weekly_points(uid, week_start)
                
                # 学習統計計算
                study_stats = self.calculate_user_study_stats(uid)
                
                # ランキングデータ作成
                user_ranking = UserRankingData(
                    uid=uid,
                    nickname=profile_info.get("nickname", "匿名ユーザー"),
                    weekly_points=points["weekly_points"],
                    total_points=points["total_points"],
                    study_days=study_stats["study_days"],
                    mastery_level=study_stats["mastery_level"],
                    mastery_rate=study_stats["mastery_rate"],
                    last_updated=datetime.datetime.now(datetime.timezone.utc),
                    show_on_leaderboard=profile_info.get("show_on_leaderboard", True)
                )
                
                ranking_data.append(user_ranking)
                
            except Exception as e:
                logger.error(f"ユーザーランキング計算エラー (uid: {uid}): {e}")
                continue
        
        # 週間ポイントでソート
        ranking_data.sort(key=lambda x: x.weekly_points, reverse=True)
        
        logger.info(f"週間ランキング計算完了: {len(ranking_data)}名")
        return ranking_data
    
    def save_weekly_ranking(self, ranking_data: List[UserRankingData], week_start: datetime.datetime):
        """週間ランキングをFirestoreに保存"""
        try:
            # 上位20位のみ保存
            top_20 = ranking_data[:20]
            
            # 週間ランキングコレクションに保存
            week_id = week_start.strftime("%Y-%m-%d")
            ranking_ref = self.db.collection("weekly_rankings").document(week_id)
            
            ranking_doc = {
                "week_start": week_start,
                "week_end": week_start + datetime.timedelta(days=7),
                "last_updated": datetime.datetime.now(datetime.timezone.utc),
                "total_participants": len(ranking_data),
                "rankings": []
            }
            
            for rank, user_data in enumerate(top_20, 1):
                ranking_doc["rankings"].append({
                    "rank": rank,
                    "uid": user_data.uid,
                    "nickname": user_data.nickname,
                    "weekly_points": user_data.weekly_points,
                    "total_points": user_data.total_points,
                    "study_days": user_data.study_days,
                    "mastery_level": user_data.mastery_level,
                    "mastery_rate": user_data.mastery_rate
                })
            
            ranking_ref.set(ranking_doc)
            logger.info(f"週間ランキング保存完了: {week_id} (上位20位)")
            
            # 個別ユーザーランキング情報も保存（自分の順位確認用）
            for rank, user_data in enumerate(ranking_data, 1):
                user_ranking_ref = self.db.collection("user_rankings").document(f"{week_id}_{user_data.uid}")
                user_ranking_ref.set({
                    "week_id": week_id,
                    "uid": user_data.uid,
                    "rank": rank,
                    "weekly_points": user_data.weekly_points,
                    "total_points": user_data.total_points,
                    "last_updated": datetime.datetime.now(datetime.timezone.utc)
                })
            
            logger.info(f"個別ユーザーランキング保存完了: {len(ranking_data)}名")
            
        except Exception as e:
            logger.error(f"週間ランキング保存エラー: {e}")
            raise
    
    def run_weekly_ranking_batch(self):
        """週間ランキングバッチ処理を実行"""
        try:
            logger.info("=== 週間ランキングバッチ処理開始 ===")
            start_time = time.time()
            
            # 今週の月曜日を取得
            today = datetime.datetime.now(datetime.timezone.utc)
            week_start = today - datetime.timedelta(days=today.weekday())
            week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
            
            # ランキング計算
            ranking_data = self.calculate_weekly_ranking(week_start)
            
            if ranking_data:
                # ランキング保存
                self.save_weekly_ranking(ranking_data, week_start)
                
                elapsed_time = time.time() - start_time
                logger.info(f"=== 週間ランキングバッチ処理完了 ===")
                logger.info(f"処理時間: {elapsed_time:.2f}秒")
                logger.info(f"処理ユーザー数: {len(ranking_data)}名")
                logger.info(f"上位20位保存完了")
                
                return True
            else:
                logger.warning("ランキングデータが空です")
                return False
                
        except Exception as e:
            logger.error(f"週間ランキングバッチ処理エラー: {e}")
            return False


def run_batch():
    """バッチ処理のエントリーポイント"""
    batch = WeeklyRankingBatch()
    return batch.run_weekly_ranking_batch()


if __name__ == "__main__":
    # 手動実行用
    success = run_batch()
    if success:
        print("✅ 週間ランキングバッチ処理が正常に完了しました")
    else:
        print("❌ 週間ランキングバッチ処理でエラーが発生しました")
