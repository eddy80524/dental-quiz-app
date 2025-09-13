#!/usr/bin/env python3
"""
gakushi-2023-1再.jsonファイル内のimage_pathsに'gakushi/2023/1再/'プレフィックスを追加するスクリプト
"""

import json
import re
from datetime import datetime

def add_prefix_to_images():
    file_path = "my_llm_app/data/gakushi-2023-1再.json"
    backup_path = f"{file_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    prefix = "gakushi/2023/1再/"
    
    print(f"📂 処理対象: {file_path}")
    print(f"🔧 追加プレフィックス: '{prefix}'")
    
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
    processed_count = 0
    
    print("🔧 修正プロセス開始...")
    print("-" * 50)
    
    for i, question in enumerate(data):
        # image_pathsフィールドの修正
        if 'image_paths' in question and isinstance(question['image_paths'], list):
            question_modified = False
            for j, image_path in enumerate(question['image_paths']):
                # 既にプレフィックスが付いていない場合のみ追加
                if not image_path.startswith(prefix) and image_path.endswith('.jpg'):
                    new_image_path = prefix + image_path
                    question['image_paths'][j] = new_image_path
                    print(f"🖼️ {question.get('number', f'Q{i+1}')}: '{image_path}' → '{new_image_path}'")
                    modified_count += 1
                    question_modified = True
                elif image_path.startswith(prefix):
                    print(f"✅ {question.get('number', f'Q{i+1}')}: '{image_path}' (already has prefix)")
            
            if question_modified:
                processed_count += 1
    
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
    print(f"  - 修正された問題数: {processed_count}")
    print(f"  - 修正された画像数: {modified_count}")
    
    if modified_count == 0:
        print("ℹ️  修正が必要な画像パスはありませんでした。")
    else:
        print("🎉 修正完了！")

if __name__ == "__main__":
    add_prefix_to_images()
