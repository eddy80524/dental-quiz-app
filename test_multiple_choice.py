#!/usr/bin/env python3
"""
複数選択と自由入力問題の判定テスト
103A38の「AC」問題に加え、順序問題や数値入力の検証を実施
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


def test_order_sensitive_answer():
    """順序や数値入力を伴う問題の判定をテスト"""

    print("\n=== 順序・数値入力判定テスト ===")

    order_cases = [
        ("ABDCE", "ABDCE", True),       # 正しい順序
        ("ABCDE", "ABDCE", False),       # 並びが異なる
        ("ABDCE", "ABDCE/ACBDE", True), # 複数の正しい順序
        ("60", "60", True),              # 数値正解
        ("059", "60", False),            # 数値が異なる
    ]

    for user_answer, correct_answer, expected in order_cases:
        result = QuestionUtils.check_answer(
            user_answer,
            correct_answer,
            order_sensitive=True
        )
        status = "✅ PASS" if result == expected else "❌ FAIL"
        print(
            f"{status} ユーザー回答: '{user_answer}' vs 正答: '{correct_answer}' -> 判定: {result} (期待: {expected})"
        )

    print("\n=== 順序判定ヘルパーテスト ===")

    ordering_question = {
        "question": "（A、B）間の操作で器具を使用した順番に並べよ。",
        "choices": ["ア", "イ", "ウ"],
        "answer": "ABC"
    }
    numeric_question = {
        "question": "FMIAが49.5度の場合の値を求めよ。",
        "choices": [],
        "answer": "60"
    }
    multi_choice_question = {
        "question": "適切な組み合わせを2つ選べ。",
        "choices": ["選択肢A", "選択肢B", "選択肢C"],
        "answer": "AC"
    }

    print(
        "並べ替え問題 =>",
        QuestionUtils.requires_order_sensitive_check(
            ordering_question,
            manual_input_used=True,
            user_answer="ABC"
        )
    )
    print(
        "数値入力問題 =>",
        QuestionUtils.requires_order_sensitive_check(
            numeric_question,
            manual_input_used=True,
            user_answer="60"
        )
    )
    print(
        "通常の複数選択 =>",
        QuestionUtils.requires_order_sensitive_check(
            multi_choice_question,
            manual_input_used=False,
            user_answer=""
        )
    )


if __name__ == "__main__":
    test_multiple_choice_answer()
    test_order_sensitive_answer()
