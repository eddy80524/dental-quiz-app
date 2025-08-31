"""
アプリ全体で使用されるユーティリティ関数を提供するモジュール

主な変更点:
- SM2アルゴリズム関連の関数を集約
- 共通のヘルパー関数を統合
- データ処理関連の最適化
- Google Analytics統合
"""

import streamlit as st
import datetime
import json
import os
import re
import time
import uuid
import subprocess
import tempfile
import base64
import hashlib
import requests
from typing import Dict, Any, List, Optional, Union
from collections import Counter, defaultdict
import pytz
import streamlit.components.v1 as components

# 日本時間のタイムゾーン設定
JST = pytz.timezone('Asia/Tokyo')


def get_natural_sort_key(q_dict):
    """
    問題辞書を受け取り、自然順ソート用のキー（タプル）を返す。
    例: "112A5" -> (112, 'A', 5)
    学士試験形式: "G24-1-1-A-1" や "G24-2再-A-1" -> ('G', 24, '1-1', 'A', 1)
    """
    try:
        q_num_str = q_dict.get('number', '0')
        # 学士試験形式: G24-1-1-A-1 や G24-2再-A-1 に対応
        # データ正規化済みでハイフンのみ使用
        m_gakushi = re.match(r'^(G)(\d+)-([\d\-再]+)-([A-Z])-(\d+)$', q_num_str)
        if m_gakushi:
            return (
                0,                       # 学士試験は先頭に0を置いて従来形式と区別
                m_gakushi.group(1),      # G
                int(m_gakushi.group(2)), # 年度
                m_gakushi.group(3),      # 1-1や2再
                m_gakushi.group(4),      # A
                int(m_gakushi.group(5))  # 問題番号
            )
        
        # 従来形式: 112A5 → (1, 112, 'A', 5)
        m = re.match(r'^(\d+)([A-Z])(\d+)$', q_num_str)
        if m:
            return (
                1,                    # 従来形式は1を置く
                int(m.group(1)),      # 回数
                m.group(2),           # 領域 (A, B, C, D)
                int(m.group(3))       # 問題番号
            )
        
        # その他の形式はそのまま文字列でソート
        return (2, q_num_str)
        
    except Exception as e:
        print(f"[DEBUG] ソートキー生成エラー: {q_num_str}, {e}")
        return (999, q_num_str)


# 科目マッピング機能をインポート
try:
    from subject_mapping import get_standardized_subject
except ImportError:
    # フォールバック：subject_mappingが利用できない場合
    def get_standardized_subject(subject):
        return subject or "未分類"

# Google Analytics設定
try:
    GA_MEASUREMENT_ID = st.secrets.get("google_analytics_id", "G-XXXXXXXXXX")
except:
    GA_MEASUREMENT_ID = "G-XXXXXXXXXX"  # フォールバック値


class AnalyticsUtils:
    """Google Analytics統合のためのユーティリティクラス"""
    
    @staticmethod
    def inject_ga_script():
        """Google Analytics スクリプトを注入"""
        ga_script = f"""
        <!-- Google tag (gtag.js) -->
        <script async src="https://www.googletagmanager.com/gtag/js?id={GA_MEASUREMENT_ID}"></script>
        <script>
          window.dataLayer = window.dataLayer || [];
          function gtag(){{dataLayer.push(arguments);}}
          gtag('js', new Date());
          gtag('config', '{GA_MEASUREMENT_ID}', {{
            cookie_domain: 'auto',
            cookie_flags: 'SameSite=None;Secure'
          }});
        </script>
        """
        components.html(ga_script, height=0)
    
    @staticmethod
    def track_event(event_name: str, parameters: Dict[str, Any] = None):
        """Google Analyticsイベントを追跡"""
        if parameters is None:
            parameters = {}
        
        # ユーザーIDを取得（セッション状態から）
        user_id = st.session_state.get('user_id', 'anonymous')
        parameters['user_id'] = user_id
        
        # タイムスタンプを追加
        parameters['timestamp'] = datetime.datetime.now(JST).isoformat()
        
        # JavaScriptでGoogle Analytics イベントを送信
        ga_js = f"""
        <script>
        if (typeof gtag !== 'undefined') {{
            gtag('event', '{event_name}', {json.dumps(parameters)});
        }}
        </script>
        """
        components.html(ga_js, height=0)
    
    @staticmethod
    def track_study_session_start(session_type: str, question_count: int = 0):
        """学習セッション開始を追跡"""
        AnalyticsUtils.track_event('study_session_start', {
            'session_type': session_type,
            'question_count': question_count,
            'page_title': 'Practice Session'
        })
    
    @staticmethod
    def track_question_answered(question_id: str, is_correct: bool, quality: int = None):
        """問題回答を追跡"""
        AnalyticsUtils.track_event('question_answered', {
            'question_id': question_id,
            'is_correct': is_correct,
            'quality': quality,
            'page_title': 'Practice Page'
        })
    
    @staticmethod
    def track_learning_completion(session_duration: float, questions_answered: int, accuracy: float):
        """学習完了を追跡"""
        AnalyticsUtils.track_event('learning_completion', {
            'session_duration_minutes': round(session_duration / 60, 2),
            'questions_answered': questions_answered,
            'accuracy_percentage': round(accuracy * 100, 1),
            'page_title': 'Practice Results'
        })
    
    @staticmethod
    def track_page_view(page_name: str):
        """ページビューを追跡"""
        AnalyticsUtils.track_event('page_view', {
            'page_name': page_name,
            'page_title': page_name
        })


