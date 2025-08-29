#!/usr/bin/env python3
"""
現在の学習データのタイムスタンプを確認し、今週のデータがあるかチェック
"""

import datetime
from firestore_db import get_firestore_manager

def check_recent_activity():
    """最近の学習アクティビティを確認"""
    manager = get_firestore_manager()
    
    # 今週の月曜日を取得
    today = datetime.datetime.now(datetime.timezone.utc)
    week_start = today - datetime.timedelta(days=today.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    
    print(f"今週の範囲: {week_start} 〜 {week_start + datetime.timedelta(days=7)}")
    print(f"現在日時: {today}")
    
    # アクティブユーザーを取得
    users_ref = manager.db.collection("users").limit(5)
    users_docs = users_ref.stream()
    
    for doc in users_docs:
        user_data = doc.to_dict()
        email = user_data.get("email", "Unknown")
        print(f"\n=== ユーザー: {email} ({doc.id}) ===")
        
        # カードデータを確認
        cards = manager.load_user_cards(doc.id)
        print(f"カード数: {len(cards)}")
        
        if len(cards) > 0:
            # 最新のhistoryを5件確認
            recent_history = []
            for card in list(cards.values())[:5]:  # 最初の5カードのhistoryをチェック
                history = card.get("history", [])
                for record in history[-3:]:  # 最新3件
                    timestamp_str = record.get("timestamp", "")
                    quality = record.get("quality", 0)
                    recent_history.append({
                        "timestamp": timestamp_str,
                        "quality": quality
                    })
            
            # 最新5件を表示
            for i, record in enumerate(recent_history[:5]):
                timestamp_str = record["timestamp"]
                quality = record["quality"]
                try:
                    timestamp = datetime.datetime.fromisoformat(timestamp_str)
                    is_this_week = week_start <= timestamp < week_start + datetime.timedelta(days=7)
                    print(f"  {i+1}. {timestamp} (Quality: {quality}) {'✓今週' if is_this_week else '過去'}")
                except:
                    print(f"  {i+1}. {timestamp_str} (Quality: {quality}) エラー")

if __name__ == "__main__":
    check_recent_activity()
