import re
from typing import List, Dict, Optional, Set
from utils import QuestionUtils

class QuestionFilter:
    """
    問題フィルタリングロジックをカプセル化するクラス
    """

    @staticmethod
    def filter_by_category(questions: List[Dict], category: str, is_gakushi: bool = False) -> List[Dict]:
        """
        カテゴリ（必修、一般、臨床実地）で問題をフィルタリングする
        """
        if category == "全て":
            return questions

        filtered_questions = []
        for q in questions:
            number_str = q.get("number", "")
            try:
                if is_gakushi:
                    # 学士はハイフン区切りの最後が番号 (例: G25-1-1-A-1 -> 1)
                    parts = number_str.split('-')
                    if not parts:
                        continue
                    num = int(parts[-1])
                else:
                    # 国試は末尾の数字を抽出 (例: 117A1 -> 1)
                    match = re.search(r'(\d+)$', number_str)
                    if not match:
                        continue
                    num = int(match.group(1))

                if category == "必修" and 1 <= num <= 20:
                    filtered_questions.append(q)
                elif category == "一般" and 21 <= num <= 65:
                    filtered_questions.append(q)
                elif category == "臨床実地" and 66 <= num <= 90:
                    filtered_questions.append(q)
            except (ValueError, IndexError):
                continue
        
        return filtered_questions

    @staticmethod
    def filter_by_exam_number(all_questions: List[Dict], exam_num: str, section: str = None) -> List[Dict]:
        """
        回数・領域でフィルタリングする
        """
        if not exam_num:
            return []
        
        prefix = exam_num
        if section:
            prefix += section
            
        return [q for q in all_questions if q.get("number", "").startswith(prefix)]

    @staticmethod
    def filter_by_gakushi_year_session_area(all_questions: List[Dict], year: str, session: str, area: str) -> List[Dict]:
        """
        学士試験の年度・回数・領域でフィルタリングする
        """
        return QuestionUtils.filter_gakushi_by_year_session_area(all_questions, year, session, area)

    @staticmethod
    def filter_by_subject(all_questions: List[Dict], subject: str, is_gakushi: bool = False) -> List[Dict]:
        """
        科目でフィルタリングする
        """
        if not subject:
            return []
            
        if is_gakushi:
            return [q for q in all_questions if str(q.get("number","")).startswith("G") and (q.get("subject") == subject)]
        else:
            return [q for q in all_questions if q.get("subject") == subject and not str(q.get("number","")).startswith("G")]

    @staticmethod
    def filter_by_keyword(all_questions: List[Dict], keyword: str, target_exam: str) -> List[Dict]:
        """
        キーワードで検索する
        """
        if not keyword or not keyword.strip():
            return []
            
        keyword = keyword.strip().lower()
        search_results = []
        
        for question in all_questions:
            q_number = question.get('number', '')
            
            # 対象試験のフィルタリング
            if target_exam == "学士" and not q_number.startswith('G'):
                continue
            if target_exam == "国試" and q_number.startswith('G'):
                continue
            
            # キーワード検索
            searchable_text = [
                question.get('question', ''),
                question.get('subject', ''),
                q_number,
                str(question.get('choices', [])),
                question.get('answer', ''),
                question.get('explanation', '')
            ]
            
            combined_text = ' '.join(searchable_text).lower()
            if keyword in combined_text:
                search_results.append(question)
                
        return search_results

    @staticmethod
    def filter_by_ids(all_questions: List[Dict], ids: Set[str]) -> List[Dict]:
        """
        問題IDのセットでフィルタリングする
        """
        return [q for q in all_questions if q.get("number") in ids]