class DataUtils:
    """データ処理関連のユーティリティクラス"""
    
    @staticmethod
    def safe_parse_timestamp(timestamp) -> Optional[datetime.datetime]:
        """安全にタイムスタンプを解析してdatetimeオブジェクトを返す"""
        try:
            if isinstance(timestamp, str):
                # ISO形式の文字列
                return datetime.datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            elif hasattr(timestamp, 'seconds'):
                # Firebase Timestampオブジェクト
                return datetime.datetime.fromtimestamp(timestamp.seconds)
            elif isinstance(timestamp, datetime.datetime):
                return timestamp
            elif isinstance(timestamp, datetime.date):
                return datetime.datetime.combine(timestamp, datetime.time())
            else:
                return None
        except (ValueError, TypeError, AttributeError):
            return None
    
    @staticmethod
    def safe_get_timestamp(item) -> float:
        """安全にタイムスタンプを取得する関数"""
        try:
            timestamp = item[1]['history'][-1]['timestamp']
            # Firebase Timestampオブジェクトの場合
            if hasattr(timestamp, 'seconds'):
                return timestamp.seconds
            # 文字列の場合
            elif isinstance(timestamp, str):
                return datetime.datetime.fromisoformat(timestamp.replace('Z', '+00:00')).timestamp()
            # 数値の場合
            elif isinstance(timestamp, (int, float)):
                return timestamp
            else:
                return 0
        except (KeyError, IndexError, ValueError, AttributeError):
            return 0


class QuestionUtils:
    """問題関連のユーティリティクラス"""
    
    @staticmethod
    def is_hisshu(q_num_str: str) -> bool:
        """問題番号文字列を受け取り、必修問題かどうかを判定する"""
        match = re.match(r'(\d+)([A-D])(\d+)', q_num_str)
        if not match:
            return False
        kai, ryoiki, num = int(match.group(1)), match.group(2), int(match.group(3))
        if 101 <= kai <= 102:
            return ryoiki in ['A', 'B'] and 1 <= num <= 25
        elif 103 <= kai <= 110:
            return ryoiki in ['A', 'C'] and 1 <= num <= 35
        elif 111 <= kai <= 118:
            return ryoiki in ['A', 'B', 'C', 'D'] and 1 <= num <= 20
        return False
    
    @staticmethod
    def is_gakushi_hisshu(q_num_str: str) -> bool:
        """学士試験の問題番号文字列を受け取り、必修問題かどうかを判定する"""
        # 学士試験の必修問題は1-20番（全領域A-D共通）
        match = re.match(r'^G\d{2}-[\d\-再]+-[A-D]-(\d+)$', q_num_str)
        if match:
            num = int(match.group(1))
            return 1 <= num <= 20
        return False

    @staticmethod
    def check_answer(user_choice: str, correct_answer: str) -> bool:
        """
        複数正解に対応した解答判定（複数選択問題対応）
        
        Args:
            user_choice: ユーザーの選択 (例: "A", "AD", "ABC", "AC")
            correct_answer: 正解 (例: "A", "A/D", "AD/AC/CD", "ABC/ABD/ACD/BCD", "AC")
        
        Returns:
            bool: 正解かどうか
        """
        if not user_choice or not correct_answer:
            return False
        
        user_choice = user_choice.strip()
        correct_answer = correct_answer.strip()
        
        # 複数正解の場合（/区切り）
        if '/' in correct_answer:
            valid_answers = [ans.strip() for ans in correct_answer.split('/')]
            return user_choice in valid_answers
        
        # 複数選択問題の場合（正答が「AC」「BD」など複数文字）
        # ユーザーの回答と正答を文字レベルで比較
        if len(correct_answer) > 1 and len(user_choice) > 1:
            # 文字を昇順にソートして比較（順序に依存しない）
            user_sorted = ''.join(sorted(user_choice.upper()))
            correct_sorted = ''.join(sorted(correct_answer.upper()))
            return user_sorted == correct_sorted
        
        # 単一正解の場合
        return user_choice.upper() == correct_answer.upper()
    
    @staticmethod
    def format_answer_display(correct_answer: str) -> str:
        """
        正解を表示用にフォーマット（複数選択問題対応）
        
        Args:
            correct_answer: 正解 (例: "A", "A/D", "AD/AC/CD", "ABC/ABD/ACD/BCD", "AC")
        
        Returns:
            str: 表示用文字列
        """
        if not correct_answer:
            return "不明"
        
        correct_answer = correct_answer.strip()
        
        # 複数正解の場合（/区切り）
        if '/' in correct_answer:
            answers = [ans.strip() for ans in correct_answer.split('/')]
            if len(answers) == 2:
                return f"{answers[0]} または {answers[1]}"
            else:
                return "、".join(answers[:-1]) + f" または {answers[-1]}"
        
        # 複数選択問題の場合（「AC」「BD」など）
        if len(correct_answer) > 1:
            # 選択肢を文字ごとに分けて表示
            choices = list(correct_answer.upper())
            if len(choices) == 2:
                return f"{choices[0]} と {choices[1]}"
            else:
                return "、".join(choices[:-1]) + f" と {choices[-1]}"
        
        return correct_answer.upper()
    
    @staticmethod
    def build_gakushi_indices(all_questions: List[Dict[str, Any]]):
        """学士試験の年度、回数、領域の情報を整理する"""
        years = set()
        sessions_by_year = defaultdict(set)
        areas_by_year_session = defaultdict(lambda: defaultdict(set))
        subjects = set()
        
        for q in all_questions:
            qn = q.get("number", "")
            if not qn.startswith("G"):
                continue
                
            # G23-2-A-1, G25-1-1-A-1, G22-1再-A-1 などの形式に対応
            m = re.match(r'^G(\d{2})-([^-]+(?:-[^-]+)*)-([A-D])-\d+$', qn)
            if m:
                y2 = int(m.group(1))
                year = 2000 + y2 if y2 <= 30 else 1900 + y2
                session = m.group(2)  # 1-1, 1-2, 1-3, 1再, 2, 2再 など
                area = m.group(3)
                
                years.add(year)
                sessions_by_year[year].add(session)
                areas_by_year_session[year][session].add(area)
                
            s = (q.get("subject") or "").strip()
            if qn.startswith("G") and s:
                subjects.add(s)
        
        years_sorted = sorted(years, reverse=True)
        
        # セッションをソート
        def sort_sessions(sessions):
            def session_key(s):
                if s == "1-1": return (1, 1, 0)
                elif s == "1-2": return (1, 2, 0)
                elif s == "1-3": return (1, 3, 0)
                elif s == "1再": return (1, 99, 0)
                elif s == "2": return (2, 0, 0)
                elif s == "2再": return (2, 99, 0)
                else: return (99, 0, 0)
            return sorted(sessions, key=session_key)
        
        sessions_map = {y: sort_sessions(list(sessions_by_year[y])) for y in years_sorted}
        areas_map = {}
        for year in years_sorted:
            areas_map[year] = {}
            for session in sessions_map[year]:
                areas_map[year][session] = sorted(list(areas_by_year_session[year][session]))
        
        gakushi_subjects = sorted(list(subjects))
        return years_sorted, sessions_map, areas_map, gakushi_subjects
    
    @staticmethod
    def filter_gakushi_by_year_session_area(all_questions: List[Dict[str, Any]], year: int, session: str, area: str):
        """学士試験の年度、回数、領域で問題をフィルタリング"""
        yy = str(year)[2:]  # 2024 -> "24"
        
        res = []
        for q in all_questions:
            qn = q.get("number", "")
            if not qn.startswith("G"):
                continue
                
            # 複数のパターンに対応
            patterns = [
                rf'^G{yy}-{re.escape(session)}-{area}-\d+$',
                rf'^G{yy}-{re.escape(session)}-{area}\d+$',
            ]
            
            for pattern in patterns:
                if re.match(pattern, qn):
                    res.append(q)
                    break
        
        return res
    
    @staticmethod
    def get_subject_of(q: Dict[str, Any]) -> str:
        """問題の科目を取得（標準化済み）"""
        original_subject = (q.get("subject") or "未分類").strip()
        return get_standardized_subject(original_subject)
    
    @staticmethod
    def make_subject_index(all_questions: List[Dict[str, Any]]):
        """科目インデックスを作成"""
        qid_to_subject, subj_to_qids = {}, {}
        for q in all_questions:
            qid = q.get("number")
            if not qid:
                continue
            s = QuestionUtils.get_subject_of(q)
            qid_to_subject[qid] = s
            subj_to_qids.setdefault(s, set()).add(qid)
        return qid_to_subject, subj_to_qids


