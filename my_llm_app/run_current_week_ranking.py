#!/usr/bin/env python3
"""
今週の週間ランキングを手動で実行するスクリプト
"""

import datetime
from weekly_ranking_batch import WeeklyRankingBatch

def run_current_week_ranking():
    """今週の週間ランキングを計算・保存"""
    batch = WeeklyRankingBatch()
    
    # 今週の月曜日を取得
    today = datetime.datetime.now(datetime.timezone.utc)
    week_start = today - datetime.timedelta(days=today.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    
    print(f"今週のランキング計算開始: {week_start}")
    
    # 週間ランキング計算
    ranking_data = batch.calculate_weekly_ranking(week_start)
    
    if ranking_data:
        # ランキング保存
        batch.save_weekly_ranking(ranking_data, week_start)
        print(f"✅ 今週のランキング保存完了: {len(ranking_data)}名")
        
        # 上位5位を表示
        print("\n🏆 今週の上位5位:")
        for i, user in enumerate(ranking_data[:5], 1):
            print(f"{i}位: {user.nickname} - 週間ポイント: {user.weekly_points}, 総ポイント: {user.total_points}")
    else:
        print("❌ ランキングデータの計算に失敗しました")

if __name__ == "__main__":
    run_current_week_ranking()
