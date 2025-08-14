#!/usr/bin/env python3
"""
JSONファイル内の全角数字を半角数字に変換するスクリプト
"""

import json
import os
import re
from pathlib import Path

def convert_fullwidth_to_halfwidth(text):
    """
    全角数字を半角数字に変換する関数
    ただし、特定の記号（①②③など）は除外
    """
    if not isinstance(text, str):
        return text
    
    # 全角数字から半角数字への変換テーブル
    fullwidth_digits = "０１２３４５６７８９"
    halfwidth_digits = "0123456789"
    
    # 変換テーブルを作成
    translation_table = str.maketrans(fullwidth_digits, halfwidth_digits)
    
    # 変換実行（丸数字などの特殊記号は除外）
    converted_text = text.translate(translation_table)
    
    return converted_text

def process_json_recursively(data):
    """
    JSON データを再帰的に処理して全角数字を半角に変換
    """
    if isinstance(data, dict):
        return {key: process_json_recursively(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [process_json_recursively(item) for item in data]
    elif isinstance(data, str):
        return convert_fullwidth_to_halfwidth(data)
    else:
        return data

def convert_json_file(file_path):
    """
    JSONファイルの全角数字を半角に変換
    """
    try:
        # JSONファイルを読み込み
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 全角数字を半角に変換
        converted_data = process_json_recursively(data)
        
        # バックアップファイルを作成
        backup_path = file_path.with_suffix('.json.backup')
        with open(backup_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        # 変換後のデータを保存
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(converted_data, f, ensure_ascii=False, indent=2)
        
        print(f"✅ 変換完了: {file_path.name}")
        print(f"   📁 バックアップ: {backup_path.name}")
        
        return True
        
    except Exception as e:
        print(f"❌ エラー: {file_path.name} - {str(e)}")
        return False

def main():
    """
    my_llm_app/data内の全てのJSONファイルを処理
    """
    data_dir = Path("/Users/utsueito/kokushi-dx-poc/dental-DX-PoC/my_llm_app/data")
    
    if not data_dir.exists():
        print(f"❌ ディレクトリが見つかりません: {data_dir}")
        return
    
    # JSONファイルを検索
    json_files = list(data_dir.glob("*.json"))
    
    if not json_files:
        print("❌ JSONファイルが見つかりません")
        return
    
    print(f"📄 {len(json_files)}個のJSONファイルを処理します...\n")
    
    success_count = 0
    for json_file in json_files:
        if convert_json_file(json_file):
            success_count += 1
        print()
    
    print(f"🎯 処理完了: {success_count}/{len(json_files)}個のファイルが正常に変換されました")

if __name__ == "__main__":
    main()
