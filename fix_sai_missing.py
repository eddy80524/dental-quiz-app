#!/usr/bin/env python3
"""
gakushi-2023-1再.jsonファイル内のnumberとimage_pathsから「再」を修正するスクリプト
G23-1-A-XX → G23-1再-A-XX に修正
"""

import json
import re
from datetime import datetime

def fix_sai_in_json():
    file_path = "my_llm_app/data/gakushi-2023-1再.json"
    backup_path = f"{file_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    print(f"📂 処理対象: {file_path}")
    
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
    
    modified_numbers = 0
    modified_images = 0
    
    print("🔧 修正プロセス開始...")
    print("-" * 50)
    
    for i, question in enumerate(data):
        # numberフィールドの修正
        if 'number' in question:
            original_number = question['number']
            # G23-1-A-XX → G23-1再-A-XX パターンを修正
            if re.match(r'G23-1-[A-D]-\d+', original_number):
                new_number = re.sub(r'G23-1-([A-D]-\d+)', r'G23-1再-\1', original_number)
                if new_number != original_number:
                    question['number'] = new_number
                    modified_numbers += 1
                    print(f"🔄 Number修正: {original_number} → {new_number}")
        
        # image_pathsフィールドの修正
        if 'image_paths' in question and isinstance(question['image_paths'], list):
            for j, image_path in enumerate(question['image_paths']):
                # G23-1-A-XXa.jpg → G23-1再-A-XXa.jpg パターンを修正
                if re.match(r'G23-1-[A-D]-\d+[a-z]\.jpg', image_path):
                    new_image_path = re.sub(r'G23-1-([A-D]-\d+[a-z]\.jpg)', r'G23-1再-\1', image_path)
                    if new_image_path != image_path:
                        question['image_paths'][j] = new_image_path
                        modified_images += 1
                        print(f"🖼️ Image修正: {image_path} → {new_image_path}")
    
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
    print(f"  - 修正されたnumber数: {modified_numbers}")
    print(f"  - 修正されたimage数: {modified_images}")
    
    if modified_numbers == 0 and modified_images == 0:
        print("ℹ️  修正が必要な項目はありませんでした。")
    else:
        print("🎉 修正完了！")

if __name__ == "__main__":
    fix_sai_in_json()
