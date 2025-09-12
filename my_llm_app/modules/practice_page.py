"""
練習ページの描画とロジックを管理するモジュール

主な変更点:
- 練習ページ関連のロジックを独立したモジュールに移行
- uid統一によるデータアクセスの最適化
- セッション管理の改善
- コンポーネント化された問題演習UI実装
- Firebase Analytics統合
"""

import streamlit as st
import datetime
import time
import random
import pytz
import sys
import os
from typing import Dict, Any, List, Optional, Tuple

# 日本時間用のタイムゾーン
JST = pytz.timezone('Asia/Tokyo')

def get_japan_now() -> datetime.datetime:
    """日本時間の現在時刻を取得"""
    return datetime.datetime.now(JST)

def get_japan_today() -> datetime.date:
    """
    日本時間の今日の日付を取得
    
    新規学習目標のリセットタイミング：
    - 日本時間の0時にカウントがリセットされる
    - ユーザーが日本にいることを想定したタイムゾーン設定
    """
    return get_japan_now().date()

def get_japan_datetime_from_timestamp(timestamp) -> datetime.datetime:
    """タイムスタンプから日本時間のdatetimeオブジェクトを取得"""
    if hasattr(timestamp, 'replace'):
        # DatetimeWithNanoseconds または datetime オブジェクト
        if hasattr(timestamp, 'tzinfo') and timestamp.tzinfo is None:
            # ナイーブなdatetimeの場合、UTCとして扱って日本時間に変換
            return pytz.UTC.localize(timestamp).astimezone(JST)
        else:
            return timestamp.astimezone(JST)
    elif isinstance(timestamp, str):
        try:
            # ISO文字列をパース
            dt = datetime.datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            return dt.astimezone(JST)
        except Exception:
            # パースに失敗した場合は現在時刻を返す
            return get_japan_now()
    else:
        # その他の場合は現在時刻を返す
        return get_japan_now()


# 必要な関数とクラスのインポート
from llm import generate_dental_explanation
try:
    from llm_fixed import handle_llm_explanation_request, save_llm_feedback
except ImportError:
    # フォールバック: llm_fixedが利用できない場合
    def handle_llm_explanation_request(*args, **kwargs):
        return "LLM機能は現在利用できません。"
    def save_llm_feedback(*args, **kwargs):
        pass
try:
    from firestore_db import get_firestore_manager, save_user_data, check_gakushi_permission
except ImportError:
    # フォールバック: Firestoreが利用できない場合
    def get_firestore_manager():
        return None
    def save_user_data(*args, **kwargs):
        pass
    def check_gakushi_permission(*args, **kwargs):
        return False
try:
    from auth import AuthManager, get_user_permission
except ImportError:
    # フォールバック: 認証が利用できない場合
    class AuthManager:
        @staticmethod
        def login(*args, **kwargs):
            return False
        @staticmethod
        def logout(*args, **kwargs):
            pass
    def get_user_permission(*args, **kwargs):
        return False
from utils import (
    log_to_ga, QuestionUtils, ALL_QUESTIONS, ALL_QUESTIONS_DICT, 
    CardSelectionUtils, SM2Algorithm, AnalyticsUtils,
    ALL_EXAM_NUMBERS, ALL_EXAM_SESSIONS, ALL_SUBJECTS, CASES,
    HISSHU_Q_NUMBERS_SET, GAKUSHI_HISSHU_Q_NUMBERS_SET,
    get_natural_sort_key
)
from subject_mapping import get_standardized_subject

# UserDataExtractor インポート
from user_data_extractor import UserDataExtractor


# 高画質画像表示用のCSS
def inject_image_quality_css():
    """画像表示品質向上のためのCSSを追加"""
    st.markdown("""
    <style>
    /* 画像のレスポンシブ表示設定 */
    .stImage > img {
        image-rendering: -webkit-optimize-contrast;
        image-rendering: crisp-edges;
        max-width: 100% !important;
        width: auto !important;
        height: auto;
        border-radius: 8px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        transition: transform 0.2s ease;
        object-fit: contain;
    }
    
    /* 画像のホバー効果 */
    .stImage > img:hover {
        transform: scale(1.02);
        box-shadow: 0 4px 16px rgba(0,0,0,0.15);
    }
    
    /* エクスパンダー内の画像調整 */
    .streamlit-expanderContent .stImage {
        margin: 10px 0;
        width: 100%;
    }
    
    /* 画像コンテナのレスポンシブ対応 */
    .stImage {
        width: 100%;
        max-width: 100%;
        overflow: hidden;
    }
    
    /* 画像キャプションのスタイル改善 */
    .stImage > div {
        text-align: center;
        font-size: 14px;
        color: #666;
        margin-top: 8px;
    }
    </style>
    """, unsafe_allow_html=True)


def _calculate_legacy_stats_full(cards: Dict, today: str, new_cards_per_day: int) -> Tuple[int, int, int]:
    """従来のロジックを使用してカード統計を計算（完全版・Streamlit Cloud対応強化）"""
    
    # 復習カード数（期限切れ）
    review_count = 0
    # 新規カード数（今日学習予定）
    new_count = 0
    # 完了数（今日学習済み）
    completed_count = 0
    
    # 今日学習したカードの詳細を追跡
    today_studied_cards = []
    
    # カードが存在しない場合は即座に0を返す
    if not cards or len(cards) == 0:
        return 0, 0, 0
    
    for q_id, card in cards.items():
        try:
            # 今日の学習記録チェック
            history = card.get("history", [])
            
            # 今日学習したかどうかをチェック
            today_studied = False
            for h in history:
                if not isinstance(h, dict):
                    continue
                    
                timestamp = h.get("timestamp", "")
                if timestamp:
                    try:
                        # FirebaseのDatetimeWithNanosecondsオブジェクトの場合
                        if hasattr(timestamp, 'strftime'):
                            timestamp_str = timestamp.strftime("%Y-%m-%d")
                        # ISO文字列の場合
                        elif isinstance(timestamp, str):
                            timestamp_str = timestamp[:10] if len(timestamp) >= 10 else timestamp
                        else:
                            timestamp_str = str(timestamp)[:10]
                        
                        if timestamp_str == today:
                            today_studied = True
                            today_studied_cards.append(q_id)
                            break
                    except Exception as e:
                        continue
            
            if today_studied:
                completed_count += 1
            elif len(history) == 0:  # 未学習カード
                new_count += 1
            else:
                # 学習履歴があるカード：復習期限をチェック
                # sm2データの複数のパターンに対応
                sm2_data = card.get("sm2_data", {}) or card.get("sm2", {})
                due_date = sm2_data.get("due_date") or sm2_data.get("next_review")
                
                if due_date:
                    try:
                        # FirebaseのDatetimeWithNanosecondsオブジェクトの場合
                        if hasattr(due_date, 'strftime'):
                            due_date_str = due_date.strftime("%Y-%m-%d")
                        # 文字列の場合
                        elif isinstance(due_date, str):
                            due_date_str = due_date[:10] if len(due_date) >= 10 else due_date
                        else:
                            due_date_str = str(due_date)[:10]
                        
                        if due_date_str <= today:
                            review_count += 1
                    except Exception as e:
                        continue
                        
        except Exception as e:
            continue
    
    # 新規カード数を上限で制限
    new_count = min(new_count, new_cards_per_day)
    
    
    return review_count, new_count, completed_count


def _calculate_legacy_stats(cards: Dict, today: str, new_cards_per_day: int) -> Tuple[int, int]:
    """従来のロジックを使用してカード統計を計算（復習・新規のみ）"""
    review_count, new_count, _ = _calculate_legacy_stats_full(cards, today, new_cards_per_day)
    return review_count, new_count


def _determine_optimal_learning_mode(detailed_stats: Dict, review_count: int, new_count: int, completed_count: int) -> Tuple[str, str]:
    """学習統計から最適な学習モードを自動判定"""
    try:
        # 基本統計の取得
        accuracy_rate = detailed_stats.get("正答率", 0.0) if detailed_stats else 0.0
        weak_areas = detailed_stats.get("weak_categories", []) if detailed_stats else []
        total_study_days = detailed_stats.get("学習継続日数", 0) if detailed_stats else 0
        
        # 判定ロジック
        # 1. 復習重視：復習問題が多い場合
        if review_count >= 10:
            return "復習重視", f"復習予定が{review_count}問と多いため、記憶の定着を優先します"
        
        # 2. 弱点強化：正答率が低い場合（60%未満）または苦手分野が多い場合
        elif (accuracy_rate > 0 and accuracy_rate < 0.6) or len(weak_areas) > 2:
            return "弱点強化", f"正答率{accuracy_rate:.1%}や苦手分野があるため、弱点補強に集中します"
        
        # 3. 新規重視：学習開始初期または新規問題が多い場合
        elif total_study_days < 7 or (new_count >= 15 and review_count < 5):
            return "新規重視", f"学習初期段階または新規問題{new_count}問が多いため、新規学習を重視します"
        
        # 4. バランス学習：デフォルト（バランスよく学習）
        else:
            return "バランス学習", "復習と新規問題のバランスを取りながら、総合的に学習を進めます"
            
    except Exception as e:
        # エラー時はバランス学習をデフォルトに
        return "バランス学習", "学習データの分析中にエラーが発生したため、バランス学習で進めます"


class QuestionComponent:
    """問題表示コンポーネント（Reactライクな設計）"""
    
    @staticmethod
    def format_chemical_formula(text: str) -> str:
        """化学式をLaTeX形式に変換"""
        if not text:
            return text
        
        # よく使われる化学式パターンの変換
        replacements = {
            'Ca2+': r'$\mathrm{Ca^{2+}}$',
            'Mg2+': r'$\mathrm{Mg^{2+}}$',
            'H2O': r'$\mathrm{H_2O}$',
            'CO2': r'$\mathrm{CO_2}$',
            'OH-': r'$\mathrm{OH^-}$',
            'HCO3-': r'$\mathrm{HCO_3^-}$',
            'PO4-': r'$\mathrm{PO_4^-}$'
        }
        
        for pattern, replacement in replacements.items():
            text = text.replace(pattern, replacement)
        
        return text
    
    @staticmethod
    def get_image_source(question_data: Dict) -> Optional[str]:
        """
        問題データから画像ソースを取得する
        
        Args:
            question_data (Dict): 問題データの辞書
            
        Returns:
            Optional[str]: 画像URL/パス、または None
        """
        # まず image_urls をチェック
        image_urls = question_data.get('image_urls')
        if image_urls and len(image_urls) > 0:
            return image_urls[0]
        
        # 次に image_paths をチェック
        image_paths = question_data.get('image_paths')
        if image_paths and len(image_paths) > 0:
            return image_paths[0]
        
        # 両方とも空またはNoneの場合はNoneを返す
        return None
    
    @staticmethod
    def render_question_display(questions: List[Dict], case_data: Dict = None):
        """問題表示コンポーネント"""
        # CSSで余白を削除
        st.markdown("""
        <style>
        .st-emotion-cache-r44huj {
            margin-bottom: 0 !important;
            padding-bottom: 0 !important;
        }
        div[style*="background-color: rgb(250, 250, 250)"] {
            margin-top: 0 !important;
            padding-top: 12px !important;
        }
        [data-testid="stElementContainer"] {
            margin-top: 0 !important;
            margin-bottom: 0.25rem !important;
        }
        </style>
        """, unsafe_allow_html=True)
        
        # 症例情報エリア（連問の場合）
        if case_data and case_data.get('scenario_text'):
            with st.container():
                st.markdown(
                    f"""
                    <div style="
                        background-color: #e3f2fd; 
                        padding: 12px 16px; 
                        border-radius: 8px; 
                        border-left: 4px solid #2196f3; 
                        margin-bottom: 16px;
                    ">
                        📋 <strong>症例:</strong> {case_data['scenario_text']}
                    </div>
                    """, 
                    unsafe_allow_html=True
                )
            st.markdown("---")
        
        # 問題表示エリア
        for i, question in enumerate(questions):
            with st.container():
                # 問題ID
                question_number = question.get('number', '')
                if question_number:
                    st.markdown(f"#### {question_number}")
                
                # 問題文（化学式対応）
                question_text = QuestionComponent.format_chemical_formula(
                    question.get('question', '')
                )
                st.markdown(question_text)
                
                # 画像表示（問題文の後）
                image_urls = question.get('image_urls', []) or []
                image_paths = question.get('image_paths', []) or []
                all_images = image_urls + image_paths  # 両方のキーから画像を取得
                
                if all_images:
                    # 高画質表示用CSSを適用
                    inject_image_quality_css()
                    
                    # デバッグ情報
                    if st.session_state.get("debug_mode", False):
                        st.write(f"🔍 画像パス検出: {all_images}")
                    
                    for img_index, img_url in enumerate(all_images):
                        try:
                            # デバッグ情報
                            if st.session_state.get("debug_mode", False):
                                st.write(f"🔍 画像 {img_index + 1} 処理中: '{img_url}'")
                            
                            # Firebase Storageのパスを署名付きURLに変換
                            from utils import get_secure_image_url
                            secure_url = get_secure_image_url(img_url)
                            
                            # デバッグ情報
                            if st.session_state.get("debug_mode", False):
                                if secure_url:
                                    st.write(f"✅ 署名付きURL生成成功: {secure_url[:100]}...")
                                else:
                                    st.write(f"❌ 署名付きURL生成失敗: {img_url}")
                            
                            if secure_url:
                                # 画像を高品質で表示（レスポンシブ対応）
                                with st.expander(f"📸 問題 {question_number} の図 {img_index + 1}", expanded=True):
                                    st.image(
                                        secure_url, 
                                        caption=f"問題 {question_number} の図 {img_index + 1}",
                                        use_container_width=True  # コンテナ幅に合わせてレスポンシブ表示
                                    )
                            else:
                                st.warning(f"画像URLの生成に失敗しました: {img_url}")
                                if st.session_state.get("debug_mode", False):
                                    st.error(f"🚨 詳細: パス '{img_url}' から署名付きURLを生成できませんでした")
                        except Exception as e:
                            st.warning(f"画像を読み込めませんでした: {img_url}")
                            if st.session_state.get("debug_mode", False):
                                st.error(f"🚨 例外発生: {str(e)}")
                                st.exception(e)
                
                # 問題間の区切り
                if i < len(questions) - 1:
                    st.markdown("---")
    
    @staticmethod
    def shuffle_choices_with_mapping(choices: List[str]) -> tuple[List[str], dict]:
        """選択肢をシャッフルし、元のインデックスとの対応マップを返す"""
        if not choices:
            return [], {}
        
        # 元のインデックスとのマッピングを作成
        indexed_choices = [(i, choice) for i, choice in enumerate(choices)]
        random.shuffle(indexed_choices)
        
        shuffled_choices = [choice for _, choice in indexed_choices]
        # 新しいラベル → 元のラベルのマッピング
        label_mapping = {}
        for new_index, (original_index, _) in enumerate(indexed_choices):
            new_label = chr(ord('A') + new_index)
            original_label = chr(ord('A') + original_index)
            label_mapping[new_label] = original_label
        
        return shuffled_choices, label_mapping
    
    @staticmethod
    def get_choice_label(index: int) -> str:
        """選択肢のラベル生成 (A, B, C...)"""
        return chr(65 + index)


