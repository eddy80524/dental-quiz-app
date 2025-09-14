#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
341個のユニーク問題 vs 315個の学習済みカードの差を調査
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'my_llm_app'))

from user_data_extractor import UserDataExtractor
import streamlit as st

def analyze_cards_vs_logs():
    """cardsデータとevaluation_logsの差を分析"""
    
    uid = input("分析するユーザーID: ")
    
    extractor = UserDataExtractor()
    
    # evaluation_logsからユニークな問題IDを取得
    evaluation_logs = extractor.extract_self_evaluation_logs(uid)
    unique_questions_in_logs = set(log.get('question_id', '') for log in evaluation_logs)
    kokushi_questions_in_logs = set(qid for qid in unique_questions_in_logs if not qid.startswith('G'))
    
    print(f"evaluation_logs内のユニーク国試問題数: {len(kokushi_questions_in_logs)}")
    
    # cardsデータを取得
    card_levels = extractor.extract_card_levels(uid, studied_only=False, exam_type_filter="国試")
    print(f"card_levelsデータの総件数: {len(card_levels) if card_levels is not None else 0}")
    
    if card_levels is None:
        print("card_levelsデータが取得できませんでした")
        return
    
    # cardsから学習済みの国試問題を抽出
    learned_cards_kokushi = set()
    for _, row in card_levels.iterrows():
        question_id = row.get('question_id', '')
        level = row.get('level', '未学習')
        if level != "未学習":
            learned_cards_kokushi.add(question_id)
    
    print(f"cards内の学習済み国試問題数: {len(learned_cards_kokushi)}")
    
    # 差分分析
    in_logs_not_in_cards = kokushi_questions_in_logs - learned_cards_kokushi
    in_cards_not_in_logs = learned_cards_kokushi - kokushi_questions_in_logs
    
    print(f"\n=== 差分分析 ===")
    print(f"evaluation_logsにあってcardsで学習済みでない問題: {len(in_logs_not_in_cards)}問")
    print(f"cardsで学習済みだがevaluation_logsにない問題: {len(in_cards_not_in_logs)}問")
    
    if in_logs_not_in_cards:
        print(f"\n=== evaluation_logsにあってcardsで学習済みでない問題（最初の10件） ===")
        for i, qid in enumerate(list(in_logs_not_in_cards)[:10]):
            # card_levelsからそのquestion_idの情報を取得
            matching_rows = card_levels[card_levels['question_id'] == qid]
            if not matching_rows.empty:
                level = matching_rows.iloc[0]['level']
                print(f"{i+1}. {qid}: level={level}")
            else:
                print(f"{i+1}. {qid}: カードデータなし")
    
    if in_cards_not_in_logs:
        print(f"\n=== cardsで学習済みだがevaluation_logsにない問題（最初の10件） ===")
        for i, qid in enumerate(list(in_cards_not_in_logs)[:10]):
            matching_rows = card_levels[card_levels['question_id'] == qid]
            if not matching_rows.empty:
                level = matching_rows.iloc[0]['level']
                print(f"{i+1}. {qid}: level={level}")
            else:
                print(f"{i+1}. {qid}: カードデータなし")

if __name__ == "__main__":
    analyze_cards_vs_logs()
