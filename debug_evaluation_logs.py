#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
evaluation_logsの詳細分析スクリプト
341個の記録が何を表しているのかを確認
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'my_llm_app'))

from user_data_extractor import UserDataExtractor
from collections import Counter
import json

def analyze_evaluation_logs():
    """evaluation_logsの詳細分析"""
    
    # 実際のユーザーIDを入力してください
    uid = input("分析するユーザーID: ")
    
    extractor = UserDataExtractor()
    evaluation_logs = extractor.extract_self_evaluation_logs(uid)
    
    if not evaluation_logs:
        print("評価ログが見つかりません")
        return
    
    print(f"=== evaluation_logs分析結果 ===")
    print(f"総記録数: {len(evaluation_logs)}")
    
    # question_idの重複分析
    question_ids = [log.get('question_id', '') for log in evaluation_logs]
    question_counter = Counter(question_ids)
    
    unique_questions = len(question_counter)
    total_records = len(evaluation_logs)
    
    print(f"ユニークな問題数: {unique_questions}")
    print(f"総練習記録数: {total_records}")
    print(f"差: {total_records - unique_questions}")
    
    # 複数回練習した問題の詳細
    repeated_questions = {qid: count for qid, count in question_counter.items() if count > 1}
    
    if repeated_questions:
        print(f"\n=== 複数回練習した問題 ===")
        print(f"複数回練習した問題数: {len(repeated_questions)}")
        
        total_repeats = sum(count - 1 for count in repeated_questions.values())
        print(f"復習回数の合計: {total_repeats}")
        
        # 上位10問を表示
        sorted_repeated = sorted(repeated_questions.items(), key=lambda x: x[1], reverse=True)
        print(f"\n復習回数が多い問題（上位10）:")
        for qid, count in sorted_repeated[:10]:
            print(f"  {qid}: {count}回")
    else:
        print("複数回練習した問題はありません")
    
    # 国試 vs 学士の分析
    kokushi_questions = [qid for qid in question_ids if not qid.startswith('G')]
    gakushi_questions = [qid for qid in question_ids if qid.startswith('G')]
    
    print(f"\n=== 試験種別分析 ===")
    print(f"国試問題の記録数: {len(kokushi_questions)}")
    print(f"学士問題の記録数: {len(gakushi_questions)}")
    
    kokushi_unique = len(set(kokushi_questions))
    gakushi_unique = len(set(gakushi_questions))
    
    print(f"国試問題のユニーク数: {kokushi_unique}")
    print(f"学士問題のユニーク数: {gakushi_unique}")
    
    # サンプル表示
    print(f"\n=== サンプルデータ（最初の5件） ===")
    for i, log in enumerate(evaluation_logs[:5]):
        print(f"{i+1}. question_id: {log.get('question_id', 'N/A')}, quality: {log.get('quality', 'N/A')}, timestamp: {log.get('timestamp', 'N/A')}")

if __name__ == "__main__":
    analyze_evaluation_logs()
