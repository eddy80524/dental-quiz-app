#!/usr/bin/env python3
"""
保存されている週間ランキングデータを確認するスクリプト
"""

import datetime
from firestore_db import get_firestore_manager

def check_saved_rankings():
    """保存された週間ランキングデータを確認"""
    manager = get_firestore_manager()
    
    print("=== 保存されている週間ランキングデータ ===")
    
    # 週間ランキングコレクションの全ドキュメントを取得
    from firebase_admin import firestore
    rankings_ref = manager.db.collection("weekly_rankings").order_by("week_start", direction=firestore.Query.DESCENDING).limit(10)
    rankings_docs = rankings_ref.stream()
    
    ranking_found = False
    for doc in rankings_docs:
        ranking_found = True
        data = doc.to_dict()
        week_id = doc.id
        week_start = data.get("week_start", "Unknown")
        total_participants = data.get("total_participants", 0)
        rankings = data.get("rankings", [])
        
        print(f"\n📅 週間ランキング: {week_id}")
        print(f"   期間: {week_start}")
        print(f"   参加者数: {total_participants}")
        print(f"   ランキング件数: {len(rankings)}")
        
        # 上位5位を表示
        if rankings:
            print("   🏆 上位5位:")
            for i, user in enumerate(rankings[:5], 1):
                nickname = user.get("nickname", "Unknown")
                weekly_points = user.get("weekly_points", 0)
                total_points = user.get("total_points", 0)
                print(f"     {i}位: {nickname} - 週間: {weekly_points}pt, 総合: {total_points}pt")
    
    if not ranking_found:
        print("❌ 保存された週間ランキングデータが見つかりません")
    
    print("\n=== fetch_ranking_data 関数の動作テスト ===")
    
    # fetch_ranking_data 関数のテスト
    ranking_data = manager.fetch_ranking_data()
    print(f"fetch_ranking_data 結果: {len(ranking_data)}件")
    
    if ranking_data:
        print("🏆 上位5位:")
        for i, user in enumerate(ranking_data[:5], 1):
            nickname = user.get("nickname", "Unknown")
            weekly_points = user.get("weekly_points", 0)
            total_points = user.get("total_points", 0)
            uid = user.get("uid", "Unknown")
            print(f"  {i}位: {nickname} (uid: {uid[:8]}...) - 週間: {weekly_points}pt, 総合: {total_points}pt")

if __name__ == "__main__":
    check_saved_rankings()
