#!/usr/bin/env python3
"""
実際のJSONデータから科目を抽出するスクリプト
国試問題と学士試験問題の科目を分けて表示
"""

import os
import json
from collections import Counter

def extract_subjects_from_data():
    """JSONデータから実際の科目を抽出"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(script_dir, 'my_llm_app', 'data')
    
    # 読み込むファイル
    files_to_load = [
        'master_questions_final.json', 
        'gakushi-2022-1-1.json', 
        'gakushi-2022-1-2.json', 
        'gakushi-2022-1-3.json', 
        'gakushi-2022-1再.json',  
        'gakushi-2022-2.json', 
        'gakushi-2023-1-1.json',
        'gakushi-2023-1-2.json',
        'gakushi-2023-1-3.json',
        'gakushi-2023-1再.json', 
        'gakushi-2023-2.json',
        'gakushi-2023-2再.json',
        'gakushi-2024-1-1.json', 
        'gakushi-2024-2.json', 
        'gakushi-2025-1-1.json'
    ]
    
    kokushi_subjects = set()
    gakushi_subjects = set()
    
    for filename in files_to_load:
        file_path = os.path.join(data_dir, filename)
        if not os.path.exists(file_path):
            print(f"ファイルが見つかりません: {filename}")
            continue
            
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            questions = []
            if isinstance(data, dict):
                questions = data.get('questions', [])
            elif isinstance(data, list):
                questions = data
            
            for q in questions:
                subject = q.get('subject', '未分類')
                number = q.get('number', '')
                
                if not subject or subject == '（未分類）':
                    continue
                
                # 国試問題か学士試験問題かを判定
                if number.startswith('G'):
                    gakushi_subjects.add(subject)
                else:
                    kokushi_subjects.add(subject)
                    
            print(f"処理完了: {filename} - 問題数: {len(questions)}")
            
        except Exception as e:
            print(f"エラー in {filename}: {e}")
    
    return sorted(list(kokushi_subjects)), sorted(list(gakushi_subjects))

if __name__ == "__main__":
    print("=== 実際のJSONデータから科目を抽出中 ===")
    
    kokushi_subjects, gakushi_subjects = extract_subjects_from_data()
    
    print("\n=== 国試問題の科目 ===")
    for i, subject in enumerate(kokushi_subjects, 1):
        print(f"{i:2d}. {subject}")
    
    print(f"\n国試問題の科目数: {len(kokushi_subjects)}")
    
    print("\n=== 学士試験問題の科目 ===")
    for i, subject in enumerate(gakushi_subjects, 1):
        print(f"{i:2d}. {subject}")
    
    print(f"\n学士試験問題の科目数: {len(gakushi_subjects)}")
    
    print("\n=== 両方に共通する科目 ===")
    common_subjects = sorted(list(set(kokushi_subjects) & set(gakushi_subjects)))
    for i, subject in enumerate(common_subjects, 1):
        print(f"{i:2d}. {subject}")
    
    print(f"\n共通科目数: {len(common_subjects)}")
    
    print("\n=== 国試のみの科目 ===")
    kokushi_only = sorted(list(set(kokushi_subjects) - set(gakushi_subjects)))
    for i, subject in enumerate(kokushi_only, 1):
        print(f"{i:2d}. {subject}")
    
    print("\n=== 学士のみの科目 ===")
    gakushi_only = sorted(list(set(gakushi_subjects) - set(kokushi_subjects)))
    for i, subject in enumerate(gakushi_only, 1):
        print(f"{i:2d}. {subject}")
