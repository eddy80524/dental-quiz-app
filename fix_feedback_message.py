#!/usr/bin/env python3
"""
practice_page.pyのget_answer_feedback_message呼び出しを修正するスクリプト
"""

import re

def fix_practice_page():
    file_path = "my_llm_app/modules/practice_page.py"
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # パターン1: 正解時の呼び出し（Trueパラメータ付き）
    pattern1 = r'(from utils import QuestionUtils\s*\n\s*main_msg, additional_info = QuestionUtils\.get_answer_feedback_message\(\s*\n\s*user_ans, correct_answer, True\s*\n\s*\))'
    
    replacement1 = '''# 問題の選択肢情報を取得
                        question = next((q for q in questions if q.get('number') == qid), None)
                        question_choices = question.get('choices', []) if question else []
                        
                        from utils import QuestionUtils
                        main_msg, additional_info = QuestionUtils.get_answer_feedback_message(
                            user_ans, correct_answer, True, question_choices
                        )'''
    
    # パターン2: 不正解時の呼び出し（Falseパラメータ付き）
    pattern2 = r'(from utils import QuestionUtils\s*\n\s*main_msg, additional_info = QuestionUtils\.get_answer_feedback_message\(\s*\n\s*user_ans, correct_answer, False\s*\n\s*\))'
    
    replacement2 = '''# 問題の選択肢情報を取得
                        question = next((q for q in questions if q.get('number') == qid), None)
                        question_choices = question.get('choices', []) if question else []
                        
                        from utils import QuestionUtils
                        main_msg, additional_info = QuestionUtils.get_answer_feedback_message(
                            user_ans, correct_answer, False, question_choices
                        )'''
    
    # パターン3: その他の呼び出し形式
    pattern3 = r'(_, additional_info = QuestionUtils\.get_answer_feedback_message\(\s*\n\s*user_ans, correct_answer, False\s*\n\s*\))'
    
    replacement3 = '''# 問題の選択肢情報を取得
                                question = next((q for q in questions if q.get('number') == qid), None)
                                question_choices = question.get('choices', []) if question else []
                                
                                _, additional_info = QuestionUtils.get_answer_feedback_message(
                                    user_ans, correct_answer, False, question_choices
                                )'''
    
    # 置換を実行
    modified = False
    
    # Trueパラメータの置換
    new_content = re.sub(pattern1, replacement1, content, flags=re.MULTILINE | re.DOTALL)
    if new_content != content:
        content = new_content
        modified = True
        print("✅ True parameters fixed")
    
    # Falseパラメータの置換
    new_content = re.sub(pattern2, replacement2, content, flags=re.MULTILINE | re.DOTALL)
    if new_content != content:
        content = new_content
        modified = True
        print("✅ False parameters fixed")
    
    # その他の形式の置換
    new_content = re.sub(pattern3, replacement3, content, flags=re.MULTILINE | re.DOTALL)
    if new_content != content:
        content = new_content
        modified = True
        print("✅ Other patterns fixed")
    
    # 簡単なパターンでの置換も試行
    simple_pattern = r'QuestionUtils\.get_answer_feedback_message\(\s*\n\s*user_ans, correct_answer, (True|False)\s*\n\s*\)'
    def replace_simple(match):
        is_correct = match.group(1)
        return f'''QuestionUtils.get_answer_feedback_message(
                            user_ans, correct_answer, {is_correct}, question_choices
                        )'''
    
    new_content = re.sub(simple_pattern, replace_simple, content, flags=re.MULTILINE)
    if new_content != content:
        content = new_content
        modified = True
        print("✅ Simple patterns fixed")
    
    if modified:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"📝 Modified {file_path}")
        return True
    else:
        print("❌ No patterns found to modify")
        return False

if __name__ == "__main__":
    fix_practice_page()
