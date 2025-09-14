#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
session_stateのcardsデータがどこから来るかを追跡する診断スクリプト
app.pyの_load_user_dataを模倣してデバッグ
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'my_llm_app'))

from user_data_extractor import UserDataExtractor

def debug_app_load_user_data():
    uid = "wLAvgm5MPZRnNwTZgFrl9iydUR33"
    
    extractor = UserDataExtractor()
    db = extractor.db
    
    print(f"=== app.pyの_load_user_dataを模倣してデバッグ ===")
    
    # study_cardsコレクションからユーザーデータを読み込み（app.pyと同じロジック）
    study_cards_ref = db.collection("study_cards")
    user_cards_query = study_cards_ref.where("uid", "==", uid)
    user_cards_docs = user_cards_query.get()
    
    print(f"study_cardsから取得したドキュメント数: {len(user_cards_docs)}")
    
    # カードデータを変換（app.pyと同じロジック）
    cards = {}
    learned_count = 0
    
    for doc in user_cards_docs:
        try:
            card_data = doc.to_dict()
            question_id = doc.id.split('_')[-1] if '_' in doc.id else doc.id
            
            # 既存の形式に変換（app.pyと同じ）
            card = {
                "q_id": question_id,
                "uid": card_data.get("uid", uid),
                "history": card_data.get("history", []),
                "sm2_data": card_data.get("sm2_data", {}),
                "performance": card_data.get("performance", {}),
                "metadata": card_data.get("metadata", {})
            }
            
            # SM2データから既存の形式に変換
            sm2_data = card_data.get("sm2_data", {})
            if sm2_data:
                card.update({
                    "n": sm2_data.get("n", 0),
                    "EF": sm2_data.get("ef", 2.5),
                    "interval": sm2_data.get("interval", 1),
                    "next_review": sm2_data.get("next_review"),
                    "last_review": sm2_data.get("last_review")
                })
            
            cards[question_id] = card
            
        except Exception as card_error:
            print(f"[WARNING] カードデータ処理エラー ({doc.id}): {card_error}")
            continue
    
    print(f"変換後のcardsデータ数: {len(cards)}")
    
    # search_page.pyと同じレベル計算を実行
    def calculate_card_level(card):
        """search_page.pyと同じロジック"""
        if not card or not isinstance(card, dict) or not card.get('history'):
            return "未学習"

        history = card.get('history', [])
        latest = history[-1]
        quality = latest.get('quality', 0)
        
        # 1. 不正解(quality < 3)なら即レベル0
        if quality < 3:
            return "レベル0"

        # 2.【重要】ギリギリ正解(quality == 3)ならレベルを「現状維持」
        if quality == 3:
            if len(history) <= 1:
                return "レベル0"
            else:
                # 直前のレベルを維持するため、再帰的に自身を呼び出す
                previous_level = calculate_card_level({'history': history[:-1]})
                return previous_level

        # 3. 自信のある正解(quality >= 4)の場合のみレベルアップを検討
        confident_successful_reviews = 0
        for review in reversed(history):
            if review.get('quality', 0) >= 4:
                confident_successful_reviews += 1
            else:
                break

        # 4. 自信のある連続正解回数に基づいてレベルを決定
        if confident_successful_reviews == 1:
            return "レベル1"
        elif confident_successful_reviews == 2:
            return "レベル2"
        elif confident_successful_reviews in [3, 4]:
            return "レベル3"
        elif confident_successful_reviews in [5, 6]:
            return "レベル4"
        elif confident_successful_reviews >= 7:
            interval = latest.get('interval', 0)
            ef = latest.get('EF', 2.5)
            if interval > 180 and ef >= 2.8:
                return "習得済み"
            elif interval > 30:
                return "レベル5"
            else:
                return "レベル4"

        return "レベル0"
    
    # 学習済み数を計算
    kokushi_learned = 0
    gakushi_learned = 0
    
    for question_id, card in cards.items():
        level = calculate_card_level(card)
        if level != "未学習":
            if question_id.startswith('G'):
                gakushi_learned += 1
            else:
                kokushi_learned += 1
    
    print(f"app.pyロジックでの学習済み数 - 国試: {kokushi_learned}, 学士: {gakushi_learned}")
    
    # historyを持つカードの数をチェック
    cards_with_history = sum(1 for card in cards.values() if card.get('history'))
    print(f"historyを持つカード数: {cards_with_history}")
    
    # サンプル表示
    print(f"\n=== historyを持つカードのサンプル（最初の5件） ===")
    history_cards = [(qid, card) for qid, card in cards.items() if card.get('history')]
    for i, (qid, card) in enumerate(history_cards[:5]):
        level = calculate_card_level(card)
        history_count = len(card.get('history', []))
        print(f"{i+1}. {qid}: {level}, history件数={history_count}")
        if card.get('history'):
            latest = card['history'][-1]
            print(f"    最新記録: quality={latest.get('quality', 'N/A')}, timestamp={latest.get('timestamp', 'N/A')}")
    
    print(f"\n=== 学習済みカードのサンプル（最初の5件） ===")
    learned_cards = [(qid, card) for qid, card in cards.items() if calculate_card_level(card) != "未学習"]
    for i, (qid, card) in enumerate(learned_cards[:5]):
        level = calculate_card_level(card)
        print(f"{i+1}. {qid}: {level}, interval={card.get('interval', 0)}, n={card.get('n', 0)}")

if __name__ == "__main__":
    debug_app_load_user_data()