class SM2Algorithm:
    """SM2学習アルゴリズム関連のクラス"""
    
    @staticmethod
    def calculate_card_level(n: int, last_quality: int, history: List[Dict[str, Any]]) -> int:
        """カードのレベルを計算"""
        if not history:
            return 0 if n == 0 else 1
        
        # 最近の学習成績を分析
        recent_qualities = [h.get("quality", 0) for h in history[-5:]]
        avg_quality = sum(recent_qualities) / len(recent_qualities) if recent_qualities else 0
        
        # レベル計算ロジック
        if n == 0:
            return 0
        elif n >= 5 and avg_quality >= 4.5:
            return 5  # 習得済み
        elif n >= 3 and avg_quality >= 4.0:
            return 4
        elif n >= 2 and avg_quality >= 3.5:
            return 3
        elif n >= 1 and avg_quality >= 3.0:
            return 2
        elif n >= 1:
            return 1
        else:
            return 0
    
    @staticmethod
    def sm2_update(card: Dict[str, Any], quality: int, now: Optional[datetime.datetime] = None) -> Dict[str, Any]:
        """標準のSM2アルゴリズム更新"""
        if now is None:
            now = datetime.datetime.now(datetime.timezone.utc)
        
        EF, n, I = card.get("EF", 2.5), card.get("n", 0), card.get("I", 0)
        
        if quality == 1:
            n = 0
            EF = max(EF - 0.3, 1.3)
            I = 10 / 1440
        elif quality == 2:
            EF = max(EF - 0.15, 1.3)
            I = max(card.get("I", 1) * 0.5, 10 / 1440)
        elif quality == 4 or quality == 5:
            if n == 0:
                I = 1
            elif n == 1:
                I = 4
            else:
                EF = max(EF + (0.1 - (5-quality)*(0.08 + (5-quality)*0.02)), 1.3)
                I = card.get("I", 1) * EF
            n += 1
            if quality == 5:
                I *= 1.3
        else:
            n = 0
            I = 10 / 1440
        
        next_review_dt = now + datetime.timedelta(days=I)
        card["history"] = card.get("history", []) + [{
            "timestamp": now.isoformat(),
            "quality": quality,
            "interval": I,
            "EF": EF
        }]
        
        # レベル計算
        level = SM2Algorithm.calculate_card_level(n, quality, card.get("history", []))
        
        card.update({
            "EF": EF,
            "n": n,
            "I": I,
            "next_review": next_review_dt.isoformat(),
            "quality": quality,
            "level": level
        })
        return card
    
    @staticmethod
    def sm2_update_with_policy(card: Dict[str, Any], quality: int, q_num_str: str, now: Optional[datetime.datetime] = None) -> Dict[str, Any]:
        """必修問題対応のSM2アルゴリズム更新"""
        if now is None:
            now = datetime.datetime.now(datetime.timezone.utc)
        
        # 国試の必修または学士試験の必修で「難しい」の場合は lapse 扱い
        if (QuestionUtils.is_hisshu(q_num_str) or QuestionUtils.is_gakushi_hisshu(q_num_str)) and quality == 2:
            EF = max(card.get("EF", 2.5) - 0.2, 1.3)
            n = 0
            I = 10 / 1440  # 10分
            next_review_dt = now + datetime.timedelta(minutes=10)
            hist = card.get("history", [])
            hist = hist + [{
                "timestamp": now.isoformat(),
                "quality": quality,
                "interval": I,
                "EF": EF
            }]
            card.update({
                "EF": EF,
                "n": n,
                "I": I,
                "next_review": next_review_dt.isoformat(),
                "quality": quality,
                "history": hist
            })
            return card
        else:
            return SM2Algorithm.sm2_update(card, quality, now=now)