class AnswerModeComponent:
    """解答、結果表示、自己評価のUIをすべて管理する統合コンポーネント"""

    @staticmethod
    def render(questions: List[Dict], group_id: str, case_data: Dict = None) -> Dict[str, Any]:
        user_selections = {}
        action_result = {}
        
        is_checked = st.session_state.get(f"checked_{group_id}", False)
        
        # 連問（同じcase_idを持つ問題）の場合の特別処理
        if len(questions) > 1 and all(q.get('case_id') for q in questions):
            case_id = questions[0].get('case_id')
            if all(q.get('case_id') == case_id for q in questions):
                # 連問として表示
                return AnswerModeComponent._render_consecutive_questions(
                    questions, group_id, case_data, is_checked, user_selections, action_result
                )
        
        # 従来の単一問題または異なるcase_idの問題の処理
        if case_data and case_data.get('scenario_text'):
            st.info(f"📋 **症例:** {case_data['scenario_text']}")
        
        with st.form(key=f"answer_form_{group_id}"):
            for q_index, question in enumerate(questions):
                qid = question.get('number', '')
                st.markdown(f"#### {qid}")
                st.markdown(question.get('question', ''))
                
                # 選択肢のシャッフルとマッピング情報の保存
                shuffled_choices, label_mapping = st.session_state.setdefault(
                    f"shuffled_mapping_{qid}_{group_id}", 
                    QuestionComponent.shuffle_choices_with_mapping(question.get('choices', []))
                )
                st.session_state[f"label_mapping_{qid}_{group_id}"] = label_mapping

                # 選択肢の描画とユーザー選択の取得
                selected_labels = []
                for choice_index, choice_text in enumerate(shuffled_choices):
                    label = QuestionComponent.get_choice_label(choice_index)
                    is_selected = st.checkbox(
                        f"{label}. {choice_text}",
                        key=f"choice_{qid}_{choice_index}_{group_id}",
                        disabled=is_checked
                    )
                    if is_selected:
                        selected_labels.append(label)
                user_selections[qid] = selected_labels
                
                if q_index < len(questions) - 1:
                    st.markdown("---")

            # --- ▼▼▼【重要】ここからが修正箇所▼▼▼ ---
            
            # フォームの内側で状態に応じて表示を切り替える
            if not is_checked:
                # 【解答中のUI】
                st.markdown("---")
                col1, col2 = st.columns(2)
                with col1:
                    action_result['check_submitted'] = st.form_submit_button("回答をチェック", type="primary", use_container_width=True)
                with col2:
                    action_result['skip_submitted'] = st.form_submit_button("スキップ", use_container_width=True)
            else:
                # 【結果表示中のUI】
                result_data = st.session_state.get(f"result_{group_id}", {})
                
                # 1. 正誤判定のアラートバーをここに表示
                correct_count = sum(1 for r in result_data.values() if r.get('is_correct'))
                total_count = len(result_data)
                
                if correct_count == total_count:
                    # すべて正解の場合
                    if total_count == 1:
                        # 単一問題の場合、複数正解対応のメッセージを表示
                        qid = list(result_data.keys())[0]
                        q_result = result_data[qid]
                        user_ans = ''.join(q_result.get('user_answer', []))
                        correct_answer = q_result.get('correct_answer', '')
                        
                        from utils import QuestionUtils
                        main_msg, additional_info = QuestionUtils.get_answer_feedback_message(
                            user_ans, correct_answer, True
                        )
                        
                        if additional_info:
                            st.success(f"{main_msg} {additional_info}")
                        else:
                            st.success(main_msg)
                    else:
                        # 複数問題の場合
                        st.success("✅ 全問正解！")
                else:
                    # 不正解の場合
                    if total_count == 1:
                        # 単一問題の場合、シンプルな表示
                        qid = list(result_data.keys())[0]
                        q_result = result_data[qid]
                        user_ans = ''.join(q_result.get('user_answer', [])) or '無回答'
                        correct_answer = q_result.get('correct_answer', '')
                        
                        from utils import QuestionUtils
                        main_msg, additional_info = QuestionUtils.get_answer_feedback_message(
                            user_ans, correct_answer, False
                        )
                        
                        # 連問でもシャッフル後の正解を使用
                        # シャッフル後の正解ラベルと選択肢テキストを取得
                        shuffled_labels = q_result.get('shuffled_correct_answer_labels', [])
                        shuffled_texts = q_result.get('shuffled_correct_answer_texts', [])
                        
                        # シャッフル後の正解表示を優先使用
                        if shuffled_labels and shuffled_texts:
                            # シャッフル後のラベルと選択肢テキストで表示
                            correct_display_parts = []
                            for label, text in zip(shuffled_labels, shuffled_texts):
                                correct_display_parts.append(f"{label}. {text}")
                            correct_display = " または ".join(correct_display_parts)
                            st.error(f"{main_msg} 正解：{correct_display}")
                        elif additional_info:
                            st.error(f"{main_msg} {additional_info}")
                        else:
                            st.error(f"{main_msg} 正解：{correct_answer}")
                    else:
                        # 複数問題の場合は詳細表示
                        incorrect_details = []
                        for qid, q_result in result_data.items():
                            if not q_result.get('is_correct'):
                                user_ans = ''.join(q_result.get('user_answer', [])) or '無回答'
                                correct_answer = q_result.get('correct_answer', '')
                                
                                from utils import QuestionUtils
                                _, additional_info = QuestionUtils.get_answer_feedback_message(
                                    user_ans, correct_answer, False
                                )
                                
                                # シャッフル後の正解ラベルと選択肢テキストを取得
                                shuffled_labels = q_result.get('shuffled_correct_answer_labels', [])
                                shuffled_texts = q_result.get('shuffled_correct_answer_texts', [])
                                
                                if shuffled_labels and shuffled_texts:
                                    # シャッフル後のラベルと選択肢テキストで表示
                                    correct_display_parts = []
                                    for label, text in zip(shuffled_labels, shuffled_texts):
                                        correct_display_parts.append(f"{label}. {text}")
                                    correct_display = ", ".join(correct_display_parts)
                                else:
                                    # フォールバック: 元の正解ラベルを表示
                                    correct_display = additional_info or f"正解：{correct_answer}"
                                
                                incorrect_details.append(f"**{qid}**: あなたの解答: `{user_ans}` | {correct_display}")
                        st.error("❌ 不正解の問題がありました。\n\n" + "\n\n".join(incorrect_details))

                # 2. その下に自己評価フォームを表示
                st.markdown("---")
                st.markdown("#### 自己評価")
                quality_options = ["× もう一度", "△ 難しい", "○ 普通", "◎ 簡単"]
                default_index = 2 if correct_count == total_count else 1
                
                quality = st.radio(
                    "学習評価", options=quality_options, index=default_index,
                    key=f"quality_{group_id}", horizontal=True, label_visibility="collapsed"
                )
                action_result['quality'] = quality
                action_result['next_submitted'] = st.form_submit_button("次の問題へ", type="primary", use_container_width=True)
        
        # --- ▲▲▲ここまで▲▲▲ ---

        action_result['user_selections'] = user_selections
        
        # 画像はフォームの外（常に最後）に表示
        for question in questions:
            all_images = (question.get('image_urls', []) or []) + (question.get('image_paths', []) or [])
            if all_images:
                with st.expander(f"📸 {question.get('number', '')}の図を見る", expanded=is_checked):
                    for img_url in all_images:
                        from utils import get_secure_image_url
                        secure_url = get_secure_image_url(img_url)
                        if secure_url:
                            st.image(secure_url, use_container_width=True)
                            
        return action_result

    @staticmethod
    def _render_consecutive_questions(questions: List[Dict], group_id: str, case_data: Dict, 
                                    is_checked: bool, user_selections: Dict, action_result: Dict) -> Dict[str, Any]:
        """連問の統合表示"""
        
        # 症例文がある場合は最初に表示（症例:ラベルを削除）
        if case_data and case_data.get('scenario_text'):
            st.info(case_data['scenario_text'])
        
        with st.form(key=f"answer_form_{group_id}"):
            # 連問を順番に表示
            for q_index, question in enumerate(questions):
                qid = question.get('number', '')
                
                # 問題番号と問題文を表示
                st.markdown(f"#### {qid}")
                st.markdown(question.get('question', ''))
                
                # 選択肢のシャッフルとマッピング情報の保存
                shuffled_choices, label_mapping = st.session_state.setdefault(
                    f"shuffled_mapping_{qid}_{group_id}", 
                    QuestionComponent.shuffle_choices_with_mapping(question.get('choices', []))
                )
                st.session_state[f"label_mapping_{qid}_{group_id}"] = label_mapping

                # 選択肢の描画とユーザー選択の取得
                selected_labels = []
                for choice_index, choice_text in enumerate(shuffled_choices):
                    label = QuestionComponent.get_choice_label(choice_index)
                    is_selected = st.checkbox(
                        f"{label}. {choice_text}",
                        key=f"choice_{qid}_{choice_index}_{group_id}",
                        disabled=is_checked
                    )
                    if is_selected:
                        selected_labels.append(label)
                user_selections[qid] = selected_labels
                
                # 問題間の区切り線
                if q_index < len(questions) - 1:
                    st.markdown("---")

            # フォームの内側で状態に応じて表示を切り替える
            if not is_checked:
                # 【解答中のUI】
                st.markdown("---")
                col1, col2 = st.columns(2)
                with col1:
                    action_result['check_submitted'] = st.form_submit_button("回答をチェック", type="primary", use_container_width=True)
                with col2:
                    action_result['skip_submitted'] = st.form_submit_button("スキップ", use_container_width=True)
            else:
                # 【結果表示中のUI】
                result_data = st.session_state.get(f"result_{group_id}", {})
                
                # 1. 正誤判定のアラートバーをここに表示
                correct_count = sum(1 for r in result_data.values() if r.get('is_correct'))
                total_count = len(result_data)
                
                if correct_count == total_count:
                    # すべて正解の場合
                    if total_count == 1:
                        # 単一問題の場合、複数正解対応のメッセージを表示
                        qid = list(result_data.keys())[0]
                        q_result = result_data[qid]
                        user_ans = ''.join(q_result.get('user_answer', []))
                        correct_answer = q_result.get('correct_answer', '')
                        
                        from utils import QuestionUtils
                        main_msg, additional_info = QuestionUtils.get_answer_feedback_message(
                            user_ans, correct_answer, True
                        )
                        
                        if additional_info:
                            st.success(f"{main_msg} {additional_info}")
                        else:
                            st.success(main_msg)
                    else:
                        # 複数問題の場合
                        st.success("✅ 全問正解！")
                else:
                    # 不正解の場合
                    if total_count == 1:
                        # 単一問題の場合、シンプルな表示
                        qid = list(result_data.keys())[0]
                        q_result = result_data[qid]
                        user_ans = ''.join(q_result.get('user_answer', [])) or '無回答'
                        correct_answer = q_result.get('correct_answer', '')
                        
                        from utils import QuestionUtils
                        main_msg, additional_info = QuestionUtils.get_answer_feedback_message(
                            user_ans, correct_answer, False
                        )
                        
                        # 単一問題でもシャッフル後の正解を使用
                        # シャッフル後の正解ラベルと選択肢テキストを取得
                        shuffled_labels = q_result.get('shuffled_correct_answer_labels', [])
                        shuffled_texts = q_result.get('shuffled_correct_answer_texts', [])
                        
                        # シャッフル後の正解表示を優先使用
                        if shuffled_labels and shuffled_texts:
                            # シャッフル後のラベルと選択肢テキストで表示
                            correct_display_parts = []
                            for label, text in zip(shuffled_labels, shuffled_texts):
                                correct_display_parts.append(f"{label}. {text}")
                            correct_display = " または ".join(correct_display_parts)
                            st.error(f"{main_msg} 正解：{correct_display}")
                        elif additional_info:
                            st.error(f"{main_msg} {additional_info}")
                        else:
                            st.error(f"{main_msg} 正解：{correct_answer}")
                    else:
                        # 複数問題の場合は詳細表示
                        incorrect_details = []
                        for qid, q_result in result_data.items():
                            if not q_result.get('is_correct'):
                                user_ans = ''.join(q_result.get('user_answer', [])) or '無回答'
                                correct_answer = q_result.get('correct_answer', '')
                                
                                from utils import QuestionUtils
                                _, additional_info = QuestionUtils.get_answer_feedback_message(
                                    user_ans, correct_answer, False
                                )
                                
                                # シャッフル後の正解ラベルと選択肢テキストを取得
                                shuffled_labels = q_result.get('shuffled_correct_answer_labels', [])
                                shuffled_texts = q_result.get('shuffled_correct_answer_texts', [])
                                
                                if shuffled_labels and shuffled_texts:
                                    # シャッフル後のラベルと選択肢テキストで表示
                                    correct_display_parts = []
                                    for label, text in zip(shuffled_labels, shuffled_texts):
                                        correct_display_parts.append(f"{label}. {text}")
                                    correct_display = ", ".join(correct_display_parts)
                                else:
                                    # フォールバック: 元の正解ラベルを表示
                                    correct_display = additional_info or f"正解：{correct_answer}"
                                
                                incorrect_details.append(f"**{qid}**: あなたの解答: `{user_ans}` | {correct_display}")
                        st.error("❌ 不正解の問題がありました。\n\n" + "\n\n".join(incorrect_details))

                # 2. その下に自己評価フォームを表示
                st.markdown("---")
                st.markdown("#### 自己評価")
                quality_options = ["× もう一度", "△ 難しい", "○ 普通", "◎ 簡単"]
                default_index = 2 if correct_count == total_count else 1
                
                quality = st.radio(
                    "学習評価", options=quality_options, index=default_index,
                    key=f"quality_{group_id}", horizontal=True, label_visibility="collapsed"
                )
                action_result['quality'] = quality
                action_result['next_submitted'] = st.form_submit_button("次の問題へ", type="primary", use_container_width=True)

        action_result['user_selections'] = user_selections
        
        # 症例画像をフォームの外に表示（通常の問題画像と同じ扱い）
        if case_data and case_data.get('image_urls'):
            with st.expander("📸 症例画像を見る", expanded=is_checked):
                for img_url in case_data.get('image_urls', []):
                    from utils import get_secure_image_url
                    secure_url = get_secure_image_url(img_url)
                    if secure_url:
                        st.image(secure_url, use_container_width=True)
        
        # 各問題の画像（症例画像以外）はフォームの外に表示
        for question in questions:
            all_images = (question.get('image_urls', []) or []) + (question.get('image_paths', []) or [])
            if all_images:
                with st.expander(f"📸 {question.get('number', '')}の図を見る", expanded=is_checked):
                    for img_url in all_images:
                        from utils import get_secure_image_url
                        secure_url = get_secure_image_url(img_url)
                        if secure_url:
                            st.image(secure_url, use_container_width=True)
        
        return action_result

    @staticmethod
    def _is_ordering_question(question_text: str, choices: List[str] = None) -> bool:
        """並び替え問題の判定"""
        # 明確な並び替えキーワードがある場合のみ並び替え問題と判定
        strict_ordering_keywords = ['順番', '順序', '配列', '並び替え']
        
        # 明確な並び替えキーワードがある場合
        if any(keyword in question_text for keyword in strict_ordering_keywords):
            return True
        
        # 「手順」キーワードがある場合は選択肢もチェック
        if '手順' in question_text and choices:
            # 選択肢が単語の組み合わせ（例：「ア→イ→ウ」）の場合のみ並び替え問題
            # 通常の文章選択肢の場合は並び替え問題ではない
            choice_pattern_count = 0
            for choice in choices:
                # 矢印やカンマで区切られた短い記号パターンを検出
                if ('→' in choice or ',' in choice) and len(choice) < 20:
                    choice_pattern_count += 1
            
            # 選択肢の大部分が順序パターンの場合のみ並び替え問題
            return choice_pattern_count >= len(choices) * 0.8
        
        return False


