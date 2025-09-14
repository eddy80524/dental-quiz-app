#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Firestoreから直接cardsデータを取得して分析
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'my_llm_app'))

from user_data_extractor import UserDataExtractor
import firebase_admin
from firebase_admin import credentials, firestore

def analyze_cards_directly():
    uid = "wLAvgm5MPZRnNwTZgFrl9iydUR33"
    
    # UserDataExtractorを使ってFirestore接続を初期化
    extractor = UserDataExtractor()
    db_client = extractor.db
    
    # Firestoreから直接cardsを取得
    try:
        cards_ref = db_client.collection('users').document(uid).collection('cards')
        cards_docs = cards_ref.get()
        
        print(f"cardsコレクションの総ドキュメント数: {len(cards_docs)}")
        
        cards_dict = {}
        learned_count = 0
        
        def calculate_card_level(card_data):
            if not card_data:
                return "未学習"
            
            interval = card_data.get('interval', 0)
            repetitions = card_data.get('repetitions', 0)
            
            if interval <= 0 or repetitions == 0:
                return "未学習"
            elif interval <= 1:
                return "新規学習"
            elif interval <= 6:
                return "短期記憶"
            elif interval <= 30:
                return "中期記憶"
            else:
                return "長期記憶"
        
        kokushi_learned = set()
        gakushi_learned = set()
        
        for doc in cards_docs:
            question_id = doc.id
            card_data = doc.to_dict()
            cards_dict[question_id] = card_data
            
            level = calculate_card_level(card_data)
            if level != "未学習":
                learned_count += 1
                if question_id.startswith('G'):
                    gakushi_learned.add(question_id)
                else:
                    kokushi_learned.add(question_id)
        
        print(f"学習済みカード数: {learned_count}")
        print(f"国試学習済み: {len(kokushi_learned)}")
        print(f"学士学習済み: {len(gakushi_learned)}")
        
        # サンプル表示
        print(f"\n=== サンプルカードデータ（最初の5件） ===")
        for i, (qid, card_data) in enumerate(list(cards_dict.items())[:5]):
            level = calculate_card_level(card_data)
            print(f"{i+1}. {qid}: {level}, interval={card_data.get('interval', 0)}, reps={card_data.get('repetitions', 0)}")
        
        return cards_dict, kokushi_learned
        
    except Exception as e:
        print(f"Firestoreからのデータ取得エラー: {e}")
        return {}, set()

if __name__ == "__main__":
    analyze_cards_directly()
