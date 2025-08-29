#!/usr/bin/env python3
"""
実際の学習データがある週でランキングを計算するスクリプト
"""

import datetime
from weekly_ranking_batch import WeeklyRankingBatch

def run_august_16_week_ranking():
    """2025-08-16を含む週のランキングを計算・保存"""
    batch = WeeklyRankingBatch()
    
    # 2025-08-16を含む週の月曜日を取得（2025-08-12）
    target_date = datetime.datetime(2025, 8, 16, tzinfo=datetime.timezone.utc)
    week_start = target_date - datetime.timedelta(days=target_date.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    
    print(f"実データがある週のランキング計算開始: {week_start}")
    print(f"範囲: {week_start} 〜 {week_start + datetime.timedelta(days=7)}")
    
    # 週間ランキング計算
    ranking_data = batch.calculate_weekly_ranking(week_start)
    
    if ranking_data:
        # ランキング保存
        batch.save_weekly_ranking(ranking_data, week_start)
        print(f"✅ {week_start.strftime('%Y-%m-%d')}週のランキング保存完了: {len(ranking_data)}名")
        
        # 週間ポイントがある上位5位を表示
        print("\n🏆 週間ポイントがある上位5位:")
        weekly_active = [user for user in ranking_data if user.weekly_points > 0]
        for i, user in enumerate(weekly_active[:5], 1):
            print(f"{i}位: {user.nickname} - 週間ポイント: {user.weekly_points}, 総ポイント: {user.total_points}")
        
        if len(weekly_active) == 0:
            print("この週に学習アクティビティがあるユーザーはいませんでした。")
            print("\n📊 総ポイント上位5位:")
            for i, user in enumerate(ranking_data[:5], 1):
                print(f"{i}位: {user.nickname} - 総ポイント: {user.total_points}")
    else:
        print("❌ ランキングデータの計算に失敗しました")

if __name__ == "__main__":
    run_august_16_week_ranking()
