#!/usr/bin/env python3
"""
gakushi-2022-1-1.jsonファイル内の選択肢から「a 」「b 」「c 」「d 」「e 」プレフィックスを削除するスクリプト
"""

import json
import re
from datetime import datetime

def fix_choice_prefixes():
    file_path = "functions/my_llm_app/data/gakushi-2022-1-1.json"
    backup_path = f"{file_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    print(f"📂 処理対象: {file_path}")
    print(f"🔧 修正対象: 選択肢から「a 」「b 」「c 」「d 」「e 」プレフィックスを削除")
    
    # バックアップ作成
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"💾 バックアップ作成: {backup_path}")
    except Exception as e:
        print(f"❌ バックアップ作成エラー: {e}")
        return
    
    # JSONファイル読み込み
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        
        # JSONの構造を確認
        if 'questions' in json_data:
            data = json_data['questions']
        else:
            data = json_data
        
        print(f"📊 総問題数: {len(data)}")
    except Exception as e:
        print(f"❌ JSONファイル読み込みエラー: {e}")
        return
    
    modified_count = 0
    processed_choices = 0
    
    print("🔧 修正プロセス開始...")
    print("-" * 50)
    
    for i, question in enumerate(data):
        # choicesフィールドの修正
        if 'choices' in question and isinstance(question['choices'], list):
            question_modified = False
            for j, choice in enumerate(question['choices']):
                # 「a 」「b 」「c 」「d 」「e 」で始まる選択肢を修正
                if isinstance(choice, str) and re.match(r'^[a-e] ', choice):
                    new_choice = re.sub(r'^[a-e] ', '', choice)
                    question['choices'][j] = new_choice
                    print(f"🔄 {question.get('number', f'Q{i+1}')}: '{choice}' → '{new_choice}'")
                    processed_choices += 1
                    question_modified = True
            
            if question_modified:
                modified_count += 1
    
    # 修正されたJSONファイルを保存
    try:
        # 元の構造を保持
        if 'questions' in json_data:
            json_data['questions'] = data
            final_data = json_data
        else:
            final_data = data
            
        with open(file_path, 'w', encoding='utf-8', newline='\n') as f:
            json.dump(final_data, f, ensure_ascii=False, indent=2)
        print("-" * 50)
        print(f"✅ ファイル保存完了: {file_path}")
    except Exception as e:
        print(f"❌ ファイル保存エラー: {e}")
        return
    
    print(f"📈 修正統計:")
    print(f"  - 修正された問題数: {modified_count}")
    print(f"  - 修正された選択肢数: {processed_choices}")
    
    if processed_choices == 0:
        print("ℹ️  修正が必要な選択肢はありませんでした。")
    else:
        print("🎉 修正完了！")

if __name__ == "__main__":
    fix_choice_prefixes()