class CardSelectionUtils:
    """カード選択関連のユーティリティクラス"""
    
    @staticmethod
    def recent_subject_penalty(q_subject: str, recent_qids: List[str], qid_to_subject: Dict[str, str]) -> float:
        """最近の科目ペナルティを計算"""
        if not recent_qids:
            return 0.0
        recent_subjects = [qid_to_subject.get(r) for r in recent_qids if r in qid_to_subject]
        return 0.15 if q_subject in recent_subjects else 0.0
    
    @staticmethod
    def pick_new_cards_for_today(all_questions: List[Dict[str, Any]], cards: Dict[str, Any], N: int = 10, recent_qids: Optional[List[str]] = None) -> List[str]:
        """今日の新規カードを選択（出題基準フィルター対応）"""
        recent_qids = recent_qids or []
        qid_to_subject, subj_to_qids = QuestionUtils.make_subject_index(all_questions)

        # 科目ごとの導入済み枚数
        introduced_counts = {subj: 0 for subj in subj_to_qids.keys()}
        for qid, card in cards.items():
            if qid in qid_to_subject:
                # n が 0 より大きいか、historyが存在する場合に導入済みとみなす
                if card.get("n", 0) > 0 or card.get("history"):
                    introduced_counts[qid_to_subject[qid]] += 1

        # 目標は当面「均等配分」
        target_ratio = {subj: 1/len(subj_to_qids) for subj in subj_to_qids.keys()} if subj_to_qids else {}

        # 全体正答率計算
        global_correct = global_total = 0
        for card in cards.values():
            for h in card.get("history", []):
                if isinstance(h, dict) and "quality" in h:
                    global_total += 1
                    if h["quality"] >= 4:
                        global_correct += 1

        global_correct_rate = global_correct / global_total if global_total > 0 else 0.5

        # 候補を収集してスコア計算
        candidates = []
        for q in all_questions:
            qid = q.get("number")
            if not qid:
                continue
            
            # 未学習の条件を修正：cardsに存在しない OR (historyが空 AND n=0)
            if qid in cards:
                card = cards[qid]
                # historyがあるか、nが0より大きい場合は学習済み
                if card.get("history", []) or card.get("n", 0) > 0:
                    continue
            
            q_subject = QuestionUtils.get_subject_of(q)
            
            # 科目バランススコア
            total_in_subject = len(subj_to_qids.get(q_subject, set()))
            introduced_in_subject = introduced_counts.get(q_subject, 0)
            current_ratio = introduced_in_subject / total_in_subject if total_in_subject > 0 else 0
            target = target_ratio.get(q_subject, 0)
            balance_score = max(0, target - current_ratio)
            
            # 最近の科目ペナルティ
            recent_penalty = CardSelectionUtils.recent_subject_penalty(q_subject, recent_qids, qid_to_subject)
            
            # ランダム要素を強化（よりランダムな選択を実現）
            import random
            random_factor = random.uniform(0, 0.5)  # 0-0.5のランダム値（従来の5倍）
            
            # 総合スコア
            total_score = balance_score - recent_penalty + random_factor
            candidates.append((qid, total_score, q_subject))

        # 候補を完全にシャッフルしてからスコア順ソート（ランダム性を強化）
        random.shuffle(candidates)  # 最初にシャッフル
        candidates.sort(key=lambda x: x[1], reverse=True)
        
        # さらに上位候補の中からランダム選択（多様性を確保）
        top_candidates = candidates[:min(N * 5, len(candidates))]  # 目標数の5倍を候補とする（従来の3倍から5倍に増加）
        random.shuffle(top_candidates)  # 上位候補を再度シャッフル
        selected = [c[0] for c in top_candidates[:N]]
        
        # 最終的に選択されたカードもシャッフル（出題順序もランダムに）
        random.shuffle(selected)
        
        # デバッグ情報を出力
        print(f"[DEBUG] 新規カード選択: 候補数={len(candidates)}, 選択数={len(selected)}")
        if selected:
            selected_subjects = [c[2] for c in top_candidates[:N]]
            print(f"[DEBUG] 選択された新規カード: {selected}")
            print(f"[DEBUG] 選択された科目: {selected_subjects}")
        
        return selected


@st.cache_data(ttl=3600)  # 1時間キャッシュ
def load_master_data(version: str = "v2025-08-22-all-gakushi-files") -> tuple:
    """マスターデータを読み込む（キャッシュ付き）"""
    start = time.time()
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    master_dir = os.path.join(script_dir, 'data')
    
    # 読み込むファイルを直接指定
    files_to_load = [
        'master_questions_final.json', 
        'gakushi-2022-1-1.json', 
        'gakushi-2022-1-2.json', 
        'gakushi-2022-1-3.json', 
        'gakushi-2022-1再.json',  
        'gakushi-2022-2.json', 
        'gakushi-2023-1-1.json',
        'gakushi-2023-1-2.json',
        'gakushi-2023-1-3.json',
        'gakushi-2023-1再.json', 
        'gakushi-2023-2.json',
        'gakushi-2023-2再.json',
        'gakushi-2024-1-1.json', 
        'gakushi-2024-2.json', 
        'gakushi-2025-1-1.json'
    ]
    target_files = [os.path.join(master_dir, f) for f in files_to_load]

    all_cases = {}
    all_questions = []
    seen_numbers = set()
    
    for file_path in target_files:
        if not os.path.exists(file_path):
            continue
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if isinstance(data, dict):
                cases = data.get('cases', {})
                if isinstance(cases, dict):
                    all_cases.update(cases)
                
                questions = data.get('questions', [])
                if isinstance(questions, list):
                    for q in questions:
                        num = q.get('number')
                        if num and num not in seen_numbers:
                            all_questions.append(q)
                            seen_numbers.add(num)
            
            elif isinstance(data, list):
                for q in data:
                    num = q.get('number')
                    if num and num not in seen_numbers:
                        all_questions.append(q)
                        seen_numbers.add(num)

        except Exception as e:
            print(f"{file_path} の読み込みでエラー: {e}")
    
    total_time = time.time() - start
    gakushi_count = sum(1 for q in all_questions if q.get('number', '').startswith('G'))
    kokushi_count = len(all_questions) - gakushi_count
    
    print(f"[DEBUG] 問題データ取得完了 - 総時間: {total_time:.3f}s")
    print(f"[DEBUG] 国試問題: {kokushi_count}問, 学士試験問題: {gakushi_count}問, 合計: {len(all_questions)}問")
    
    return all_cases, all_questions


