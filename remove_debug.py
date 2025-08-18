#!/usr/bin/env python3
"""デバッグ出力を削除するスクリプト"""

import re

def remove_debug_lines(file_path):
    """ファイルからデバッグ行を削除"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # デバッグprint文を削除
    lines = content.split('\n')
    filtered_lines = []
    
    for line in lines:
        # DEBUG print文をスキップ
        if 'print(f"[DEBUG]' in line or 'print("[DEBUG]' in line:
            continue
        # デバッグ用コメントをスキップ
        if '# DEBUG:' in line or '# デバッグ:' in line:
            continue
        filtered_lines.append(line)
    
    # 書き戻し
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(filtered_lines))
    
    print(f"デバッグ出力を削除しました: {file_path}")

if __name__ == "__main__":
    remove_debug_lines("/Users/utsueito/kokushi-dx-poc/dental-DX-PoC/my_llm_app/app.py")
