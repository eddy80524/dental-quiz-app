#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
復習スケジュールの詳細分析スクリプト
今日の復習対象 vs 将来の復習予定を確認
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'my_llm_app'))

from user_data_extractor import UserDataExtractor
from modules.search_page import get_review_priority_cards, get_japan_today
import datetime

def analyze_review_schedule():
    uid = "wLAvgm5MPZRnNwTZgFrl9iydUR33"
    
    extractor = UserDataExtractor()
    db_client = extractor.db
    
    # study_cardsからデータを取得
    study_cards_ref = db_client.collection("study_cards")
    user_cards_query = study_cards_ref.where("uid", "==", uid)
    user_cards_docs = user_cards_query.get()
    
    # cardsデータを構築
    cards = {}
    for doc in user_cards_docs:
        card_data = doc.to_dict()
        question_id = doc.id.split('_')[-1] if '_' in doc.id else doc.id
        
        card = {
            "q_id": question_id,
            "history": card_data.get("history", []),
        }
        cards[question_id] = card
    
    print(f"=== 復習スケジュール分析 ===")
    
    today = get_japan_today()
    print(f"今日の日付（日本時間）: {today}")
    
    # 今日の復習対象を取得
    today_priority_cards = get_review_priority_cards(cards, today)
    print(f"\n今日の復習対象: {len(today_priority_cards)}問")
    
    # 期限切れ vs 今日予定の内訳
    overdue_cards = [card for card in today_priority_cards if card[2] > 0]  # 経過日数 > 0
    due_today_cards = [card for card in today_priority_cards if card[2] == 0]  # 今日が復習予定日
    
    print(f"  - 期限切れ: {len(overdue_cards)}問")
    print(f"  - 今日が復習予定日: {len(due_today_cards)}問")
    
    # 将来の復習予定をチェック
    future_days = [1, 2, 3, 7]  # 1日後、2日後、3日後、1週間後
    
    print(f"\n=== 将来の復習予定 ===")
    for days_ahead in future_days:
        future_date = today + datetime.timedelta(days=days_ahead)
        future_priority_cards = get_review_priority_cards(cards, future_date)
        
        # 今日の復習対象を除外して、純粋に将来追加される分のみをカウント
        future_only = len(future_priority_cards) - len(today_priority_cards)
        
        print(f"{days_ahead}日後({future_date}): +{future_only}問追加 (累計: {len(future_priority_cards)}問)")
    
    # 詳細サンプル表示
    print(f"\n=== 期限切れ問題サンプル（上位5件） ===")
    for i, (q_id, priority_score, days_overdue) in enumerate(overdue_cards[:5]):
        print(f"{i+1}. {q_id}: {days_overdue}日遅れ (優先度: {priority_score:.2f})")
    
    print(f"\n=== 今日予定問題サンプル（上位5件） ===")
    for i, (q_id, priority_score, days_overdue) in enumerate(due_today_cards[:5]):
        print(f"{i+1}. {q_id}: 今日が復習日 (優先度: {priority_score:.2f})")
    
    # 学習済みだが復習対象でない問題の数
    total_learned = sum(1 for card in cards.values() if card.get('history'))
    not_due_today = total_learned - len(today_priority_cards)
    print(f"\n学習済みだが今日復習対象でない問題: {not_due_today}問")

if __name__ == "__main__":
    analyze_review_schedule()