@st.cache_data(ttl=3600)
def get_derived_data(all_questions: List[Dict[str, Any]]):
    """派生データを別途キャッシュして計算コストを分散"""
    start = time.time()
    
    questions_dict = {q['number']: q for q in all_questions}
    subjects = sorted(list(set(q['subject'] for q in all_questions if q.get('subject') and q.get('subject') != '（未分類）')))
    exam_numbers = sorted(list(set(re.match(r'(\d+)', q['number']).group(1) for q in all_questions if re.match(r'(\d+)', q['number']))), key=int, reverse=True)
    exam_sessions = sorted(list(set(re.match(r'(\d+[A-D])', q['number']).group(1) for q in all_questions if re.match(r'(\d+[A-D])', q['number']))))
    hisshu_numbers = {q['number'] for q in all_questions if QuestionUtils.is_hisshu(q['number'])}
    gakushi_hisshu_numbers = {q['number'] for q in all_questions if QuestionUtils.is_gakushi_hisshu(q['number'])}
    
    derived_time = time.time() - start
    print(f"[DEBUG] get_derived_data - 派生データ計算: {derived_time:.3f}s")
    
    return questions_dict, subjects, exam_numbers, exam_sessions, hisshu_numbers, gakushi_hisshu_numbers


def log_to_ga(event_name: str, user_id: str, params: Dict[str, Any]):
    """Google Analytics GA4にイベントを送信"""
    try:
        # Firebase Analytics（Firestore経由）でのイベント記録は無効化されています
        # Firebase Analyticsモジュールが利用できないため、ログ出力のみ行います
        print(f"[DEBUG] Analytics event: {event_name} for user {user_id} with params: {params}")
        
        # 必要に応じて将来のAnalytics統合のためのプレースホルダー
        pass
            
    except Exception as e:
        print(f"[DEBUG] GA logging error (non-critical): {e}")


def _track_daily_active_user(uid: str):
    """日次アクティブユーザー追跡"""
    try:
        from firestore_db import get_firestore_manager
        import datetime
        
        today = datetime.date.today().isoformat()
        db_manager = get_firestore_manager()
        
        # daily_active_usersコレクションに記録
        daily_user_ref = db_manager.db.collection("daily_active_users").document(f"{today}_{uid}")
        daily_user_ref.set({
            "uid": uid,
            "date": today,
            "last_activity": datetime.datetime.now(datetime.timezone.utc),
            "active": True
        }, merge=True)
        
        # 月次サマリーも更新
        month = datetime.date.today().strftime("%Y-%m")
        monthly_ref = db_manager.db.collection("monthly_analytics_summary").document(f"{uid}_{month}")
        
        from google.cloud.firestore import Increment
        monthly_ref.set({
            "uid": uid,
            "month": month,
            "days_active": Increment(1),
            "last_activity": datetime.datetime.now(datetime.timezone.utc)
        }, merge=True)
        
    except Exception as e:
        print(f"[DEBUG] Daily active user tracking error: {e}")


def get_question_by_id(question_id: str) -> Optional[Dict[str, Any]]:
    """問題IDから問題データを取得"""
    return ALL_QUESTIONS_DICT.get(question_id)


def get_theme_css() -> str:
    """テーマ用CSS（ダミー実装）"""
    return ""


# 初期データ読み込み（モジュール読み込み時に実行）
CASES, ALL_QUESTIONS = load_master_data()
ALL_QUESTIONS_DICT, ALL_SUBJECTS, ALL_EXAM_NUMBERS, ALL_EXAM_SESSIONS, HISSHU_Q_NUMBERS_SET, GAKUSHI_HISSHU_Q_NUMBERS_SET = get_derived_data(ALL_QUESTIONS)


# ===== PDF生成関連の関数群 =====

def extract_year_from_question_number(q_number: str) -> Optional[int]:
    """
    問題番号から年度を抽出するヘルパー関数
    国試問題（118A1）と学士試験問題（G24-1-1-A-1）の両方に対応
    """
    if not q_number:
        return None
    
    # 学士試験問題（G始まり）の場合
    if q_number.startswith('G'):
        # パターン1: G22-1-1-A-1, G23-2-A-67 など
        match = re.match(r'G(\d+)', q_number)
        if match:
            year = int(match.group(1))
            # 2桁年度を4桁に変換（20xx年として解釈）
            return 2000 + year if year < 100 else year
    else:
        # 国試問題の場合：118A1, 95C40 など
        match = re.match(r'(\d+)', q_number)
        if match:
            year = int(match.group(1))
            # 3桁年度（108回以降）と2桁年度（107回以前）を適切に変換
            if year >= 100:
                return year  # 108, 118 など
            else:
                return year + 100 if year < 50 else year + 100  # 95 -> 195（第95回）
    
    return None


def _latex_escape(text: str) -> str:
    """LaTeX特殊文字をエスケープ"""
    if not text:
        return ""
    
    # LaTeX特殊文字のエスケープマップ
    escape_map = {
        '\\': r'\textbackslash{}',
        '{': r'\{',
        '}': r'\}',
        '$': r'\$',
        '&': r'\&',
        '%': r'\%',
        '#': r'\#',
        '^': r'\textasciicircum{}',
        '_': r'\_',
        '~': r'\textasciitilde{}',
    }
    
    for char, escaped in escape_map.items():
        text = text.replace(char, escaped)
    
    return text


def _answer_mark_for_overlay(answer_str: str) -> str:
    """'A', 'C', 'A/C' を右下用 'a', 'c', 'ac' へ正規化"""
    if not answer_str:
        return ""
    raw = answer_str.replace("／", "/")
    # スラッシュで分割するか、単純に文字のリストにする
    letters = (raw.split("/") if "/" in raw else list(raw.strip()))
    def _to_alph(ch):
        # アルファベットのみ小文字に変換
        return chr(ord('a') + (ord(ch.upper()) - ord('A'))) if ch.isalpha() else ch
    # スラッシュなしで文字を連結
    return "".join(_to_alph(ch) for ch in letters if ch)


