#!/usr/bin/env python3
"""
gakushi-2023-1-3.json の image_paths に "gakushi/2023/1-3/" プレフィックスを追加するスクリプト
"""

import json
import os

def fix_image_paths():
    json_file = "my_llm_app/data/gakushi-2023-1-3.json"
    prefix = "gakushi/2023/1-3/"
    
    # JSONファイルを読み込み
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    total_questions = len(data.get('questions', []))
    modified_count = 0
    modified_images = 0
    
    print(f"📂 処理対象: {json_file}")
    print(f"📊 総問題数: {total_questions}")
    print(f"🔧 追加プレフィックス: '{prefix}'")
    print("-" * 50)
    
    # 各問題の image_paths を確認・修正
    for i, question in enumerate(data.get('questions', [])):
        question_number = question.get('number', f'Question-{i+1}')
        image_paths = question.get('image_paths', [])
        
        if image_paths:
            modified_this_question = False
            new_image_paths = []
            
            for image_path in image_paths:
                # すでにプレフィックスが付いている場合はスキップ
                if image_path.startswith(prefix):
                    new_image_paths.append(image_path)
                    print(f"  ✅ {question_number}: '{image_path}' (already has prefix)")
                else:
                    # プレフィックスを追加
                    new_path = prefix + image_path
                    new_image_paths.append(new_path)
                    print(f"  🔄 {question_number}: '{image_path}' → '{new_path}'")
                    modified_this_question = True
                    modified_images += 1
            
            if modified_this_question:
                question['image_paths'] = new_image_paths
                modified_count += 1
    
    print("-" * 50)
    print(f"📈 修正統計:")
    print(f"  - 修正された問題数: {modified_count}")
    print(f"  - 修正された画像数: {modified_images}")
    
    if modified_count > 0:
        # バックアップファイルを作成
        backup_file = json_file + ".backup"
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"💾 バックアップ作成: {backup_file}")
        
        # 修正されたファイルを保存
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✅ 修正完了: {json_file}")
    else:
        print("ℹ️  修正が必要な画像パスはありませんでした。")

if __name__ == "__main__":
    fix_image_paths()