class PracticeSession:
    """練習セッションを管理するクラス"""
    
    def __init__(self):
        if get_firestore_manager:
            self.firestore_manager = get_firestore_manager()
        else:
            self.firestore_manager = None
    
    def get_next_q_group(self) -> List[str]:
        """次の問題グループを取得（日本時間ベース）"""
        now = get_japan_now()
        
        # 利用可能な復習問題を取得
        stq = st.session_state.get("short_term_review_queue", [])
        ready_reviews = []
        for i, item in enumerate(stq):
            ra = item.get("ready_at")
            if isinstance(ra, str):
                try:
                    ra = datetime.datetime.fromisoformat(ra)
                except Exception:
                    ra = now
            if not ra or ra <= now:
                ready_reviews.append((i, item))
        
        # 利用可能な新規問題を取得
        main_queue = st.session_state.get("main_queue", [])
        
        # 復習問題と新規問題のバランス調整
        review_count = len(ready_reviews)
        new_count = len(main_queue)
        
        
        # 復習問題が5個以上溜まっている場合は復習を優先
        if review_count >= 5:
            if ready_reviews:
                i, item = ready_reviews[0]
                stq.pop(i)
                st.session_state["short_term_review_queue"] = stq
                result_group = item.get("group", [])
                return result_group
        
        # 通常時：復習30%、新規70%の確率で選択
        elif review_count > 0 and new_count > 0:
            if random.random() < 0.3:  # 30%の確率で復習
                i, item = ready_reviews[0]
                stq.pop(i)
                st.session_state["short_term_review_queue"] = stq
                result_group = item.get("group", [])
                return result_group
            else:
                result_group = main_queue.pop(0) if main_queue else []
                st.session_state["main_queue"] = main_queue
                return result_group
        
        # 復習問題のみ利用可能
        elif ready_reviews:
            i, item = ready_reviews[0]
            stq.pop(i)
            st.session_state["short_term_review_queue"] = stq
            result_group = item.get("group", [])
            return result_group
        
        # 新規問題のみ利用可能
        elif main_queue:
            result_group = main_queue.pop(0)
            st.session_state["main_queue"] = main_queue
            return result_group
        
        # 問題がない場合
        return []
    
    def enqueue_short_review(self, group: List[str], minutes: int):
        """短期復習キューに追加（日本時間ベース）"""
        ready_at = get_japan_now() + datetime.timedelta(minutes=minutes)
        if "short_term_review_queue" not in st.session_state:
            st.session_state.short_term_review_queue = []
        st.session_state.short_term_review_queue.append({
            "group": group,
            "ready_at": ready_at
        })
    
    def setup_daily_quiz_from_cloud_function(self):
        """Cloud Functionからおまかせクイズをセットアップ"""
        uid = st.session_state.get("uid")
        if not uid:
            st.error("ユーザーIDが見つかりません")
            return False
        
        # getDailyQuiz Cloud Functionを呼び出し
        from auth import call_cloud_function
        payload = {"uid": uid}
        
        result = call_cloud_function("getDailyQuiz", payload)
        
        if result and result.get("success"):
            # Cloud Functionから返された学習キューをセッションに設定
            cloud_data = result.get("data", {})
            
            st.session_state["main_queue"] = cloud_data.get("main_queue", [])
            st.session_state["current_q_group"] = cloud_data.get("current_q_group", [])
            st.session_state["short_term_review_queue"] = cloud_data.get("short_term_review_queue", [])
            
            queue_info = f"新規: {len(st.session_state['main_queue'])}グループ, " \
                        f"現在: {len(st.session_state['current_q_group'])}問, " \
                        f"復習: {len(st.session_state['short_term_review_queue'])}グループ"
            
            st.success(f"おまかせ学習キューを生成しました\n{queue_info}")
            return True
        else:
            # Cloud Function失敗時はエラーメッセージを表示
            st.error("学習キューの生成に失敗しました。しばらく待ってから再度お試しください。")
            return False

def render_practice_page(auth_manager=None):
    """練習ページのメイン描画関数（uid統一版）"""
    practice_session = PracticeSession()
    
    # ユーザー認証チェック
    if auth_manager is None:
        if AuthManager:
            auth_manager = AuthManager()
        else:
            st.error("認証システムが利用できません")
            return
    if not auth_manager.ensure_valid_session():
        st.error("セッションが無効です。再ログインしてください。")
        return
    
    uid = st.session_state.get("uid")
    if not uid:
        st.error("ユーザーIDが見つかりません。")
        return
    
    
    # 前回セッション復帰処理
    if st.session_state.get("continue_previous") and st.session_state.get("session_choice_made"):
        st.success("前回のセッションを復帰しました")
        st.session_state.pop("continue_previous", None)
        
        if st.session_state.get("current_question_index") is not None:
            st.info(f"問題 {st.session_state.get('current_question_index', 0) + 1} から継続します")
    
    # セッション状態を確認
    session_choice_made = st.session_state.get("session_choice_made")
    main_queue = st.session_state.get("main_queue")
    
    # サイドバーで学習モードが選択されていない場合は何も表示せずに終了
    if not session_choice_made and not main_queue:
        # 何も表示しないのではなく、ウェルカムメッセージを表示
        try:
            st.markdown("### 📚 学習を開始しましょう")
            st.info("👈 左のサイドバーから学習モードを選択して、学習を開始してください。")
        except Exception as e:
            st.error(f"表示エラー: {e}")
        return
    
    # アクティブセッション表示
    _render_active_session(practice_session, uid)


def _render_active_session(practice_session: PracticeSession, uid: str):
    """アクティブな学習セッションの表示"""
    session_type = st.session_state.get("session_type", "")
    
    # セッションタイプが空の場合、current_session_typeまたはpractice_modeから推測
    if not session_type:
        session_type = st.session_state.get("current_session_type", "")
        if not session_type and st.session_state.get("practice_mode") == "auto":
            session_type = "おまかせ演習"
    
    # セッションタイプに応じた処理
    session_type = st.session_state.get("session_type", "")
    
    # バランス学習、弱点強化、復習重視、新規重視は全ておまかせ演習として処理
    if session_type in ["バランス学習", "弱点強化", "復習重視", "新規重視", "おまかせ演習", "自動学習", "おまかせ学習"]:
        _render_omakase_session(practice_session, uid)
    elif session_type.startswith("自由演習"):
        _render_free_learning_session(practice_session, uid)
    else:
        st.error(f"セッションタイプが不明です: {session_type}")
        st.info("サイドバーから学習を再開してください。")


def _render_omakase_session(practice_session: PracticeSession, uid: str):
    """おまかせ演習セッションの表示"""
    #st.header("おまかせ演習")
    st.markdown('<h2 style="margin-bottom: 0px;">おまかせ演習</h2>', unsafe_allow_html=True) # ← 新しいコードを追加
    
    
    # 現在の問題グループを取得
    current_group = st.session_state.get("current_q_group", [])
    
    # 問題グループが空の場合、次のグループを取得
    if not current_group:
        current_group = practice_session.get_next_q_group()
        if current_group:
            st.session_state["current_q_group"] = current_group
            st.session_state["current_question_index"] = 0
        else:
            # セッション完了時のイベント追跡
            if not st.session_state.get("session_completed_logged"):
                session_start_time = st.session_state.get("session_start_time", time.time())
                session_duration = time.time() - session_start_time
                session_type = st.session_state.get("session_type", "おまかせ演習")
                
                log_to_ga("study_session_completion", uid, {
                    "session_type": session_type,
                    "session_duration_seconds": session_duration,
                    "questions_completed": len(st.session_state.get("main_queue", [])),
                    "completion_method": "all_questions_finished"
                })
                
                st.session_state["session_completed_logged"] = True
            
            st.info("📚 全ての問題が完了しました！新しいセッションを開始してください。")
            if st.button("新しいセッションを開始"):
                _reset_session()
            return
    
    # 問題表示
    _display_current_question(practice_session, uid)


def _render_free_learning_session(practice_session: PracticeSession, uid: str):
    """自由演習セッションの表示"""
    session_type = st.session_state.get("session_type", "自由演習")
    st.header(session_type)
    
    # 現在の問題グループを取得
    current_group = st.session_state.get("current_q_group", [])
    
    # 問題グループが空の場合、次のグループを取得
    if not current_group:
        current_group = practice_session.get_next_q_group()
        if current_group:
            st.session_state["current_q_group"] = current_group
            st.session_state["current_question_index"] = 0
        else:
            # セッション完了時のイベント追跡
            if not st.session_state.get("session_completed_logged"):
                session_start_time = st.session_state.get("session_start_time", time.time())
                session_duration = time.time() - session_start_time
                
                log_to_ga("study_session_completion", uid, {
                    "session_type": session_type,
                    "session_duration_seconds": session_duration,
                    "questions_completed": len(st.session_state.get("main_queue", [])),
                    "completion_method": "all_questions_finished"
                })
                
                st.session_state["session_completed_logged"] = True
            
            st.info("📚 全ての問題が完了しました！新しいセッションを開始してください。")
            if st.button("新しいセッションを開始"):
                _reset_session()
            return
    
    # 問題表示
    _display_current_question(practice_session, uid)








def _is_review_mode(current_group: List[str]) -> bool:
    """
    現在の問題グループが復習モードかどうかを判定
    復習モードの場合、問題を再度解けるようにチェック状態をリセットする
    """
    if not current_group:
        return False
        
    # セッション状態から復習関連のフラグを確認
    # 1. 復習セッションフラグが設定されているかチェック
    if st.session_state.get("is_review_session", False):
        return True
    
    # 2. 今日の復習セッションかどうかをチェック
    practice_session = st.session_state.get("practice_session")
    if practice_session and hasattr(practice_session, 'is_review_session'):
        return getattr(practice_session, 'is_review_session', False)
    
    # 3. 短期復習キューから来た問題かどうかをチェック
    short_term_queue = st.session_state.get("short_term_review_queue", [])
    if any(qid in current_group for qid in short_term_queue):
        return True
    
    # 4. result_logに既に記録されている問題かどうかをチェック（復習の可能性）
    result_log = st.session_state.get("result_log", {})
    if any(qid in result_log for qid in current_group):
        # ただし、今回の学習セッションで新たに出題された問題は除外
        current_session_new_questions = st.session_state.get("current_session_new_questions", set())
        if not any(qid in current_session_new_questions for qid in current_group):
            return True
    
    return False