def _image_block_latex(file_list: List[str]) -> str:
    """1枚 -> 0.45幅、2枚 -> 0.45×2、3枚以上 -> 2列折返し"""
    if not file_list:
        return ""
    if len(file_list) == 1:
        return rf"\begin{{center}}\includegraphics[width=0.45\textwidth]{{{file_list[0]}}}\end{{center}}"
    if len(file_list) == 2:
        a, b = file_list[0], file_list[1]
        return (
            r"\begin{center}"
            rf"\includegraphics[width=0.45\textwidth]{{{a}}}"
            rf"\includegraphics[width=0.45\textwidth]{{{b}}}"
            r"\end{center}"
        )
    # 3枚以上の場合
    out = [r"\begin{center}"]
    for i, fn in enumerate(file_list):
        out.append(rf"\includegraphics[width=0.45\textwidth]{{{fn}}}")
        # 2枚ごと（奇数インデックス）に改行コマンドを追加（最後の画像の後には不要）
        if i % 2 == 1 and i != len(file_list) - 1:
            out.append(r"\\[0.5ex]")
    out.append(r"\end{center}")
    return "\n".join(out)


def get_secure_image_url(path: str) -> Optional[str]:
    """
    Firebase Storageのパスから15分有効な署名付きURLを生成。
    http(s)で始まるURLはそのまま返します。
    """
    if not path or not isinstance(path, str):
        return None

    if path.startswith('http://') or path.startswith('https://'):
        return path
    
    try:
        # firebase_adminをインポート（この関数はFirebase Admin SDKが初期化されていることを前提とします）
        from firebase_admin import storage
        import datetime
        
        bucket = storage.bucket()
        blob = bucket.blob(path)

        # 存在確認をせずに、まずURL生成を試みる（高速化のため）
        return blob.generate_signed_url(
            expiration=datetime.timedelta(minutes=15),
            method="GET",
            version="v4"
        )
    except Exception as e:
        print(f"[ERROR] 署名付きURLの生成に失敗しました: Path='{path}', Error='{e}'")
        # ここで代替パスを試すなどのフォールバック処理も追加可能です
        return None


def get_http_session():
    """HTTPセッションを取得（再利用可能）"""
    if not hasattr(get_http_session, '_session'):
        get_http_session._session = requests.Session()
        get_http_session._session.headers.update({
            'User-Agent': 'DentalQuizApp/1.0'
        })
    return get_http_session._session


def ensure_firebase_initialized():
    """Firebase Admin SDKが初期化されていることを確認し、必要に応じて初期化する"""
    try:
        import firebase_admin
        from firebase_admin import credentials
        
        # 既に初期化されている場合は何もしない
        if firebase_admin._apps:
            return True
            
        # 初期化されていない場合は初期化を試みる
        try:
            # Streamlit secretsから認証情報を取得
            firebase_config = st.secrets.get("firebase_service_account", {})
            if firebase_config:
                cred = credentials.Certificate(firebase_config)
                firebase_admin.initialize_app(cred, {
                    'storageBucket': st.secrets.get("firebase_storage_bucket", "")
                })
                print("✅ Firebase Admin SDK初期化完了")
                return True
        except Exception as init_error:
            print(f"❌ Firebase初期化エラー: {init_error}")
            return False
    except ImportError:
        print("❌ Firebase Admin SDKがインストールされていません")
        return False
    except Exception as e:
        print(f"❌ Firebase初期化チェックエラー: {e}")
        return False


def get_secure_image_url(path: str) -> Optional[str]:
    """
    Firebase Storageのパスから15分有効な署名付きURLを生成。
    http(s)で始まるURLはそのまま返します。
    """
    if not path or not isinstance(path, str):
        return None

    if path.startswith('http://') or path.startswith('https://'):
        return path
    
    # Firebase初期化を確認
    if not ensure_firebase_initialized():
        print(f"[ERROR] Firebase初期化に失敗しました。パス: {path}")
        return None
    
    try:
        # firebase_adminをインポート（この関数はFirebase Admin SDKが初期化されていることを前提とします）
        from firebase_admin import storage
        import datetime
        
        bucket = storage.bucket()
        blob = bucket.blob(path)

        # 存在確認をせずに、まずURL生成を試みる（高速化のため）
        return blob.generate_signed_url(
            expiration=datetime.timedelta(minutes=15),
            method="GET",
            version="v4"
        )
    except Exception as e:
        print(f"[ERROR] 署名付きURLの生成に失敗しました: Path='{path}', Error='{e}'")
        # ここで代替パスを試すなどのフォールバック処理も追加可能です
    """Firebase Admin SDKが初期化されていることを確認し、必要に応じて初期化する"""
    try:
        import firebase_admin
        from firebase_admin import credentials
        
        # 既に初期化されている場合は何もしない
        if firebase_admin._apps:
            return True
            
        # 初期化されていない場合は初期化を試みる
        try:
            # Streamlit secretsから認証情報を取得
            firebase_config = st.secrets.get("firebase_service_account", {})
            if firebase_config:
                cred = credentials.Certificate(firebase_config)
                firebase_admin.initialize_app(cred, {
                    'storageBucket': st.secrets.get("firebase_storage_bucket", "")
                })
                print("✅ Firebase Admin SDK初期化完了")
                return True
        except Exception as init_error:
            print(f"❌ Firebase初期化エラー: {init_error}")
            return False
    except ImportError:
        print("❌ Firebase Admin SDKがインストールされていません")
        return False
    except Exception as e:
        print(f"❌ Firebase初期化チェックエラー: {e}")
        return False


