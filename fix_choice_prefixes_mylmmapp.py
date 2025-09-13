#!/usr/bin/env python3
"""
my_llm_app側のgakushi-2022-1-1.jsonファイルから選択肢のプレフィックス（a 、b 、c 、d 、e ）を削除するスクリプト
"""

import json
import re
from datetime import datetime
import shutil
import os

def main():
    # ファイルパス
    input_file = "my_llm_app/data/gakushi-2022-1-1.json"
    
    print(f"📂 処理対象: {input_file}")
    print("🔧 修正対象: 選択肢から「a 」「b 」「c 」「d 」「e 」プレフィックスを削除")
    
    # バックアップファイル作成
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"{input_file}.backup_{timestamp}"
    shutil.copy2(input_file, backup_file)
    print(f"💾 バックアップ作成: {backup_file}")
    
    # JSONファイル読み込み
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # my_llm_app側はquestions配列の中にデータがある
    questions_data = data.get('questions', data)
    print(f"📊 総問題数: {len(questions_data)}")
    
    # 修正カウンター
    modified_questions = 0
    modified_choices = 0
    
    # プレフィックスパターン（a 、b 、c 、d 、e ）
    prefix_pattern = re.compile(r'^([a-e]) (.+)$')
    
    print("🔧 修正プロセス開始...")
    print("-" * 50)
    
    # 各問題を処理
    for question in questions_data:
        question_modified = False
        
        if 'choices' in question and isinstance(question['choices'], list):
            new_choices = []
            
            for choice in question['choices']:
                if isinstance(choice, str):
                    # プレフィックスが存在するかチェック
                    match = prefix_pattern.match(choice)
                    if match:
                        old_choice = choice
                        new_choice = match.group(2)  # プレフィックスを除いた部分
                        new_choices.append(new_choice)
                        
                        # 修正情報を出力
                        print(f"🔄 {question['number']}: '{old_choice}' → '{new_choice}'")
                        
                        modified_choices += 1
                        question_modified = True
                    else:
                        new_choices.append(choice)
                else:
                    new_choices.append(choice)
            
            # 修正があった場合のみ更新
            if question_modified:
                question['choices'] = new_choices
                modified_questions += 1
    
    print("-" * 50)
    
    # questionsキーがある場合は、その構造を保持して保存
    if 'questions' in data:
        data['questions'] = questions_data
    else:
        data = questions_data
    
    # 修正されたJSONファイルを保存
    with open(input_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ ファイル保存完了: {input_file}")
    print(f"📈 修正統計:")
    print(f"  - 修正された問題数: {modified_questions}")
    print(f"  - 修正された選択肢数: {modified_choices}")
    print("🎉 修正完了！")

if __name__ == "__main__":
    main()
