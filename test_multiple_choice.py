#!/usr/bin/env python3
"""
複数選択問題の判定テスト
103A38の「AC」問題を検証
"""

import sys
import os
sys.path.append('/Users/utsueito/kokushi-dx-poc/dental-DX-PoC/my_llm_app')

from utils import QuestionUtils

def test_multiple_choice_answer():
    """複数選択問題の答え判定をテスト"""
    
    print("=== 複数選択問題判定テスト ===")
    
    # テストケース1: 103A38の実際の問題
    test_cases = [
        # (ユーザー回答, 正答, 期待結果)
        ("AC", "AC", True),   # 正しい順序
        ("CA", "AC", True),   # 逆順でも正解
        ("A", "AC", False),   # 1つだけ選択
        ("C", "AC", False),   # 1つだけ選択
        ("AB", "AC", False),  # 間違った組み合わせ
        ("BC", "AC", False),  # 間違った組み合わせ
        ("ABC", "AC", False), # 多すぎる選択
        ("ac", "AC", True),   # 大文字小文字の違い
        ("", "AC", False),    # 空の回答
    ]
    
    print("103A38問題テスト:")
    print("正答: AC (Turner症候群 + Klinefelter症候群)")
    print()
    
    for user_answer, correct_answer, expected in test_cases:
        result = QuestionUtils.check_answer(user_answer, correct_answer)
        status = "✅ PASS" if result == expected else "❌ FAIL"
        print(f"{status} ユーザー回答: '{user_answer}' vs 正答: '{correct_answer}' -> 判定: {result} (期待: {expected})")
    
    print("\n=== 表示フォーマットテスト ===")
    
    # 表示テストケース
    format_cases = [
        ("A", "A"),
        ("AC", "A と C"),
        ("ABC", "A、B と C"),
        ("A/B", "A または B"),
        ("AD/BC/CD", "AD、BC または CD"),
    ]
    
    for answer, expected_format in format_cases:
        formatted = QuestionUtils.format_answer_display(answer)
        print(f"正答: '{answer}' -> 表示: '{formatted}' (期待: '{expected_format}')")

if __name__ == "__main__":
    test_multiple_choice_answer()