def get_secure_image_url(path: str) -> Optional[str]:
    """
    Firebase Storageのパスから15分有効な署名付きURLを生成。
    http(s)で始まるURLはそのまま返します。
    """
    if not path or not isinstance(path, str):
        return None

    if path.startswith('http://') or path.startswith('https://'):
        return path
    
    # Firebase初期化を確認
    if not ensure_firebase_initialized():
        print(f"[ERROR] Firebase初期化に失敗しました。パス: {path}")
        return None
    
    try:
        # firebase_adminをインポート（この関数はFirebase Admin SDKが初期化されていることを前提とします）
        from firebase_admin import storage
        import datetime
        
        bucket = storage.bucket()
        blob = bucket.blob(path)

        # 存在確認をせずに、まずURL生成を試みる（高速化のため）
        return blob.generate_signed_url(
            expiration=datetime.timedelta(minutes=15),
            method="GET",
            version="v4"
        )
    except Exception as e:
        print(f"[ERROR] 署名付きURLの生成に失敗しました: Path='{path}', Error='{e}'")
        # ここで代替パスを試すなどのフォールバック処理も追加可能です
    """HTTPセッションを取得（再利用可能）"""
    if not hasattr(get_http_session, '_session'):
        get_http_session._session = requests.Session()
        get_http_session._session.headers.update({
            'User-Agent': 'DentalQuizApp/1.0'
        })
    return get_http_session._session


def create_simple_fallback_template(questions: List[Dict]) -> str:
    """シンプルなフォールバックテンプレート"""
    content = []
    content.append(r'\documentclass[a4paper]{jsarticle}')
    content.append(r'\usepackage[utf8]{inputenc}')
    content.append(r'\usepackage{graphicx}')
    content.append(r'\begin{document}')
    content.append(r'\title{検索結果}')
    content.append(r'\maketitle')
    content.append(f'{len(questions)}問の問題が含まれています。')
    content.append(r'\end{document}')
    
    return '\n'.join(content)


def rewrite_to_xelatex_template(latex_source: str) -> str:
    """XeLaTeX用にテンプレートを書き換え"""
    # documentclassをXeLaTeX対応に変更
    latex_source = latex_source.replace(
        r'\documentclass[dvipdfmx,a4paper,uplatex]{jsarticle}', 
        r'\documentclass[a4paper]{article}'
    )
    
    # 日本語フォント設定を追加
    xelatex_packages = r'''
\usepackage{fontspec}
\usepackage{xeCJK}
\setCJKmainfont{Hiragino Kaku Gothic ProN}
\setmainfont{Times New Roman}
'''
    
    # パッケージの後に挿入
    latex_source = latex_source.replace(
        r'\usepackage{amsmath}', 
        r'\usepackage{amsmath}' + xelatex_packages
    )
    
    return latex_source


def _gather_images_for_questions(questions: List[Dict]) -> tuple:
    """
    各問題の image_urls / image_paths を署名URL化してダウンロード。
    戻り値: ( {ファイル名:バイト列}, [[問題ごとのローカル名...], ...] )
    """
    import pathlib
    assets = {}
    per_q_files = []
    session = get_http_session()

    for qi, q in enumerate(questions, start=1):
        files = []
        candidates = []
        # 'image_urls'と'image_paths'の両方のキーから画像パスを収集
        for k in ("image_urls", "image_paths"):
            v = q.get(k)
            if v and isinstance(v, list):
                candidates.extend(v)

        # URL解決（http/httpsはそのまま、Storageパスは署名付きURLへ）
        resolved_urls = []
        for path in candidates:
            if isinstance(path, str):
                url = get_secure_image_url(path)
                if url:
                    resolved_urls.append(url)

        # ダウンロード処理
        for j, url in enumerate(resolved_urls, start=1):
            try:
                r = session.get(url, timeout=10)
                if r.status_code != 200:
                    continue
                
                # URLやContent-Typeから拡張子を推定
                ext = ".jpg"
                p = pathlib.Path(url.split("?")[0])
                if p.suffix.lower() in [".jpg", ".jpeg", ".png", ".pdf"]:
                    ext = p.suffix.lower()
                else:
                    ct = (r.headers.get("Content-Type") or "").lower()
                    if "png" in ct: ext = ".png"
                    elif "jpeg" in ct or "jpg" in ct: ext = ".jpg"
                
                name = f"q{qi:03d}_img{j:02d}{ext}"
                assets[name] = r.content
                files.append(name)
            except Exception as e:
                print(f"画像ダウンロードエラー: {url}, Error: {e}")
                continue
        
        per_q_files.append(files)
        
    return assets, per_q_files


