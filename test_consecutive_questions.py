#!/usr/bin/env python3
"""
連問表示機能の単体テスト
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'my_llm_app'))

from utils import CardSelectionUtils, ALL_QUESTIONS_DICT

def test_consecutive_grouping():
    """連問グループ化のテスト"""
    print("=== 連問グループ化テスト ===")
    
    # テスト用問題ID（102D症例を含む）
    test_qids = ['102D13', '102D14', '103A15', '104B20', '105C21']
    
    print(f"テスト問題ID: {test_qids}")
    
    # グループ化実行
    grouped = CardSelectionUtils.group_consecutive_questions(test_qids, ALL_QUESTIONS_DICT)
    
    print(f"\nグループ化結果:")
    for i, group in enumerate(grouped):
        print(f"グループ {i+1}: {group}")
        
        # 各問題の詳細を表示
        for qid in group:
            question = ALL_QUESTIONS_DICT.get(qid)
            if question:
                case_id = question.get('case_id', 'なし')
                question_text = question.get('question', 'なし')[:50] + '...' if len(question.get('question', '')) > 50 else question.get('question', 'なし')
                print(f"  - {qid}: case_id={case_id}, 問題='{question_text}'")
            else:
                print(f"  - {qid}: 問題が見つかりません")
    
    # 102D13と102D14が同じグループになっているかチェック
    for group in grouped:
        if '102D13' in group and '102D14' in group:
            print(f"\n✅ 102D13と102D14が同じグループになりました: {group}")
            return True
    
    print(f"\n❌ 102D13と102D14が別々のグループになっています")
    return False

def test_case_data():
    """症例データのテスト"""
    print("\n=== 症例データテスト ===")
    
    # 102D13の問題データを確認
    question_102d13 = ALL_QUESTIONS_DICT.get('102D13')
    question_102d14 = ALL_QUESTIONS_DICT.get('102D14')
    
    if question_102d13:
        print(f"102D13が見つかりました:")
        print(f"  case_id: {question_102d13.get('case_id', 'なし')}")
        print(f"  問題文: {question_102d13.get('question', 'なし')}")
        print(f"  選択肢数: {len(question_102d13.get('choices', []))}")
    else:
        print("102D13が見つかりません")
    
    if question_102d14:
        print(f"\n102D14が見つかりました:")
        print(f"  case_id: {question_102d14.get('case_id', 'なし')}")
        print(f"  問題文: {question_102d14.get('question', 'なし')}")
        print(f"  選択肢数: {len(question_102d14.get('choices', []))}")
    else:
        print("102D14が見つかりません")
    
    # 症例データを確認
    from utils import CASES
    case_id = 'case-102D-13-14'
    if case_id in CASES:
        case_data = CASES[case_id]
        print(f"\n症例データが見つかりました ({case_id}):")
        print(f"  症例文: {case_data.get('scenario_text', 'なし')[:100]}...")
        print(f"  画像URL数: {len(case_data.get('image_urls', []))}")
    else:
        print(f"\n症例データが見つかりません ({case_id})")
        print(f"利用可能な症例ID: {list(CASES.keys())[:5]}...")

if __name__ == "__main__":
    print("連問表示機能テスト開始\n")
    
    # データ読み込み確認
    print(f"総問題数: {len(ALL_QUESTIONS_DICT)}")
    
    # テスト実行
    test_case_data()
    success = test_consecutive_grouping()
    
    print(f"\n=== テスト結果 ===")
    print(f"連問グループ化: {'✅ 成功' if success else '❌ 失敗'}")