def _display_current_question(practice_session: PracticeSession, uid: str):
    """現在の問題を表示（コンポーネントベースの実装）"""
    
    # 問題表示エリアの余白を調整
    st.markdown("""
    <style>
    div[style*="background-color: rgb(250, 250, 250)"] {
        margin-top: 0 !important;
        padding-top: 8px !important;
    }
    [data-testid="stElementContainer"] {
        margin-top: 0 !important;
        margin-bottom: 0.25rem !important;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # 1. 表示する問題グループの決定
    current_group = st.session_state.get("current_q_group", [])
    
    if not current_group:
        # キューから次の問題グループを取得
        next_group = practice_session.get_next_q_group()
        if next_group:
            st.session_state["current_q_group"] = next_group
            st.session_state["current_question_index"] = 0
            current_group = next_group
        else:
            st.success("🎉 全ての問題が完了しました！")
            if st.button("新しいセッションを開始"):
                _reset_session()
            return
    
    # 問題データの準備
    q_objects = []
    case_data = None
    
    for qid in current_group:
        question = ALL_QUESTIONS_DICT.get(qid)
        if question:
            q_objects.append(question)
            # 連問（症例問題）の特別処理
            if question.get('case_id') and not case_data:
                case_data = _get_case_data(question.get('case_id'))
    
    if not q_objects:
        st.error("問題データが見つかりません")
        return
    
    # グループIDの生成（問題の一意識別用）
    group_id = "_".join(current_group)
    st.session_state["current_group_id"] = group_id  # 結果表示で使用するため保存
    
    # ▼▼▼ 常にAnswerModeComponentを呼び出すように変更 ▼▼▼
    
    # is_checkedフラグによる分岐をなくし、ResultModeComponentの呼び出しを完全に削除
    action_result = AnswerModeComponent.render(q_objects, group_id, case_data)
    
    # action_resultがNoneの場合の安全な処理
    if action_result is None:
        action_result = {}
    
    if action_result.get('check_submitted'):
        _process_group_answer_improved(
            q_objects, action_result['user_selections'], group_id
        )
    elif action_result.get('skip_submitted'):
        _skip_current_group(practice_session)
    elif action_result.get('next_submitted'):
        _process_self_evaluation_improved(
            q_objects, action_result['quality'], group_id, practice_session, uid
        )


def _process_group_answer_improved(q_objects: List[Dict], user_selections: Dict, 
                                 group_id: str):
    """改善された解答処理（自己評価時のみ記録）"""
    result_data = {}
    
    for question in q_objects:
        qid = question.get('number', '')
        user_answer = user_selections.get(qid, '')
        correct_answer = question.get('answer', '')
        
        # ラベルマッピングを取得（シャッフルされた選択肢の場合）
        mapping_key = f"label_mapping_{qid}_{group_id}"
        label_mapping = st.session_state.get(mapping_key, {})
        
        # ▼▼▼ user_answer_str生成ロジックを置換 ▼▼▼
        user_answer_str = ""
        if isinstance(user_answer, list):
            # user_answerは['A', 'C']のようなラベルのリスト
            original_labels = [label_mapping.get(label, label) for label in user_answer]
            user_answer_str = "".join(sorted(original_labels))
        elif isinstance(user_answer, str):
            # テキスト入力の場合（並び替え問題など）
            mapped_chars = [label_mapping.get(char, char) for char in user_answer.upper()]
            user_answer_str = "".join(mapped_chars)
        # 正誤判定（集合比較による堅牢な判定）
        # 文字列比較ではなく、含まれる文字の集合が一致するかで判定
        # これにより順序や空白・特殊文字の問題を回避
        correct_answer_set = set(correct_answer.strip().upper())
        user_answer_set = set(user_answer_str.strip().upper())
        is_correct = (correct_answer_set == user_answer_set)
        
        # デバッグ情報（集合比較）
        if st.session_state.get("debug_mode", False):
            st.write(f"  正解文字集合: {correct_answer_set}")
            st.write(f"  ユーザー文字集合: {user_answer_set}")
            st.write(f"  判定結果: {is_correct}")
        
        # シャッフル後の正解ラベルを計算
        shuffled_correct_answer_labels = []
        shuffled_correct_answer_texts = []
        
        if label_mapping:
            # label_mapping の逆引きマップを作成: {original_label: new_label}
            reverse_mapping = {original_label: new_label for new_label, original_label in label_mapping.items()}
            
            # 正解ラベル（例: 'B', 'BC'など）の各文字について、シャッフル後のラベルを取得
            for correct_char in correct_answer.strip().upper():
                shuffled_label = reverse_mapping.get(correct_char, correct_char)
                shuffled_correct_answer_labels.append(shuffled_label)
            
            # 選択肢テキストも取得
            shuffled_choices_key = f"shuffled_mapping_{qid}_{group_id}"
            shuffled_choices_data = st.session_state.get(shuffled_choices_key, ([], {}))
            shuffled_choices = shuffled_choices_data[0] if isinstance(shuffled_choices_data, tuple) else shuffled_choices_data
            
            for shuffled_label in shuffled_correct_answer_labels:
                # ラベル（A, B, C...）をインデックスに変換
                choice_index = ord(shuffled_label) - ord('A')
                if 0 <= choice_index < len(shuffled_choices):
                    shuffled_correct_answer_texts.append(shuffled_choices[choice_index])
        
        result_data[qid] = {
            'user_answer': user_answer,
            'user_answer_str': user_answer_str,
            'correct_answer': correct_answer,
            'shuffled_correct_answer_labels': shuffled_correct_answer_labels,
            'shuffled_correct_answer_texts': shuffled_correct_answer_texts,
            'is_correct': is_correct
        }
    
    # 結果をセッションに保存（自己評価まで待機）
    st.session_state[f"result_{group_id}"] = result_data
    st.session_state[f"checked_{group_id}"] = True
    
    # 各問題の回答チェック済みフラグを設定
    for question in q_objects:
        qid = question.get('number', '')
        answer_checked_key = f"answer_checked_{qid}_{group_id}"
        st.session_state[answer_checked_key] = True
    
    # 成功メッセージ（自己評価への案内）
    all_correct = all(result['is_correct'] for result in result_data.values())
    if all_correct:
        st.success("🎉 全問正解です！自己評価をして学習記録を保存しましょう。")
    else:
        correct_count = sum(1 for result in result_data.values() if result['is_correct'])
        total_count = len(result_data)
        st.info(f"📊 {correct_count}/{total_count} 問正解 - 自己評価をして学習記録を保存しましょう。")
    
    st.rerun()


def _process_self_evaluation_improved(q_objects: List[Dict], quality_text: str, 
                                    group_id: str, practice_session: PracticeSession, uid: str):
    """改善された自己評価処理（学習記録の確定処理）"""
    
    # 品質スコアの変換（4段階評価）
    quality_mapping = {
        "◎ 簡単": 5,
        "○ 普通": 4,
        "△ 難しい": 2,
        "× もう一度": 1
    }
    quality = quality_mapping.get(quality_text, 3)
    
    # 各問題のSM2更新
    cards = st.session_state.get("cards", {})
    updated_cards = []
    
    # 検索進捗ページ用の学習ログ更新
    try:
        from modules.search_page import update_session_evaluation_log
        current_time = datetime.datetime.now()
        for question in q_objects:
            qid = question.get('number', '')
            update_session_evaluation_log(qid, quality, current_time)
    except ImportError:
        pass
    except Exception as e:
        pass
    
    for question in q_objects:
        qid = question.get('number', '')
        
        if qid not in cards:
            cards[qid] = {
                "n": 0,
                "EF": 2.5,
                "interval": 0,
                "due": None,
                "history": []
            }
        
        card = cards[qid]
        updated_card = SM2Algorithm.sm2_update_with_policy(card, quality, qid)
        cards[qid] = updated_card
        updated_cards.append((qid, updated_card))
        
        # Firestoreに保存（非同期・エラー無視で軽量化）
        try:
            if save_user_data:
                print(f"💾 演習結果を保存中: {qid} (UID: {uid[:8]}...)")
                save_user_data(uid, qid, updated_card)
                print(f"✅ 保存完了: {qid}")
            else:
                print(f"❌ save_user_data関数が利用できません")
        except Exception as e:
            # 保存エラーは無視（後でリトライ）
            print(f"❌ 保存エラー: {qid} - {e}")
            pass
    
    # セッション状態を強制的に更新
    st.session_state["cards"] = cards.copy()  # コピーして確実に更新を検知させる
    
    # ランキングスコア更新（カード更新後に実行）
    try:
        from modules.ranking_calculator import update_user_ranking_scores
        evaluation_logs = st.session_state.get('evaluation_logs', [])
        user_profile = st.session_state.get('user_profile', {})
        
        # ユーザープロフィールが設定されていない場合は初期化
        if not user_profile or not user_profile.get('uid'):
            from firestore_db import get_user_profile_for_ranking, save_user_profile
            profile = get_user_profile_for_ranking(uid)
            if profile:
                user_profile = {
                    "uid": uid,
                    "nickname": profile.get("nickname", f"ユーザー{uid[:8]}"),
                    "show_on_leaderboard": profile.get("show_on_leaderboard", True),
                    "email": st.session_state.get("email", "")
                }
            else:
                # プロフィールが存在しない場合はデフォルト値で作成
                default_nickname = f"ユーザー{uid[:8]}"
                user_profile = {
                    "uid": uid,
                    "nickname": default_nickname,
                    "show_on_leaderboard": True,
                    "email": st.session_state.get("email", "")
                }
                save_user_profile(uid, default_nickname, True)
            
            st.session_state['user_profile'] = user_profile
        
        nickname = user_profile.get('nickname', f"ユーザー{uid[:8]}")
        # 更新されたカードデータを使用
        ranking_data = update_user_ranking_scores(uid, cards, evaluation_logs, nickname)
        
    except ImportError:
        pass
    except Exception as e:
        pass
    
    # サイドバーの評価分布を強制更新するためのキーを更新
    current_time = get_japan_now().isoformat()
    st.session_state["last_evaluation_update"] = current_time
    
    # 学習ログに記録（自己評価時のみ）
    result_log = st.session_state.get("result_log", {})
    
    for question in q_objects:
        qid = question.get('number', '')
        result_data = st.session_state.get(f"result_{group_id}", {}).get(qid, {})
        
        new_record = {
            "timestamp": get_japan_now().isoformat(),  # 日本時間で記録
            "correct": result_data.get('is_correct', False),
            "selected": result_data.get('user_answer_str', ''),
            "quality": quality
        }
        
        result_log[qid] = new_record
    
    st.session_state["result_log"] = result_log
    
    # Google Analytics ログ（自己評価完了時のみ）
    session_type = st.session_state.get("session_type", "unknown")
    question_count = len(q_objects)
    result_data = st.session_state.get(f"result_{group_id}", {})
    correct_count = sum(1 for result in result_data.values() if result['is_correct'])
    
    try:
        log_to_ga("self_evaluation_completed", uid, {
            "question_count": question_count,
            "correct_count": correct_count,
            "quality": quality,
            "quality_text": quality_text,
            "session_type": session_type,
            "group_id": group_id
        })
    except Exception as e:
        # ログエラーは無視（UX優先）
        pass
    
    # 現在のグループを短期復習キューに追加（品質が低い場合）
    if quality <= 2:
        current_group = st.session_state.get("current_q_group", [])
        practice_session.enqueue_short_review(current_group, 15)  # 15分後に復習
        st.info("🔄 復習が必要な問題として15分後に再出題されます")
    
    # セッション状態のクリーンアップ
    keys_to_remove = [f"checked_{group_id}", f"result_{group_id}"]
    for key in keys_to_remove:
        st.session_state.pop(key, None)
    
    # シャッフルされた選択肢のキーもクリーンアップ
    for question in q_objects:
        qid = question.get('number', '')
        shuffle_key = f"shuffled_choices_{qid}_{group_id}"
        st.session_state.pop(shuffle_key, None)
    
    # 次の問題グループを取得
    next_group = practice_session.get_next_q_group()
    if next_group:
        st.session_state["current_q_group"] = next_group
        st.success("✅ 学習記録を保存しました。次の問題に進みます！")
    else:
        st.session_state["current_q_group"] = []
        st.success("🎉 全ての問題が完了しました！お疲れ様でした！")
    
    # サイドバーの表示を即座に更新するためのフラグ
    st.session_state["sidebar_refresh_needed"] = True
    
    st.rerun()


def _get_case_data(case_id: str) -> Dict[str, Any]:
    """症例データを取得"""
    # CASES辞書から直接症例データを取得
    if case_id in CASES:
        case_info = CASES[case_id]
        return {
            'scenario_text': case_info.get('scenario_text', ''),
            'image_urls': case_info.get('image_urls', []),
            'case_id': case_id
        }
    
    # フォールバック: ALL_QUESTIONSから検索（旧ロジック）
    for question in ALL_QUESTIONS:
        if question.get('case_id') == case_id and question.get('scenario_text'):
            return {
                'scenario_text': question.get('scenario_text', ''),
                'image_urls': question.get('image_urls', []),
                'case_id': case_id
            }
    
    return None


def _skip_current_group(practice_session: PracticeSession):
    """現在の問題グループをスキップ"""
    import time
    
    current_group = st.session_state.get("current_q_group", [])
    
    if current_group:
        # スキップした問題をキューの末尾に戻す
        main_queue = st.session_state.get("main_queue", [])
        main_queue.append(current_group)
        st.session_state["main_queue"] = main_queue
        st.info("📚 問題をスキップしました。後ほど再出題されます。")
    
    # スキップ時刻を記録（統計計算スキップのため）
    st.session_state["last_skip_time"] = time.time()
    
    # 次の問題グループを取得
    next_group = practice_session.get_next_q_group()
    if next_group:
        st.session_state["current_q_group"] = next_group
    else:
        st.session_state["current_q_group"] = []
    
    st.rerun()


def _reset_session():
    """セッションをリセット"""
    keys_to_reset = [
        "session_choice_made", "session_type", "current_q_group", 
        "main_queue", "short_term_review_queue",
        "session_completed_logged", "session_start_time",
        "is_review_session"  # 復習セッションフラグもリセット
    ]
    
    for key in keys_to_reset:
        st.session_state.pop(key, None)
    
    # 問題関連のセッション状態もクリーンアップ
    keys_to_remove = []
    for key in st.session_state.keys():
        if key.startswith(("checked_", "result_", "shuffled_choices_")):
            keys_to_remove.append(key)
    
    for key in keys_to_remove:
        st.session_state.pop(key, None)
    
    st.success("🔄 セッションをリセットしました")
    st.rerun()


def render_practice_sidebar():
    """練習ページ専用のサイドバーを描画"""
    
    # サイドバー更新フラグをチェック
    if st.session_state.get("sidebar_refresh_needed", False):
        st.session_state["sidebar_refresh_needed"] = False
        # フラグをクリアした後、少し待ってから処理を続行
        import time
        time.sleep(0.1)
    
    try:
        uid = st.session_state.get("uid")
        if not uid:
            st.warning("ユーザーIDが見つかりません")
            return
            
        # --- 演習ページのサイドバー ---
        st.markdown("### 🎓 学習ハブ")

        # 学習モード選択
        learning_mode = st.radio(
            "学習モード",
            ['おまかせ学習（推奨）', '自由演習（分野・回数指定）'],
            key="learning_mode"
        )

        st.divider()

        if learning_mode == 'おまかせ学習（推奨）':
            # 学習セッション初期化中の場合の処理
            if st.session_state.get("initializing_study", False):
                st.markdown("#### 📅 本日の学習目標")
                st.info("🔄 学習セッションを準備中...")
                # 初期化中は他の表示を全て停止
                st.stop()
            else:
                # Anki風の日次目標表示 + SM-2ベース復習スケジュール
                st.markdown("#### 📅 本日の学習目標・復習スケジュール")
                from modules.search_page import get_japan_today
                today = get_japan_today()  # 日本時間の今日
                cards = st.session_state.get("cards", {})

                # SM-2アルゴリズムベースの復習スケジュール計算
                from modules.search_page import calculate_sm2_review_schedule, get_review_priority_cards
                
                # 7日分の復習スケジュールを計算
                review_schedule = calculate_sm2_review_schedule(cards, days_ahead=7)
                
                # 今日の復習対象カードを優先度付きで取得
                today_priority_cards = get_review_priority_cards(cards, today)
                review_count = len(today_priority_cards)
                
                # 今日の復習統計
                overdue_cards = [card for card in today_priority_cards if card[2] > 0]  # 経過日数 > 0
                due_today_cards = [card for card in today_priority_cards if card[2] == 0]  # 今日が復習予定日

                # 今日の復習情報のみ表示（シンプル・前向き）
                col1, col2 = st.columns(2)
                
                with col1:
                    st.metric(
                        label="今日の復習",
                        value=f"{review_count}問",
                        delta=f"期限切れ: {len(overdue_cards)}問" if overdue_cards else "すべて期限内 ✅",
                        help=f"期限切れ: {len(overdue_cards)}問 / 今日予定: {len(due_today_cards)}問"
                    )
                
                with col2:
                    # 新規学習目標
                    new_target = st.session_state.get("new_cards_per_day", 10)
                    st.metric(
                        label="新規学習目標",
                        value=f"{new_target}問",
                        help="今日の新規学習目標数"
                    )

                # 復習詳細（シンプル表示）
                if review_count > 0 and overdue_cards:
                    st.warning(f"⚠️ 期限切れの復習問題が {len(overdue_cards)}問 あります。優先的に学習することをお勧めします。")

                # 本日の学習完了数を計算（重複カウント防止強化版）
                today_reviews_done = 0
                today_new_done = 0
                processed_cards = set()  # 重複カウント防止
                

                try:
                    for q_num, card in cards.items():
                        if not isinstance(card, dict) or q_num in processed_cards:
                            continue

                        history = card.get('history', [])
                        if not history:
                            continue

                        # 本日の学習履歴があるかチェック（日本時間ベース）
                        has_today_session = False
                        for review in history:
                            if isinstance(review, dict):
                                review_timestamp = review.get('timestamp', '')
                                review_date_obj = None
                                
                                # タイムスタンプのパース処理（日本時間変換）
                                try:
                                    review_datetime_jst = get_japan_datetime_from_timestamp(review_timestamp)
                                    review_date_obj = review_datetime_jst.date()
                                except Exception:
                                    continue
                                
                                if review_date_obj == today:
                                    has_today_session = True
                                    break

                        if has_today_session:
                            processed_cards.add(q_num)  # 処理済みマーク

                            # 今日より前に学習記録があるかどうかで新規/復習を判定（日本時間ベース）
                            has_previous_learning = False
                            
                            for review in history:
                                if isinstance(review, dict):
                                    timestamp = review.get('timestamp', '')
                                    
                                    try:
                                        review_datetime_jst = get_japan_datetime_from_timestamp(timestamp)
                                        review_date_obj = review_datetime_jst.date()
                                        
                                        # 今日より前の学習記録があるかチェック
                                        if review_date_obj and review_date_obj < today:
                                            has_previous_learning = True
                                            break
                                    except Exception:
                                        continue

                            if has_previous_learning:
                                # 過去に学習記録があるので復習
                                today_reviews_done += 1
                            else:
                                # 今日が初回学習なので新規
                                today_new_done += 1
                                
                                
                except Exception as e:
                    # エラーが発生した場合は0で初期化
                    today_reviews_done = 0
                    today_new_done = 0

                # result_logからも本日のデータを取得（補完用）
                result_log = st.session_state.get("result_log", {})
                
                for q_id, result_data in result_log.items():
                    if q_id in processed_cards:
                        continue  # 既にhistoryでカウント済み
                        
                    timestamp = result_data.get('timestamp', '')
                    if isinstance(timestamp, str):
                        try:
                            result_date = datetime.datetime.fromisoformat(timestamp.replace('Z', '+00:00')).date()
                            if result_date == today:
                                # result_logでは全て新規として扱う（自己評価時のログなので）
                                today_new_done += 1
                                processed_cards.add(q_id)
                        except:
                            pass
                

                # 新規学習目標数（安全な取得）
                new_target = st.session_state.get("new_cards_per_day", 10)
                if not isinstance(new_target, int):
                    new_target = 10

                # 残り目標数を計算（安全な値チェック付き）
                review_remaining = max(0, review_count - today_reviews_done) if isinstance(review_count, int) and isinstance(today_reviews_done, int) else 0
                new_remaining = max(0, new_target - today_new_done) if isinstance(new_target, int) and isinstance(today_new_done, int) else 0

                # 本日の進捗サマリー
                total_done = today_reviews_done + today_new_done
                daily_goal = review_count + new_target
                progress_rate = min(100, (total_done / daily_goal * 100)) if daily_goal > 0 else 0

                # メイン進捗表示（縦並び）
                st.metric(
                    label="本日の学習",
                    value=f"{total_done}枚",
                    help=f"目標: {daily_goal}枚 (達成率: {progress_rate:.0f}%)"
                )

                if total_done >= daily_goal:
                    st.metric(
                        label="達成率",
                        value="100%",
                        help="目標達成おめでとうございます！"
                    )
                else:
                    st.metric(
                        label="達成率",
                        value=f"{progress_rate:.0f}%",
                        help=f"あと{daily_goal - total_done}枚で目標達成"
                    )

                remaining_total = review_remaining + new_remaining
                if remaining_total > 0:
                    st.metric(
                        label="残り目標",
                        value=f"{remaining_total}枚",
                        help="本日の残り学習目標数"
                    )
                else:
                    st.metric(
                        label="✅ 完了",
                        value="目標達成",
                        help="本日の学習目標をすべて達成しました"
                    )

                st.markdown("---")

                # 詳細進捗表示（縦並び）
                if review_remaining > 0:
                    st.metric(
                        label="復習",
                        value=f"{review_remaining}枚",
                        help=f"復習対象: {review_count}枚 / 完了: {today_reviews_done}枚"
                    )
                else:
                    st.metric(
                        label="復習",
                        value="完了 ✅",
                        help=f"本日の復習: {today_reviews_done}枚完了"
                    )

                if new_remaining > 0:
                    st.metric(
                        label="新規",
                        value=f"{new_remaining}枚",
                        help=f"新規目標: {new_target}枚 / 完了: {today_new_done}枚"
                    )
                else:
                    st.metric(
                        label="新規",
                        value="完了 ✅",
                        help=f"本日の新規学習: {today_new_done}枚完了"
                    )

                # 学習開始ボタン
                if st.button("🚀 今日の学習を開始する", type="primary", key="start_today_study"):
                    # 学習開始中フラグを設定
                    st.session_state["initializing_study"] = True
                    # 復習セッションフラグを設定（復習問題の状態をリセットするため）
                    st.session_state["is_review_session"] = True

                    with st.spinner("学習セッションを準備中..."):
                        # SM-2アルゴリズムベースの復習カード選択
                        grouped_queue = []
                        
                        # 今日の復習対象カードを優先度順で取得
                        priority_cards = get_review_priority_cards(cards, today)
                        
                        
                        # 復習カードを優先度順で追加（最大100問まで）
                        for q_id, priority_score, days_overdue in priority_cards[:100]:
                            grouped_queue.append([q_id])

                        # 新規カードの追加
                        recent_ids = list(st.session_state.get("result_log", {}).keys())[-15:]
                        uid = st.session_state.get("uid")
                        
                        # Firestoreに直接問い合わせるのではなく、セッション状態から権限情報を取得する
                        has_gakushi_permission = st.session_state.get('has_gakushi_permission', False)
                        
                        if has_gakushi_permission:
                            available_questions = ALL_QUESTIONS.copy()
                        else:
                            available_questions = [q for q in ALL_QUESTIONS if not q.get("number", "").startswith("G")]
                        
                        # 利用可能な問題を事前にシャッフル（より完全なランダム性を確保）
                        import random
                        random.shuffle(available_questions)

                        pick_ids = CardSelectionUtils.pick_new_cards_for_today(
                            available_questions,
                            st.session_state.get("cards", {}),
                            N=new_target,
                            recent_qids=recent_ids
                        )

                        for qid in pick_ids:
                            grouped_queue.append([qid])
                            if qid not in st.session_state.cards:
                                st.session_state.cards[qid] = {}

                        # 復習問題と新規問題を混合してシャッフル（完全ランダム出題順序）
                        import random
                        random.shuffle(grouped_queue)

                        if grouped_queue:
                            st.session_state.main_queue = grouped_queue
                            st.session_state.short_term_review_queue = []
                            
                            # セッション開始フラグを設定
                            st.session_state["session_choice_made"] = True
                            st.session_state["session_type"] = "おまかせ学習"
                            
                            # 最初の問題グループを設定
                            if grouped_queue:
                                st.session_state["current_q_group"] = grouped_queue[0]
                                st.session_state["current_question_index"] = 0
                                # main_queueから最初のグループを削除
                                st.session_state["main_queue"] = grouped_queue[1:]

                            # 一時状態をクリア
                            for k in list(st.session_state.keys()):
                                if k.startswith(("checked_", "user_selection_", "shuffled_", "free_input_", "order_input_")):
                                    del st.session_state[k]

                            if save_user_data:
                                print(f"💾 学習セッション状態を保存中...")
                                save_user_data(st.session_state.get("uid"), st.session_state)
                                print(f"✅ セッション状態保存完了")
                            else:
                                print(f"❌ save_user_data関数が利用できません（セッション保存）")
                            st.session_state["initializing_study"] = False
                            st.success(f"今日の学習を開始します！（{len(grouped_queue)}問）")
                            st.rerun()
                        else:
                            st.session_state["initializing_study"] = False
                            st.info("今日の学習対象がありません。")

        else:
            # 自由演習モードのUI
            st.markdown("#### 🎯 自由演習設定")

            # 以前の選択UIを復活
            uid = st.session_state.get("uid")
            has_gakushi_permission = st.session_state.get('has_gakushi_permission', False)
            mode_choices = ["回数別", "科目別", "必修問題のみ", "キーワード検索"]
            mode = st.radio("出題形式を選択", mode_choices, key="free_mode_radio")

            # 対象（国試/学士）セレクタ
            if has_gakushi_permission:
                target_exam = st.radio("対象", ["国試", "学士"], key="free_target_exam", horizontal=True)
            else:
                target_exam = "国試"

            questions_to_load = []

            if mode == "回数別":
                if target_exam == "国試":
                    selected_exam_num = st.selectbox("回数", ALL_EXAM_NUMBERS, key="free_exam_num")
                    if selected_exam_num:
                        available_sections = sorted([s[-1] for s in ALL_EXAM_SESSIONS if s.startswith(selected_exam_num)])
                        selected_section_char = st.selectbox("領域", available_sections, key="free_section")
                        if selected_section_char:
                            selected_session = f"{selected_exam_num}{selected_section_char}"
                            questions_to_load = [q for q in ALL_QUESTIONS if q.get("number", "").startswith(selected_session)]
                else:
                    g_years, g_sessions_map, g_areas_map, _ = QuestionUtils.build_gakushi_indices(ALL_QUESTIONS)
                    if g_years:
                        g_year = st.selectbox("年度", g_years, key="free_g_year")
                        if g_year:
                            sessions = g_sessions_map.get(g_year, [])
                            if sessions:
                                g_session = st.selectbox("回数", sessions, key="free_g_session")
                                if g_session:
                                    areas = g_areas_map.get(g_year, {}).get(g_session, ["A", "B", "C", "D"])
                                    g_area = st.selectbox("領域", areas, key="free_g_area")
                                    if g_area:
                                        questions_to_load = QuestionUtils.filter_gakushi_by_year_session_area(ALL_QUESTIONS, g_year, g_session, g_area)

            elif mode == "科目別":
                if target_exam == "国試":
                    KISO_SUBJECTS = ["解剖学", "歯科理工学", "組織学", "生理学", "病理学", "薬理学", "微生物学・免疫学", "衛生学", "発生学・加齢老年学", "生化学"]
                    RINSHOU_SUBJECTS = ["保存修復学", "歯周病学", "歯内治療学", "クラウンブリッジ学", "部分床義歯学", "全部床義歯学", "インプラント学", "口腔外科学", "歯科放射線学", "歯科麻酔学", "矯正歯科学", "小児歯科学"]
                    group = st.radio("科目グループ", ["基礎系科目", "臨床系科目"], key="free_subject_group")
                    subjects_to_display = KISO_SUBJECTS if group == "基礎系科目" else RINSHOU_SUBJECTS
                    available_subjects = [s for s in ALL_SUBJECTS if s in subjects_to_display]
                    selected_subject = st.selectbox("科目", available_subjects, key="free_subject")
                    if selected_subject:
                        questions_to_load = [q for q in ALL_QUESTIONS if q.get("subject") == selected_subject and not str(q.get("number","")).startswith("G")]
                else:
                    GAKUSHI_KISO_SUBJECTS = ["倫理学", "化学", "歯科理工学", "生理学", "法医学教室", "口腔病理学", "薬理学", "生物学", "口腔衛生学", "口腔解剖学", "生化学", "物理学", "解剖学", "細菌学"]
                    GAKUSHI_RINSHOU_SUBJECTS = ["内科学", "歯周病学", "口腔治療学", "有歯補綴咬合学", "欠損歯列補綴咬合学", "歯科保存学", "口腔インプラント", "口腔外科学1", "口腔外科学2", "歯科放射線学", "歯科麻酔学", "歯科矯正学", "障がい者歯科", "高齢者歯科学", "小児歯科学"]
                    group = st.radio("科目グループ", ["基礎系科目", "臨床系科目"], key="free_gakushi_subject_group")
                    subjects_to_display = GAKUSHI_KISO_SUBJECTS if group == "基礎系科目" else GAKUSHI_RINSHOU_SUBJECTS
                    _, _, _, g_subjects = QuestionUtils.build_gakushi_indices(ALL_QUESTIONS)
                    available_subjects = [s for s in g_subjects if s in subjects_to_display]
                    selected_subject = st.selectbox("科目", available_subjects, key="free_g_subject")
                    if selected_subject:
                        questions_to_load = [q for q in ALL_QUESTIONS if str(q.get("number","")).startswith("G") and (q.get("subject") == selected_subject)]

            elif mode == "必修問題のみ":
                if target_exam == "国試":
                    questions_to_load = [q for q in ALL_QUESTIONS if q.get("number") in HISSHU_Q_NUMBERS_SET]
                else:
                    questions_to_load = [q for q in ALL_QUESTIONS if q.get("number") in GAKUSHI_HISSHU_Q_NUMBERS_SET]

            elif mode == "キーワード検索":
                search_keyword = st.text_input("キーワード", placeholder="例: インプラント、根管治療", key="free_keyword")
                if search_keyword.strip():
                    keyword = search_keyword.strip().lower()
                    search_results = []
                    
                    for question in ALL_QUESTIONS:
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
                    
                    questions_to_load = search_results if search_results else []

            # 出題順
            order_mode = st.selectbox("出題順", ["順番通り", "シャッフル"], key="free_order")
            if order_mode == "シャッフル" and questions_to_load:
                import random
                questions_to_load = questions_to_load.copy()
                random.shuffle(questions_to_load)
            elif questions_to_load:
                try:
                    questions_to_load = sorted(questions_to_load, key=get_natural_sort_key)
                except Exception:
                    pass

            # 学習開始ボタン
            if st.button("🎯 この条件で演習を開始", type="primary", key="start_free_study"):
                if not questions_to_load:
                    st.warning("該当する問題がありません。")
                else:
                    # 権限フィルタリング
                    filtered_questions = []
                    for q in questions_to_load:
                        question_number = q.get('number', '')
                        if question_number.startswith("G") and not has_gakushi_permission:
                            continue
                        filtered_questions.append(q)

                    if not filtered_questions:
                        st.warning("権限のある問題が見つかりませんでした。")
                    else:
                        # グループ化
                        grouped_queue = []
                        processed_q_nums = set()
                        for q in filtered_questions:
                            q_num = str(q['number'])
                            if q_num in processed_q_nums:
                                continue
                            case_id = q.get('case_id')
                            if case_id and case_id in CASES:
                                siblings = sorted([str(sq['number']) for sq in ALL_QUESTIONS if sq.get('case_id') == case_id])
                                if siblings not in grouped_queue:
                                    grouped_queue.append(siblings)
                                processed_q_nums.update(siblings)
                            else:
                                grouped_queue.append([q_num])
                                processed_q_nums.add(q_num)

                        st.session_state.main_queue = grouped_queue
                        st.session_state.short_term_review_queue = []
                        
                        # セッション開始フラグを設定
                        st.session_state["session_choice_made"] = True
                        st.session_state["session_type"] = "自由演習"
                        # 自由演習は復習セッションではないのでフラグをクリア
                        st.session_state.pop("is_review_session", None)
                        
                        # 最初の問題グループを設定
                        if grouped_queue:
                            st.session_state["current_q_group"] = grouped_queue[0]
                            st.session_state["current_question_index"] = 0
                            # main_queueから最初のグループを削除
                            st.session_state["main_queue"] = grouped_queue[1:]
                        else:
                            st.session_state["current_q_group"] = []

                        # カード初期化
                        if "cards" not in st.session_state:
                            st.session_state.cards = {}
                        for q in filtered_questions:
                            if q['number'] not in st.session_state.cards:
                                st.session_state.cards[q['number']] = {}

                        # 一時状態クリア
                        for key in list(st.session_state.keys()):
                            if key.startswith(("checked_", "user_selection_", "shuffled_", "free_input_", "order_input_")):
                                del st.session_state[key]

                        if save_user_data:
                            print(f"💾 自由演習セッション状態を保存中...")
                            save_user_data(st.session_state.get("uid"), st.session_state)
                            print(f"✅ 自由演習セッション状態保存完了")
                        else:
                            print(f"❌ save_user_data関数が利用できません（自由演習）")
                        st.success(f"演習を開始します！（{len(grouped_queue)}グループ）")
                        st.rerun()

        # 現在の学習キュー状況表示 + SM-2復習スケジュール
        st.divider()
        st.markdown("#### 📚 学習キュー状況・復習スケジュール")

        # 短期復習の「準備完了」件数を表示（日本時間ベース）
        now_jst = get_japan_now()
        ready_short = 0
        for item in st.session_state.get("short_term_review_queue", []):
            ra = item.get("ready_at")
            if isinstance(ra, str):
                try:
                    ra = datetime.datetime.fromisoformat(ra)
                except Exception:
                    ra = now_jst
            if not ra or ra <= now_jst:
                ready_short += 1

        st.write(f"メインキュー: **{len(st.session_state.get('main_queue', []))}** グループ")
        st.write(f"短期復習: **{ready_short}** グループ準備完了")

        # SM-2復習状況（今日のみ表示、日本時間ベース）
        try:
            cards = st.session_state.get("cards", {})
            from modules.search_page import get_review_priority_cards, get_japan_today
            
            # 今日の復習状況のみ表示（日本時間）
            today = get_japan_today()
            today_priority_cards = get_review_priority_cards(cards, today)
            today_count = len(today_priority_cards)
            overdue_count = len([card for card in today_priority_cards if card[2] > 0])
            
            if today_count > 0:
                st.markdown("**📅 今日の復習:**")
                if overdue_count > 0:
                    st.write(f"復習: {today_count}問 (期限切れ: {overdue_count}問)")
                else:
                    st.write(f"復習: {today_count}問")
        
        except Exception as e:
            pass

        # セッション初期化
        if st.button("🔄 セッションを初期化", key="reset_session"):
            st.session_state.current_q_group = []
            for k in list(st.session_state.keys()):
                if k.startswith(("checked_", "user_selection_", "shuffled_", "free_input_", "order_input_")):
                    del st.session_state[k]
            st.info("セッションを初期化しました")
            st.rerun()
            
    except Exception as e:
        st.error(f"学習ハブでエラーが発生しました: {str(e)}")
        st.exception(e)


def _render_auto_learning_mode():
    """🚀 2. 「おまかせ学習」モードのUI（シンプル版）"""
    
    # cardsの初期化（安全のため最初に実行）
    cards = {}
    
    try:
        st.markdown("### おまかせ学習")
        
        uid = st.session_state.get("uid")
        if not uid:
            st.warning("ユーザーIDが見つかりません")
            return
        
        # Firestoreから個人の学習データを取得（最初に実行）
        if get_firestore_manager:
            firestore_manager = get_firestore_manager()
        else:
            firestore_manager = None
        cards = {}
        
        try:
            # 1. セッション状態のカードデータを最優先で使用
            session_cards = st.session_state.get("cards", {})
            
            # 2. セッション状態にデータがない、または空の場合はFirestoreから強制取得
            if not session_cards or len(session_cards) == 0:
                
                if firestore_manager and firestore_manager.db:
                    # Firestoreから直接study_cardsを取得
                    study_cards_ref = firestore_manager.db.collection("study_cards")
                    user_cards_query = study_cards_ref.where("uid", "==", uid)
                    user_cards_docs = list(user_cards_query.stream())
                    
                    
                    # カードデータを変換
                    for doc in user_cards_docs:
                        try:
                            card_data = doc.to_dict()
                            question_id = doc.id.split('_')[-1] if '_' in doc.id else doc.id
                            
                            # 既存の形式に変換
                            card = {
                                "q_id": question_id,
                                "uid": card_data.get("uid", uid),
                                "history": card_data.get("history", []),
                                "sm2_data": card_data.get("sm2_data", {}),
                                "performance": card_data.get("performance", {}),
                                "metadata": card_data.get("metadata", {})
                            }
                            
                            # SM2データから既存の形式に変換
                            sm2_data = card_data.get("sm2_data", {})
                            if sm2_data:
                                card.update({
                                    "n": sm2_data.get("n", 0),
                                    "EF": sm2_data.get("ef", 2.5),
                                    "interval": sm2_data.get("interval", 1),
                                    "next_review": sm2_data.get("next_review"),
                                    "last_review": sm2_data.get("last_review")
                                })
                            
                            cards[question_id] = card
                            
                        except Exception as card_error:
                            print(f"[WARNING] カードデータ処理エラー ({doc.id}): {card_error}")
                            continue
                    
                    # セッション状態にも保存
                    st.session_state["cards"] = cards
                else:
                    print(f"[ERROR] Firestoreマネージャーまたはdbが無効")
                    cards = {}
            else:
                # セッション状態のデータをそのまま使用
                cards = session_cards
            
            # デバッグ情報を追加
            print(f"  - セッションカード数: {len(session_cards)}")
            print(f"  - 使用中カード数: {len(cards)}")
            print(f"  - データソース: {'セッション状態' if session_cards else 'Firestore直接取得'}")
            
        except Exception as e:
            print(f"[ERROR] 学習データ取得エラー: {str(e)}")
            st.warning(f"学習データの取得に失敗: {str(e)}")
            cards = st.session_state.get("cards", {})

        # UserDataExtractorを使用した詳細分析（最適化版・デプロイ対応強化）
        detailed_stats = None
        
        # 統計計算をスキップする条件をチェック（パフォーマンス最適化）
        last_skip_time = st.session_state.get("last_skip_time", 0)
        current_time = time.time()
        skip_recently = (current_time - last_skip_time) < 2.0  # 2秒以内のスキップは統計計算をスキップ
        
        # ログイン直後の初回表示時もスキップ（必要な時のみ計算）
        is_initial_load = not st.session_state.get("stats_calculated", False)
        
        if is_initial_load:
            pass
        
        if skip_recently:
            pass
        
        should_skip_stats = skip_recently or is_initial_load
        
        if cards and len(cards) > 0 and not should_skip_stats:
            try:
                
                # Streamlit Cloud対応：データが存在する場合のみUserDataExtractorを使用
                extractor = UserDataExtractor()
                
                # 直接統計を計算（キャッシュではなく現在のカードデータから）
                try:
                    user_stats = extractor.get_user_comprehensive_stats(uid)
                    if user_stats and isinstance(user_stats, dict):
                        detailed_stats = user_stats
                        # 統計をキャッシュに保存（スキップ時の高速化のため）
                        st.session_state["cached_detailed_stats"] = detailed_stats
                        # 統計計算完了フラグを設定
                        st.session_state["stats_calculated"] = True
                        
                        # 重要な統計データが存在するか確認
                        if 'level_distribution' in detailed_stats and detailed_stats['level_distribution']:
                            pass
                        else:
                            detailed_stats = None
                    else:
                        detailed_stats = None
                except Exception as ude_error:
                    print(f"[ERROR] UserDataExtractor直接計算エラー: {ude_error}")
                    detailed_stats = None
                    
            except Exception as e:
                print(f"[ERROR] UserDataExtractor全体エラー: {e}")
                detailed_stats = None
        else:
            if not cards or len(cards) == 0:
                pass
            if skip_recently:
                # スキップ時はキャッシュされた統計を使用
                detailed_stats = st.session_state.get("cached_detailed_stats", None)
            elif is_initial_load:
                # 初回ロード時もキャッシュを使用（統計計算を遅延）
                detailed_stats = st.session_state.get("cached_detailed_stats", None)
            else:
                detailed_stats = None

        new_cards_per_day = st.session_state.get("new_cards_per_day", 10)
        
        # リアルタイム計算 - UserDataExtractorが利用可能なら優先使用（Streamlit Cloud対応）
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        
        if len(cards) == 0:
            # カードデータが存在しない場合のデフォルト値
            review_count = 0
            new_count = 0
            completed_count = 0
        else:
            # UserDataExtractorから統計を計算
            detailed_stats = None
            try:
                extractor = UserDataExtractor()
                user_stats = extractor.get_user_comprehensive_stats(uid)
                if user_stats and isinstance(user_stats, dict) and user_stats.get('level_distribution'):
                    detailed_stats = user_stats
                    
                    # UserDataExtractorから統計を計算
                    level_distribution = detailed_stats.get("level_distribution", {})
                    
                    # 復習期限カード数の計算（レベル0-5）
                    review_count = 0
                    for level, count in level_distribution.items():
                        if level in ['レベル0', 'レベル1', 'レベル2', 'レベル3', 'レベル4', 'レベル5']:
                            review_count += count
                    
                    # 新規カード数の計算（未学習カード、上限制限）
                    new_count = min(level_distribution.get("未学習", 0), new_cards_per_day)
                    
                    # 今日の学習数
                    completed_count = detailed_stats.get("今日の学習数", 0)
                    
                    print(f"  - 復習期限: {review_count}問 (レベル0-5の合計)")
                    print(f"  - 新規カード: {new_count}問 (未学習カード)")
                    print(f"  - 今日完了: {completed_count}問")
                    
                else:
                    detailed_stats = None
                    review_count, new_count, completed_count = _calculate_legacy_stats_full(cards, today, new_cards_per_day)
                    
            except Exception as e:
                print(f"[ERROR] UserDataExtractor全体エラー: {e}")
                detailed_stats = None
                review_count, new_count, completed_count = _calculate_legacy_stats_full(cards, today, new_cards_per_day)
        # 学習状況を簡潔に表示
        col1, col2 = st.columns(2)
        with col1:
            st.metric("復習予定", f"{review_count}問")
            st.metric("新規予定", f"{new_count}問")
        with col2:
            st.metric("今日の学習", f"{completed_count}問")
            total_target = review_count + new_count
            if total_target > 0:
                progress = min(completed_count / total_target, 1.0)
                st.metric("進捗", f"{progress:.1%}")
            else:
                st.metric("進捗", "0.0%")
        
        # AI自動判定（バックグラウンド処理 - ユーザーには詳細を表示しない）
        optimal_mode, reasoning = _determine_optimal_learning_mode(detailed_stats, review_count, new_count, completed_count)
        
        # 学習セッション設定
        st.markdown("#### 学習セッション設定")
        
        session_length = st.selectbox(
            "学習時間を選択",
            ["10分（約5問）", "20分（約10問）", "30分（約15問）", "カスタム"],
            index=1,
            help="AIが最適な問題を自動選択して出題します",
            label_visibility="collapsed"
        )
        
        if session_length == "カスタム":
            custom_count = st.number_input("問題数", min_value=1, max_value=50, value=10)
        else:
            custom_count = int(session_length.split("約")[1].split("問")[0])
        
        # 学習開始ボタン
        if st.button("今日の学習を開始する", type="primary", use_container_width=True):
            _start_ai_enhanced_learning(optimal_mode, custom_count, detailed_stats)
            
    except Exception as e:
        st.error(f"おまかせ学習モードでエラー: {str(e)}")
        st.exception(e)


def _render_free_learning_mode(has_gakushi_permission: bool):
    """🎯 3. 「自由演習」モードのUI"""
    try:
        st.markdown("### ⚙️ 演習条件設定")
        
        # 対象試験の選択
        if has_gakushi_permission:
            target_exam = st.radio(
                "対象試験",
                ["国試", "学士試験"],
                key="free_target_exam"
            )
        else:
            # 権限がない場合は選択肢を表示せず、自動的に国試に設定
            target_exam = "国試"
            st.markdown("**対象試験**: 国試")
        
        # 出題形式の選択
        quiz_format = st.radio(
            "出題形式",
            ["回数別", "科目別", "必修問題のみ", "キーワード検索"],
            key="free_quiz_format"
        )
        
        # 詳細条件の選択（動的UI）
        _render_detailed_conditions(quiz_format, target_exam)
        
        # 出題順の選択
        question_order = st.selectbox(
            "出題順",
            ["順番通り", "シャッフル"],
            key="free_question_order"
        )
        
        # 演習開始ボタン
        if st.button("🎯 この条件で演習を開始", type="primary", use_container_width=True):
            # デバッグ情報表示
            st.info(f"選択条件: {quiz_format}, {target_exam}, {question_order}")
            _start_free_learning(quiz_format, target_exam, question_order)
            
    except Exception as e:
        st.error(f"自由演習モードでエラー: {str(e)}")
        st.exception(e)


def _render_detailed_conditions(quiz_format: str, target_exam: str):
    """詳細条件の動的UI表示"""
    if quiz_format == "回数別":
        if target_exam == "国試":
            # 国試の回数選択（現実的な範囲）
            kaisu_options = [f"{i}回" for i in range(95, 119)]  # 95回〜118回
            selected_kaisu = st.selectbox("国試回数", kaisu_options, 
                                        index=len(kaisu_options)-1, key="free_kaisu")
            
            # 領域選択
            area_options = ["全領域", "A領域", "B領域", "C領域", "D領域"]
            selected_area = st.selectbox("領域", area_options, key="free_area")
        else:
            # 学士試験の年度・回数選択
            year_options = [f"{y}年度" for y in range(2022, 2026)]  # 2022-2025年度
            selected_year = st.selectbox("年度", year_options, 
                                       index=len(year_options)-1, key="free_gakushi_year")
            
            # 回数選択（実際のデータに基づく：1-1, 1-2, 1-3, 1再, 2, 2再）
            kaisu_options = ["1-1", "1-2", "1-3", "1再", "2", "2再"]
            selected_kaisu = st.selectbox("回数", kaisu_options, key="free_gakushi_kaisu")
            
            area_options = ["全領域", "A領域", "B領域"]
            selected_area = st.selectbox("領域", area_options, key="free_gakushi_area")
    
    elif quiz_format == "科目別":
        # 科目選択（実際のJSONデータから科目を取得）
        uid = st.session_state.get("uid")
        has_gakushi_permission = st.session_state.get('has_gakushi_permission', False)
        analysis_target = st.session_state.get("analysis_target", "国試問題")
        
        # 実際のJSONデータから科目を取得
        try:
            from utils import ALL_QUESTIONS
            
            kokushi_subjects = set()
            gakushi_subjects = set()
            
            for q in ALL_QUESTIONS:
                subject = q.get('subject', '')
                number = q.get('number', '')
                
                if not subject or subject == '（未分類）':
                    continue
                
                # 国試問題か学士試験問題かを判定
                if number.startswith('G'):
                    gakushi_subjects.add(subject)
                else:
                    kokushi_subjects.add(subject)
            
            # 対象試験に応じて科目を選択
            if target_exam == "学士試験" and has_gakushi_permission:
                subject_options = sorted(list(gakushi_subjects))
            else:  # target_exam == "国試" または権限なし
                subject_options = sorted(list(kokushi_subjects))
            
            if not subject_options:
                subject_options = ["一般"]
                
        except Exception as e:
            st.error(f"科目データの取得中にエラーが発生しました: {e}")
            subject_options = ["一般"]
        
        selected_subject = st.selectbox("科目", subject_options, key="free_subject")
    
    elif quiz_format == "キーワード検索":
        keyword = st.text_input(
            "検索キーワード",
            placeholder="例：根管治療、インプラント、咬合",
            key="free_keyword",
            help="問題文に含まれるキーワードで検索します"
        )


def _render_session_status():
    """📋 4. 共通のUI要素 - セッション状態表示"""
    st.divider()
    st.markdown("### 📋 セッション状況")
    
    # 学習キュー状況
    main_queue = st.session_state.get("main_queue", [])
    short_review_queue = st.session_state.get("short_review_queue", [])
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("メインキュー", f"{len(main_queue)}問")
    with col2:
        st.metric("短期復習", f"{len(short_review_queue)}問")
    
    # 学習記録セクション
    st.divider()
    st.markdown("#### 📈 学習記録")
    if st.session_state.cards and len(st.session_state.cards) > 0:
        from collections import Counter
        import datetime
        
        quality_to_mark = {1: "×", 2: "△", 4: "◯", 5: "◎"}
        mark_to_label = {"◎": "簡単", "◯": "普通", "△": "難しい", "×": "もう一度"}
        
        # 安全に評価データを取得
        evaluated_marks = []
        for card in st.session_state.cards.values():
            if isinstance(card, dict):
                # qualityフィールドから直接取得
                quality = card.get('quality')
                if quality and quality in quality_to_mark:
                    evaluated_marks.append(quality_to_mark[quality])
                # historyから最新の評価を取得（qualityがない場合）
                elif not quality and card.get('history'):
                    history = card.get('history', [])
                    if isinstance(history, list) and len(history) > 0:
                        last_entry = history[-1]
                        if isinstance(last_entry, dict):
                            hist_quality = last_entry.get('quality')
                            if hist_quality and hist_quality in quality_to_mark:
                                evaluated_marks.append(quality_to_mark[hist_quality])
        
        total_evaluated = len(evaluated_marks)
        counter = Counter(evaluated_marks)

        with st.expander("自己評価の分布", expanded=True):
            if total_evaluated > 0:
                st.markdown(f"**合計評価数：{total_evaluated}問**")
                for mark, label in mark_to_label.items():
                    count = counter.get(mark, 0)
                    percent = int(round(count / total_evaluated * 100)) if total_evaluated else 0
                    st.markdown(f"{mark} {label}：{count}問 ({percent}％)")
            else:
                st.info("まだ評価された問題がありません。")

        with st.expander("最近の評価ログ", expanded=False):
            # cardsデータから履歴があるものを安全に取得
            cards_with_history = []
            for q_num, card in st.session_state.cards.items():
                if isinstance(card, dict) and card.get('history'):
                    history = card['history']
                    if isinstance(history, list) and len(history) > 0:
                        cards_with_history.append((q_num, card))
            
            # タイムスタンプでソート（安全に処理）
            def get_safe_timestamp(item):
                try:
                    q_num, card = item
                    history = card.get('history', [])
                    if history and isinstance(history, list):
                        last_entry = history[-1]
                        if isinstance(last_entry, dict):
                            # timestampがある場合
                            if 'timestamp' in last_entry:
                                ts = last_entry['timestamp']
                                # DatetimeWithNanosecondsオブジェクトをstring化
                                if hasattr(ts, 'isoformat'):
                                    return ts.isoformat()
                                elif isinstance(ts, str):
                                    return ts
                                else:
                                    return str(ts)
                            # dateがある場合
                            elif 'date' in last_entry:
                                ts = last_entry['date']
                                if hasattr(ts, 'isoformat'):
                                    return ts.isoformat()
                                elif isinstance(ts, str):
                                    return ts
                                else:
                                    return str(ts)
                            # その他のタイムスタンプフィールド
                            elif 'time' in last_entry:
                                ts = last_entry['time']
                                if hasattr(ts, 'isoformat'):
                                    return ts.isoformat()
                                elif isinstance(ts, str):
                                    return ts
                                else:
                                    return str(ts)
                    return '1970-01-01T00:00:00'  # デフォルト値
                except Exception as e:
                    return '1970-01-01T00:00:00'  # エラー時のデフォルト値
            
            sorted_cards = sorted(cards_with_history, key=get_safe_timestamp, reverse=True)
            
            if sorted_cards:
                for q_num, card in sorted_cards[:10]:
                    try:
                        last_history = card['history'][-1]
                        
                        # 評価マークを安全に取得
                        quality = last_history.get('quality')
                        last_eval_mark = quality_to_mark.get(quality, "?")
                        
                        # タイムスタンプを安全に取得・フォーマット（日本時間対応）
                        timestamp_str = "未記録"
                        ts_value = last_history.get('timestamp') or last_history.get('date')
                        if ts_value:
                            try:
                                # タイムゾーン変換関数を呼び出す
                                dt_jst = get_japan_datetime_from_timestamp(ts_value)
                                timestamp_str = dt_jst.strftime('%Y-%m-%d %H:%M')
                            except Exception:
                                timestamp_str = "時刻取得エラー"
                        
                        # 元のシンプルなUI形式に戻す
                        jump_btn = st.button(f"{q_num}", key=f"jump_{q_num}")
                        st.markdown(f"- `{q_num}` : **{last_eval_mark}** ({timestamp_str})", unsafe_allow_html=True)
                        
                        # ジャンプ処理
                        if jump_btn:
                            st.session_state.current_q_group = [q_num]
                            for key in list(st.session_state.keys()):
                                if key.startswith("checked_") or key.startswith("user_selection_") or key.startswith("shuffled_") or key.startswith("free_input_"):
                                    del st.session_state[key]
                            st.rerun()
                    except Exception as e:
                        # 個別の履歴エントリでエラーが発生した場合はスキップ
                        continue
            else:
                st.info("履歴のある問題がありません。")
    else:
        st.info("まだ評価された問題がありません。")


def _start_ai_enhanced_learning(session_type: str, problem_count: int, detailed_stats: Optional[Dict] = None):
    """AI強化版おまかせ学習の開始処理"""
    uid = st.session_state.get("uid")
    
    # データの事前チェック
    if not ALL_QUESTIONS:
        st.error("問題データが読み込まれていません。データを初期化しています...")
        try:
            # データ強制リロード
            from utils import load_data
            load_data()
            # モジュールをリロード
            import importlib
            import utils
            importlib.reload(utils)
            from utils import ALL_QUESTIONS as RELOADED_QUESTIONS
            if not RELOADED_QUESTIONS:
                st.error("問題データの読み込みに失敗しました。")
                return
        except Exception as e:
            st.error(f"データ読み込みエラー: {e}")
            return
    
    with st.spinner(f"AI分析中... {session_type}モードで最適な問題を選択しています"):
        try:
            # 詳細統計がある場合は常にローカルAI分析を使用
            if detailed_stats:
                question_ids = _select_questions_by_ai_analysis(
                    uid, session_type, problem_count, detailed_stats
                )
            else:
                # 詳細統計がない場合：簡単なローカル問題選択
                question_ids = _select_questions_simple_fallback(uid, session_type, problem_count)
            
            if question_ids:
                # 問題データを取得
                questions = [q for q in ALL_QUESTIONS if q.get("number") in question_ids]
                
                st.session_state["main_queue"] = [[q.get("number")] for q in questions]
                st.session_state["practice_mode"] = "auto"
                st.session_state["current_session_type"] = session_type
                st.session_state["session_type"] = session_type  # バリデーション用にも設定
                # 新規学習セッションの場合は復習フラグをクリア
                if session_type not in ["復習重視"]:  # 復習重視以外は復習セッションではない
                    st.session_state.pop("is_review_session", None)
                
                # Analytics記録
                log_to_ga("practice_session_start", uid, {
                    "session_type": session_type,
                    "problem_count": len(questions),
                    "ai_enhanced": True
                })
                
                st.success(f"{len(questions)}問のセッションを開始します")
                st.rerun()
            else:
                st.error("問題の選択に失敗しました。しばらく後でお試しください。")
                
        except Exception as e:
            st.error(f"AI学習セッション生成エラー: {str(e)}")
            print(f"[ERROR] AI学習セッション生成エラー: {e}")


def _select_questions_simple_fallback(uid: str, session_type: str, count: int) -> List[str]:
    """詳細統計がない場合のシンプルな問題選択"""
    try:
        if get_firestore_manager:
            firestore_manager = get_firestore_manager()
            user_cards = firestore_manager.get_user_cards(uid)
        else:
            user_cards = {}
        
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        review_questions = []
        new_questions = []
        
        # 復習問題の抽出
        for q_id, card in user_cards.items():
            if q_id in ALL_QUESTIONS_DICT:
                history = card.get("history", [])
                if history:  # 学習済み
                    sm2_data = card.get("sm2", {})
                    due_date = sm2_data.get("due_date")
                    if due_date:
                        try:
                            if hasattr(due_date, 'strftime'):
                                due_date_str = due_date.strftime("%Y-%m-%d")
                            elif isinstance(due_date, str):
                                due_date_str = due_date[:10] if len(due_date) >= 10 else due_date
                            else:
                                due_date_str = str(due_date)[:10]
                            
                            if due_date_str <= today:
                                review_questions.append(q_id)
                        except:
                            continue
        
        # 新規問題の抽出
        for question in ALL_QUESTIONS:
            q_id = str(question.get("number"))
            if q_id not in user_cards or not user_cards[q_id].get("history", []):
                new_questions.append(q_id)
        
        # セッションタイプ別の選択
        if session_type == "復習重視":
            selected = review_questions[:count]
            if len(selected) < count:
                selected.extend(new_questions[:count - len(selected)])
        elif session_type == "新規重視":
            selected = new_questions[:count]
            if len(selected) < count:
                selected.extend(review_questions[:count - len(selected)])
        else:  # バランス学習または弱点強化
            review_count = min(len(review_questions), count // 2)
            new_count = count - review_count
            selected = review_questions[:review_count] + new_questions[:new_count]
        
        random.shuffle(selected)
        return selected[:count]
        
    except Exception as e:
        print(f"[ERROR] シンプル問題選択エラー: {e}")
        # 最後の手段：ランダム選択
        all_question_ids = [str(q.get("number")) for q in ALL_QUESTIONS if q.get("number")]
        random.shuffle(all_question_ids)
        return all_question_ids[:count]


def _select_questions_by_ai_analysis(uid: str, session_type: str, count: int, stats: Dict) -> List[str]:
    """AI分析に基づく問題選択ロジック"""
    try:
        if get_firestore_manager:
            firestore_manager = get_firestore_manager()
            user_cards = firestore_manager.get_user_cards(uid)
        else:
            user_cards = {}
        
        # セッションタイプ別の選択ロジック
        if session_type == "弱点強化":
            # 弱点分野の低レベルカードを優先
            weak_categories = stats.get('weak_categories', [])
            selected_questions = _select_weak_area_questions(user_cards, weak_categories, count)
            
        elif session_type == "復習重視":
            # 期限切れ復習カードを優先
            selected_questions = _select_review_priority_questions(user_cards, count)
            
        elif session_type == "新規重視":
            # 未学習カードを優先
            selected_questions = _select_new_questions(user_cards, count)
            
        else:  # バランス学習
            # バランスよく選択
            selected_questions = _select_balanced_questions(user_cards, stats, count)
        
        return selected_questions[:count]
        
    except Exception as e:
        print(f"AI question selection error: {e}")
        return []


def _select_weak_area_questions(user_cards: Dict, weak_categories: List[str], count: int) -> List[str]:
    """弱点分野の問題を選択"""
    weak_questions = []
    
    for q_id, card in user_cards.items():
        if q_id in ALL_QUESTIONS_DICT:
            question = ALL_QUESTIONS_DICT[q_id]
            category = question.get("category", "")
            
            # 弱点分野かつ習熟度が低い問題を選択
            if any(weak_cat in category for weak_cat in weak_categories):
                level = card.get("level", 0)
                if level < 3:  # レベル3未満を弱点とみなす
                    weak_questions.append(q_id)
    
    # ランダムに並び替えて返す
    random.shuffle(weak_questions)
    return weak_questions


def _select_review_priority_questions(user_cards: Dict, count: int) -> List[str]:
    """復習優先問題を選択"""
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    review_questions = []
    
    for q_id, card in user_cards.items():
        sm2_data = card.get("sm2", {})
        due_date = sm2_data.get("due_date")
        
        if due_date:
            try:
                if hasattr(due_date, 'strftime'):
                    due_date_str = due_date.strftime("%Y-%m-%d")
                elif isinstance(due_date, str):
                    due_date_str = due_date[:10]
                else:
                    due_date_str = str(due_date)[:10]
                
                if due_date_str <= today:
                    review_questions.append(q_id)
            except:
                continue
    
    # 期限の古い順にソート
    review_questions.sort(key=lambda q_id: user_cards[q_id].get("sm2", {}).get("due_date", ""))
    return review_questions


def _select_new_questions(user_cards: Dict, count: int) -> List[str]:
    """新規問題を選択"""
    new_questions = []
    
    # 権限チェックを追加
    uid = st.session_state.get("uid")
    has_gakushi_permission = st.session_state.get('has_gakushi_permission', False)
    
    # 権限に応じて利用可能な問題を制限
    if has_gakushi_permission:
        available_questions = ALL_QUESTIONS
    else:
        available_questions = [q for q in ALL_QUESTIONS if not q.get("number", "").startswith("G")]
    
    # デバッグ: 年代別問題数を確認
    year_counts = {}
    for q in available_questions:
        number = q.get("number", "")
        if number and len(number) >= 3:
            year_prefix = number[:3]  # 例: "100", "101", "118"
            year_counts[year_prefix] = year_counts.get(year_prefix, 0) + 1
    
    
    # 利用可能な問題をシャッフルしてから未学習のものを選択（順序バイアスを排除）
    shuffled_questions = list(available_questions)
    random.shuffle(shuffled_questions)
    
    # デバッグ: 未学習問題の判定を詳しく記録
    learned_count = 0
    unlearned_count = 0
    unlearned_years = {}
    
    for question in shuffled_questions:
        q_id = str(question.get("number"))
        
        # 未学習の条件を修正：cardsに存在しない OR historyが空
        is_unlearned = False
        if q_id not in user_cards:
            is_unlearned = True
        else:
            card = user_cards[q_id]
            if not card.get("history", []) and card.get("n", 0) == 0:
                is_unlearned = True
        
        if is_unlearned:
            new_questions.append(q_id)
            unlearned_count += 1
            
            # 年代別カウント
            if len(q_id) >= 3:
                year_prefix = q_id[:3]
                unlearned_years[year_prefix] = unlearned_years.get(year_prefix, 0) + 1
        else:
            learned_count += 1
            
        # 十分な候補が集まったら早期終了（パフォーマンス向上）
        if len(new_questions) >= count * 5:  # 目標数の5倍で十分
            break
    
    
    # さらにシャッフル（念のため）
    random.shuffle(new_questions)
    
    if new_questions:
        selected_sample = new_questions[:min(10, len(new_questions))]
    
    return new_questions


def _select_balanced_questions(user_cards: Dict, stats: Dict, count: int) -> List[str]:
    """バランスよく問題を選択"""
    # 復習 40%, 弱点 30%, 新規 30% の割合で選択
    review_count = int(count * 0.4)
    weak_count = int(count * 0.3)
    new_count = count - review_count - weak_count
    
    selected = []
    
    # 復習問題
    review_questions = _select_review_priority_questions(user_cards, review_count)
    selected.extend(review_questions[:review_count])
    
    # 弱点問題
    weak_categories = stats.get('weak_categories', [])
    weak_questions = _select_weak_area_questions(user_cards, weak_categories, weak_count)
    selected.extend(weak_questions[:weak_count])
    
    # 新規問題
    new_questions = _select_new_questions(user_cards, new_count)
    selected.extend(new_questions[:new_count])
    
    # 不足分を補完
    if len(selected) < count:
        remaining = count - len(selected)
        all_available = _select_new_questions(user_cards, remaining * 2)
        selected.extend(all_available[:remaining])
    
    random.shuffle(selected)
    return selected


def _start_auto_learning():
    """おまかせ学習の開始処理"""
    uid = st.session_state.get("uid")
    
    # データの事前チェック
    if not ALL_QUESTIONS:
        st.error("問題データが読み込まれていません。データを初期化しています...")
        try:
            # データ強制リロード
            from utils import load_data
            load_data()
            # モジュールをリロード
            import importlib
            import utils
            importlib.reload(utils)
            from utils import ALL_QUESTIONS as RELOADED_QUESTIONS
            if not RELOADED_QUESTIONS:
                st.error("問題データの読み込みに失敗しました。")
                return
        except Exception as e:
            st.error(f"データ読み込みエラー: {e}")
            return
    
    with st.spinner("最適な問題を選択中..."):
        # Cloud Function呼び出し処理（簡略化）
        try:
            from auth import call_cloud_function
            result = call_cloud_function("getDailyQuiz", {
                "uid": uid,
                "target": st.session_state.get("analysis_target", "国試"),
                "new_cards_per_day": st.session_state.get("new_cards_per_day", 10)
            })
            
            if result and "questionIds" in result and len(result["questionIds"]) > 0:
                # Cloud Functionから問題リストを取得
                question_ids = result["questionIds"]
                questions = [q for q in ALL_QUESTIONS if q.get("number") in question_ids]
                
                st.session_state["main_queue"] = [[q.get("number")] for q in questions]
                st.session_state["session_mode"] = "auto_learning"
                st.session_state["session_choice_made"] = True
                st.session_state["session_type"] = "おまかせ演習"
                st.session_state["session_start_time"] = time.time()
                
                # 学習セッション開始の追跡
                uid = st.session_state.get("uid")
                if uid:
                    log_to_ga("study_session_start", uid, {
                        "session_type": "auto_learning",
                        "question_count": len(questions),
                        "session_id": f"auto_{int(time.time())}",
                        "learning_mode": "おまかせ演習"
                    })
                
                st.success(f"📚 {len(questions)}問の学習セッションを開始します")
                AnalyticsUtils.track_study_session_start("auto_learning", len(questions))
            else:
                _fallback_auto_learning()
        except Exception as e:
            print(f"Cloud Function error: {e}")
            _fallback_auto_learning()
        
        # 学習画面に遷移
        time.sleep(0.5)
        st.rerun()


def _fallback_auto_learning():
    """フォールバック処理"""
    st.info("ローカル処理で問題を選択します")
    new_cards_per_day = st.session_state.get("new_cards_per_day", 10)
    
    # ランダムに問題を選択
    import random
    uid = st.session_state.get("uid")
    
    # ALL_QUESTIONSが空の場合の対処
    if not ALL_QUESTIONS:
        st.error("問題データが読み込まれていません。データ読み込みを試行します...")
        try:
            # データ強制リロード
            from utils import load_data
            load_data()
            from utils import ALL_QUESTIONS as RELOADED_QUESTIONS
            if not RELOADED_QUESTIONS:
                st.error("問題データの読み込みに失敗しました。管理者にお問い合わせください。")
                return
            available_questions = RELOADED_QUESTIONS
        except Exception as e:
            st.error(f"データ読み込みエラー: {e}")
            return
    else:
        if uid and st.session_state.get('has_gakushi_permission', False):
            available_questions = ALL_QUESTIONS
        else:
            # 学士以外の問題のみ
            available_questions = [q for q in ALL_QUESTIONS if q.get("exam_type") != "学士"]
    
    if not available_questions:
        st.error("利用可能な問題がありません。")
        return
    
    # ユーザーの学習状況を考慮して未学習問題から選択
    user_cards = st.session_state.get("cards", {})
    unlearned_questions = []
    
    for q in available_questions:
        q_id = q.get("number")
        if q_id not in user_cards or (
            not user_cards[q_id].get("history", []) and 
            user_cards[q_id].get("n", 0) == 0
        ):
            unlearned_questions.append(q)
    
    
    # 年代別分布を記録（デバッグ用）
    unlearned_years = {}
    for q in unlearned_questions:
        number = q.get("number", "")
        if number and len(number) >= 3:
            year_prefix = number[:3]
            unlearned_years[year_prefix] = unlearned_years.get(year_prefix, 0) + 1
    
    
    # 未学習問題がない場合は全問題から選択
    if not unlearned_questions:
        unlearned_questions = available_questions
    
    selected_questions = random.sample(unlearned_questions, 
                                     min(new_cards_per_day, len(unlearned_questions)))
    
    # 選択された問題の年代別分布も記録
    selected_years = {}
    for q in selected_questions:
        number = q.get("number", "")
        if number and len(number) >= 3:
            year_prefix = number[:3]
            selected_years[year_prefix] = selected_years.get(year_prefix, 0) + 1
    
    
    # グループ化せずに直接リストとして設定
    st.session_state["main_queue"] = [[q.get("number")] for q in selected_questions]
    st.session_state["session_mode"] = "auto_learning"
    st.session_state["session_choice_made"] = True
    st.session_state["session_type"] = "おまかせ演習"
    st.success(f"📚 {len(selected_questions)}問の学習セッションを開始します")


def _start_free_learning(quiz_format: str, target_exam: str, question_order: str):
    """自由演習の開始処理"""
    uid = st.session_state.get("uid")
    
    # データの事前チェック
    if not ALL_QUESTIONS:
        st.error("問題データが読み込まれていません。データを初期化しています...")
        try:
            # データ強制リロード
            from utils import load_data
            load_data()
            # モジュールをリロード
            import importlib
            import utils
            importlib.reload(utils)
            from utils import ALL_QUESTIONS as RELOADED_QUESTIONS
            if not RELOADED_QUESTIONS:
                st.error("問題データの読み込みに失敗しました。")
                return
        except Exception as e:
            st.error(f"データ読み込みエラー: {e}")
            return
    
    with st.spinner("条件に合う問題を選択中..."):
        try:
            # ユーザー権限の確認
            available_questions = ALL_QUESTIONS
            
            # 権限に応じた問題の絞り込み
            if uid and not st.session_state.get('has_gakushi_permission', False):
                # 権限のないユーザーは国試問題のみ（番号が'G'で始まらない問題）
                available_questions = [q for q in ALL_QUESTIONS if not q.get("number", "").startswith("G")]
            else:
                # 権限のあるユーザーは学士問題にもアクセス可能
                pass
            
            # 対象試験での絞り込み
            if target_exam == "国試":
                # 国試問題：番号が'G'で始まらない問題
                available_questions = [q for q in available_questions if not q.get("number", "").startswith("G")]
            elif target_exam == "学士試験":
                # 学士試験問題：番号が'G'で始まる問題
                available_questions = [q for q in available_questions if q.get("number", "").startswith("G")]
            elif target_exam == "CBT":
                # CBT問題：現在は実装されていないため空リスト
                available_questions = []
            
            # 絞り込み後の問題のexam_typeを確認
            if len(available_questions) == 0 and target_exam == "CBT":
                st.warning("CBT問題は現在データベースに含まれていません。")
            
            # 出題形式での絞り込み
            if quiz_format == "回数別":
                    # 回数別の詳細条件を取得
                    if target_exam == "国試":
                        selected_kaisu = st.session_state.get("free_kaisu", "117回")
                        selected_area = st.session_state.get("free_area", "全領域")
                        
                        # "117回" -> "117" に変換
                        kaisu_number = selected_kaisu.replace("回", "")
                        
                        # 指定回数の問題のみに絞り込み
                        available_questions = [q for q in available_questions 
                                             if q.get("number", "").startswith(f"{kaisu_number}")]
                        
                        # 領域の絞り込み
                        if selected_area != "全領域":
                            area_letter = selected_area.replace("領域", "")  # "A領域" -> "A"
                            available_questions = [q for q in available_questions 
                                                 if area_letter in q.get("number", "")]
                        
                        
                    elif target_exam == "学士試験":
                        selected_year = st.session_state.get("free_gakushi_year", "2025年度")
                        selected_kaisu = st.session_state.get("free_gakushi_kaisu", "1-1")
                        selected_area = st.session_state.get("free_gakushi_area", "全領域")
                        
                        # "2025年度" -> "25" に変換
                        year_number = str(int(selected_year.replace("年度", "")) - 2000)
                        
                        # 学士試験の問題番号形式: G25-1-1-... など
                        available_questions = [q for q in available_questions 
                                             if q.get("number", "").startswith(f"G{year_number}-{selected_kaisu}-")]
                        
                        # 領域の絞り込み
                        if selected_area != "全領域":
                            area_letter = selected_area.replace("領域", "")  # "A領域" -> "A"
                            available_questions = [q for q in available_questions 
                                                 if f"-{area_letter}-" in q.get("number", "")]
                        
            elif quiz_format == "科目別":
                # 科目別の詳細条件を取得（標準化された科目名で比較）
                selected_subject = st.session_state.get("free_subject", "")
                if selected_subject:
                    available_questions = [q for q in available_questions 
                                         if get_standardized_subject(q.get("subject", "")) == selected_subject]
                pass
            elif quiz_format == "必修問題のみ":
                # 必修問題のみ
                if target_exam == "国試":
                    hisshu_numbers = HISSHU_Q_NUMBERS_SET
                    available_questions = [q for q in available_questions if q.get("number") in hisshu_numbers]
                elif target_exam == "学士試験":
                    hisshu_numbers = GAKUSHI_HISSHU_Q_NUMBERS_SET
                    available_questions = [q for q in available_questions if q.get("number") in hisshu_numbers]
            elif quiz_format == "キーワード検索":
                # キーワード検索の詳細条件は後で追加実装
                # 現在は何もしない（全ての問題を対象とする）
                pass
            
            if not available_questions:
                st.error("選択した条件に合う問題がありません。条件を変更してください。")
                st.error(f"条件: 出題形式={quiz_format}, 対象試験={target_exam}, 問題順序={question_order}")
                return
            
            # 問題の順序設定
            if question_order == "シャッフル":
                import random
                random.shuffle(available_questions)
            else:
                # 順番通り（問題番号順）- 自然順ソートを使用
                available_questions = sorted(available_questions, key=get_natural_sort_key)
            
            # 自由演習では条件に該当する全ての問題を使用
            selected_questions = available_questions
            
            # セッション状態を設定
            st.session_state["main_queue"] = [[q.get("number")] for q in selected_questions]
            st.session_state["session_mode"] = "free_learning"
            st.session_state["session_choice_made"] = True
            st.session_state["session_type"] = f"自由演習({quiz_format}/{target_exam})"
            st.session_state["session_start_time"] = time.time()
            
            # 自由学習セッション開始の追跡
            uid = st.session_state.get("uid")
            if uid:
                log_to_ga("study_session_start", uid, {
                    "session_type": "free_learning",
                    "question_count": len(selected_questions),
                    "session_id": f"free_{int(time.time())}",
                    "learning_mode": "自由演習",
                    "quiz_format": quiz_format,
                    "target_exam": target_exam,
                    "question_order": question_order
                })
            
            st.success(f"📚 {len(selected_questions)}問の学習セッションを開始します")
            AnalyticsUtils.track_study_session_start("free_learning", len(selected_questions))
            
            # 学習画面に遷移
            time.sleep(0.5)
            st.rerun()
            
        except Exception as e:
            st.error(f"自由演習の開始エラー: {e}")
            print(f"Free learning error: {e}")
            import traceback
            traceback.print_exc()


def _jump_to_question(q_id: str):
    """指定された問題にジャンプ"""
    st.session_state["current_question_id"] = q_id
    st.rerun()