def export_questions_to_latex_tcb_jsarticle(questions, right_label_fn=None):
    """
    tcolorbox(JS)版のLaTeX生成。高品質レイアウトで問題を出力。
    right_label_fn: lambda q -> 右上に出す文字列（例: 科目/年度など）。未指定なら '◯◯◯◯◯'
    title={...} には q['display_title']→q['number'] の優先で入れます。
    """
    header = r"""\documentclass[dvipdfmx,a4paper,uplatex]{jsarticle}
\usepackage[utf8]{inputenc}
\usepackage[dvipdfmx]{hyperref}
\hypersetup{colorlinks=true,citecolor=blue,linkcolor=blue}
\usepackage{xcolor}
\definecolor{lightgray}{HTML}{F9F9F9}
\renewcommand{\labelitemi}{・}
\def\labelitemi{・}
\usepackage{tikz}
\usetikzlibrary{calc}
\IfFileExists{bxtexlogo.sty}{\usepackage{bxtexlogo}}{}
\IfFileExists{ascmac.sty}{\usepackage{ascmac}}{}
\IfFileExists{mhchem.sty}{\usepackage[version=3]{mhchem}}{}
\usepackage{tcolorbox}
\tcbuselibrary{breakable, skins, theorems}
\usepackage[top=30truemm,bottom=30truemm,left=25truemm,right=25truemm]{geometry}
\newcommand{\ctext}[1]{\raise0.2ex\hbox{\textcircled{\scriptsize{#1}}}}
\renewcommand{\labelenumii}{\theenumii}
\renewcommand{\theenumii}{\alph{enumi}}
\IfFileExists{chemfig.sty}{\usepackage{chemfig}}{}
\IfFileExists{adjustbox.sty}{\usepackage{adjustbox}}{}
\usepackage{amsmath,amssymb}
\usepackage{tabularx}
\usepackage{enumitem}
\usepackage{graphicx} % 画像
\begin{document}
"""
    body = []
    for i, q in enumerate(questions, start=1):
        title_text = _latex_escape(q.get("display_title") or q.get("number") or f"問{i}")
        question_text = _latex_escape(q.get("question", "") or "")
        right_label = _latex_escape((right_label_fn(q) if right_label_fn else "◯◯◯◯◯") or "")
        ans_mark = _answer_mark_for_overlay((q.get("answer") or "").strip())

        # Python側でtcolorboxのオプション文字列を動的に生成
        box_open = (
            rf"\begin{{tcolorbox}}"
            r"[enhanced, colframe=black, colback=white,"
            rf" title={{{title_text}}}, fonttitle=\bfseries, breakable=true,"
            r" coltitle=black,"
            r" attach boxed title to top left={xshift=5mm, yshift=-3mm},"
            r" boxed title style={colframe=black, colback=white, },"
            r" top=4mm,"
            r" overlay={"
            + (rf"\node[anchor=north east, xshift=-5mm, yshift=3mm, font=\bfseries\Large, fill=white, inner sep=2pt] at (frame.north east) {{{right_label}}};" if right_label else "")
            + (rf"\node[anchor=south east, xshift=-3mm, yshift=3mm] at (frame.south east) {{{ans_mark}}};" if ans_mark else "")
            + r"}]"
        )
        
        body.append(box_open)
        body.append(question_text)

        # 画像スロット（後で置換）
        body.append(rf"%__IMAGES_SLOT__{i}__")

        # 選択肢
        choices = q.get("choices") or []
        if choices:
            body.append(r"\begin{enumerate}[nosep, left=0pt,label=\alph*.]")
            for ch in choices:
                text = ch.get("text", str(ch)) if isinstance(ch, dict) else str(ch)
                body.append(r"\item " + _latex_escape(text))
            body.append(r"\end{enumerate}")

        body.append(r"\end{tcolorbox}")
        body.append(r"\vspace{0.8em}")

        # 各問題ごとに改ページ（最後だけ入れない）
        if i < len(questions):
            body.append(r"\clearpage")

    footer = r"\end{document}"
    return header + "\n".join(body) + "\n" + footer


def compile_latex_to_pdf(latex_source: str, assets: Dict[str, bytes] = None) -> tuple:
    """
    LaTeX → PDF変換機能（高品質版）
    subprocessとtempfileを使用した本格的なPDF生成
    """
    if assets is None:
        assets = {}
    
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            # LaTeXファイルを書き込み
            tex_file = os.path.join(temp_dir, "document.tex")
            with open(tex_file, 'w', encoding='utf-8') as f:
                f.write(latex_source)
            
            # 画像アセットをコピー
            for filename, content in assets.items():
                asset_path = os.path.join(temp_dir, filename)
                with open(asset_path, 'wb') as f:
                    f.write(content)
            
            try:
                # uplatex → dvipdfmx の順序で実行（日本語対応）
                # LaTeX → DVI
                uplatex_result = subprocess.run(
                    ['uplatex', '-interaction=nonstopmode', 'document.tex'],
                    cwd=temp_dir,
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                
                if uplatex_result.returncode != 0:
                    error_log = f"uplatex error:\nSTDOUT:\n{uplatex_result.stdout}\nSTDERR:\n{uplatex_result.stderr}"
                    
                    # フォールバック: XeLaTeXを試す
                    try:
                        xelatex_source = rewrite_to_xelatex_template(latex_source)
                        with open(tex_file, 'w', encoding='utf-8') as f:
                            f.write(xelatex_source)
                        
                        xelatex_result = subprocess.run(
                            ['xelatex', '-interaction=nonstopmode', 'document.tex'],
                            cwd=temp_dir,
                            capture_output=True,
                            text=True,
                            timeout=60
                        )
                        
                        if xelatex_result.returncode == 0:
                            pdf_file = os.path.join(temp_dir, "document.pdf")
                            if os.path.exists(pdf_file):
                                with open(pdf_file, 'rb') as f:
                                    pdf_bytes = f.read()
                                return pdf_bytes, "PDF生成成功（XeLaTeX使用）"
                        
                        error_log += f"\n\nxelatex fallback error:\nSTDOUT:\n{xelatex_result.stdout}\nSTDERR:\n{xelatex_result.stderr}"
                        
                    except FileNotFoundError:
                        error_log += "\n\nXeLaTeXが利用できません"
                    
                    return None, error_log
                
                # DVI → PDF
                dvipdfmx_result = subprocess.run(
                    ['dvipdfmx', 'document.dvi'],
                    cwd=temp_dir,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if dvipdfmx_result.returncode != 0:
                    error_log = f"dvipdfmx error:\nSTDOUT:\n{dvipdfmx_result.stdout}\nSTDERR:\n{dvipdfmx_result.stderr}"
                    return None, error_log
                
                # PDFファイルを読み込み
                pdf_file = os.path.join(temp_dir, "document.pdf")
                if os.path.exists(pdf_file):
                    with open(pdf_file, 'rb') as f:
                        pdf_bytes = f.read()
                    return pdf_bytes, "PDF生成成功"
                else:
                    return None, "PDF file not found after compilation"
                    
            except subprocess.TimeoutExpired:
                return None, "LaTeX compilation timeout (60秒)"
            except FileNotFoundError as e:
                # LaTeX環境が利用できない場合のフォールバック
                if 'uplatex' in str(e):
                    # 簡易PDFダミーデータを生成
                    dummy_content = f"PDF生成環境が利用できません。問題数: {len(latex_source.split('questionbox')) - 1}"
                    return dummy_content.encode('utf-8'), "LaTeX環境未インストール（簡易出力）"
                else:
                    return None, f"Required command not found: {e}"
            
    except Exception as e:
        return None, f"PDF生成エラー: {e}"
