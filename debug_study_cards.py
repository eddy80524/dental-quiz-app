#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
study_cardsコレクションから実際のcardsデータを分析
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'my_llm_app'))

from user_data_extractor import UserDataExtractor

def analyze_study_cards():
    uid = "wLAvgm5MPZRnNwTZgFrl9iydUR33"
    
    # UserDataExtractorを使ってFirestore接続を初期化
    extractor = UserDataExtractor()
    db_client = extractor.db
    
    # Firestoreから直接study_cardsを取得
    try:
        study_cards_ref = db_client.collection("study_cards")
        user_cards_query = study_cards_ref.where("uid", "==", uid)
        user_cards_docs = user_cards_query.get()
        
        print(f"study_cardsコレクションの該当ドキュメント数: {len(user_cards_docs)}")
        
        cards_dict = {}
        learned_count = 0
        
        def calculate_card_level_from_sm2(sm2_data):
            if not sm2_data:
                return "未学習"
            
            interval = sm2_data.get('interval', 0)
            n = sm2_data.get('n', 0)
            
            if interval <= 0 or n == 0:
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
        
        for doc in user_cards_docs:
            try:
                card_data = doc.to_dict()
                # ドキュメントIDからquestion_idを抽出
                doc_id = doc.id
                question_id = doc_id.split('_')[-1] if '_' in doc_id else doc_id
                
                sm2_data = card_data.get("sm2_data", {})
                level = calculate_card_level_from_sm2(sm2_data)
                
                cards_dict[question_id] = {
                    'doc_id': doc_id,
                    'level': level,
                    'sm2_data': sm2_data
                }
                
                if level != "未学習":
                    learned_count += 1
                    if question_id.startswith('G'):
                        gakushi_learned.add(question_id)
                    else:
                        kokushi_learned.add(question_id)
                        
            except Exception as e:
                print(f"ドキュメント処理エラー ({doc.id}): {e}")
                continue
        
        print(f"学習済みカード数: {learned_count}")
        print(f"国試学習済み: {len(kokushi_learned)}")
        print(f"学士学習済み: {len(gakushi_learned)}")
        
        # サンプル表示
        print(f"\n=== サンプルカードデータ（最初の5件） ===")
        for i, (qid, card_info) in enumerate(list(cards_dict.items())[:5]):
            sm2 = card_info['sm2_data']
            print(f"{i+1}. {qid}: {card_info['level']}, interval={sm2.get('interval', 0)}, n={sm2.get('n', 0)}")
        
        return cards_dict, kokushi_learned
        
    except Exception as e:
        print(f"study_cardsからのデータ取得エラー: {e}")
        return {}, set()

if __name__ == "__main__":
    analyze_study_cards()
