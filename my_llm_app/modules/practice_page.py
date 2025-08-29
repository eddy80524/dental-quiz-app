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
from typing import Dict, Any, List, Optional, Tuple

from auth import AuthManager
from firestore_db import FirestoreManager, get_firestore_manager, save_user_data, check_gakushi_permission, get_user_profile_for_ranking, save_user_profile
from utils import (
    log_to_ga, QuestionUtils, ALL_QUESTIONS, ALL_QUESTIONS_DICT, 
    CardSelectionUtils, SM2Algorithm, AnalyticsUtils,
    HISSHU_Q_NUMBERS_SET, GAKUSHI_HISSHU_Q_NUMBERS_SET
)
from firebase_analytics import FirebaseAnalytics, PerformanceAnalytics


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
    def render_question_display(questions: List[Dict], case_data: Dict = None):
        """問題表示コンポーネント"""
        # 問題タイプ表示
        if questions:
            first_question_id = questions[0].get('number', '')
            cards = st.session_state.get("cards", {})
            
            if first_question_id in cards and cards[first_question_id].get('n', 0) > 0:
                st.info("🔄 **復習問題**")
            else:
                st.info("🆕 **新規問題**")
        
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
                image_urls = question.get('image_urls', [])
                if image_urls:
                    for img_index, img_url in enumerate(image_urls):
                        try:
                            st.image(
                                img_url, 
                                caption=f"問題 {question_number} の図 {img_index + 1}",
                                use_column_width=True
                            )
                        except Exception as e:
                            st.warning(f"画像を読み込めませんでした: {img_url}")
                
                # 問題間の区切り
                if i < len(questions) - 1:
                    st.markdown("---")
    
    @staticmethod
    def shuffle_choices(choices: List[str]) -> List[str]:
        """選択肢をシャッフル"""
        shuffled = choices.copy()
        random.shuffle(shuffled)
        return shuffled
    
    @staticmethod
    def get_choice_label(index: int) -> str:
        """選択肢のラベル生成 (A, B, C...)"""
        return chr(65 + index)


class AnswerModeComponent:
    """解答モードコンポーネント"""
    
    @staticmethod
    def render(questions: List[Dict], group_id: str, case_data: Dict = None) -> Dict[str, Any]:
        """解答モード画面の描画（問題表示も含む）"""
        user_selections = {}
        
        # 問題タイプ表示
        if questions:
            first_question_id = questions[0].get('number', '')
            cards = st.session_state.get("cards", {})
            
            if first_question_id in cards and cards[first_question_id].get('n', 0) > 0:
                st.info("🔄 **復習問題**")
            else:
                st.info("🆕 **新規問題**")
        
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
        
        # スタイル付きコンテナ
        with st.container():
            st.markdown(
                """
                <div style="
                    background-color: #fafafa; 
                    padding: 24px; 
                    border-radius: 12px; 
                    margin-top: 24px;
                ">
                """, 
                unsafe_allow_html=True
            )
            
            # フォーム開始
            with st.form(key=f"answer_form_{group_id}"):
                
                for q_index, question in enumerate(questions):
                    qid = question.get('number', f'q_{q_index}')
                    choices = question.get('choices', [])
                    
                    # 問題ID
                    question_number = question.get('number', '')
                    if question_number:
                        st.markdown(f"#### {question_number}")
                    
                    # 問題文（化学式対応）
                    question_text = QuestionComponent.format_chemical_formula(
                        question.get('question', '')
                    )
                    st.markdown(question_text)
                    
                    if not choices:
                        # 自由入力問題
                        st.markdown(f"##### 解答を入力してください:")
                        user_selections[qid] = st.text_input(
                            "解答:",
                            key=f"input_{qid}_{group_id}",
                            placeholder="解答を入力..."
                        )
                    
                    elif AnswerModeComponent._is_ordering_question(question.get('question', '')):
                        # 並び替え問題
                        shuffled_choices = QuestionComponent.shuffle_choices(choices)
                        
                        user_selections[qid] = st.text_input(
                            "解答（記号のみ）:",
                            key=f"ordering_{qid}_{group_id}",
                            placeholder="例: ABCD",
                            help="選択肢を確認して、正しい順番で記号を入力してください"
                        )
                    
                    else:
                        # 選択式問題 - 選択肢を問題文の直後に表示
                        # セッション状態に選択肢の順序を保存
                        shuffle_key = f"shuffled_choices_{qid}_{group_id}"
                        if shuffle_key not in st.session_state:
                            st.session_state[shuffle_key] = QuestionComponent.shuffle_choices(choices)
                        
                        shuffled_choices = st.session_state[shuffle_key]
                        selected_choices = []
                        
                        # 選択肢表示
                        for choice_index, choice in enumerate(shuffled_choices):
                            label = QuestionComponent.get_choice_label(choice_index)
                            
                            # チェックボックスのスタイル改善
                            is_selected = st.checkbox(
                                f"{label}. {choice}",
                                key=f"choice_{qid}_{choice_index}_{group_id}"
                            )
                            
                            if is_selected:
                                selected_choices.append(choice)
                        
                        user_selections[qid] = selected_choices
                    
                    # 問題間の区切り
                    if q_index < len(questions) - 1:
                        st.markdown("---")
                
                # アクションボタンエリア（選択肢の後、画像の前）
                col1, col2, col3 = st.columns([2, 2, 3])
                
                with col1:
                    check_submitted = st.form_submit_button(
                        "📝 回答をチェック", 
                        type="primary",
                        help="選択した解答を確認します"
                    )
                
                with col2:
                    skip_submitted = st.form_submit_button(
                        "⏭️ スキップ",
                        help="この問題をスキップして後で解きます"
                    )
                
                # 画像表示（ボタンの後）
                for q_index, question in enumerate(questions):
                    question_number = question.get('number', '')
                    image_urls = question.get('image_urls', [])
                    if image_urls:
                        st.markdown("---")  # 区切り線
                        for img_index, img_url in enumerate(image_urls):
                            try:
                                st.image(
                                    img_url, 
                                    caption=f"問題 {question_number} の図 {img_index + 1}",
                                    use_container_width=True
                                )
                            except Exception as e:
                                st.warning(f"画像を読み込めませんでした: {img_url}")
            
            st.markdown("</div>", unsafe_allow_html=True)
        
        return {
            'user_selections': user_selections,
            'check_submitted': check_submitted,
            'skip_submitted': skip_submitted
        }
    
    @staticmethod
    def _is_ordering_question(question_text: str) -> bool:
        """並び替え問題の判定"""
        ordering_keywords = ['順番', '順序', '配列', '並び替え', '手順']
        return any(keyword in question_text for keyword in ordering_keywords)


class ResultModeComponent:
    """結果表示モードコンポーネント"""
    
    @staticmethod
    def render(questions: List[Dict], group_id: str, result_data: Dict, case_data: Dict = None) -> Dict[str, Any]:
        """結果表示モード画面の描画（問題表示も含む）"""
        
        # 問題タイプ表示
        if questions:
            first_question_id = questions[0].get('number', '')
            cards = st.session_state.get("cards", {})
            
            if first_question_id in cards and cards[first_question_id].get('n', 0) > 0:
                st.info("🔄 **復習問題**")
            else:
                st.info("🆕 **新規問題**")
        
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
        
        with st.container():
            # 結果表示エリア
            for q_index, question in enumerate(questions):
                qid = question.get('number', f'q_{q_index}')
                user_answer = result_data.get(qid, {}).get('user_answer', '')
                correct_answer = question.get('answer', '')
                is_correct = result_data.get(qid, {}).get('is_correct', False)
                
                # 問題表示エリア
                st.markdown(f"#### 問題 {q_index + 1}")
                
                # 問題ID
                question_number = question.get('number', '')
                if question_number:
                    st.markdown(f"**{question_number}**")
                
                # 問題文（化学式対応）
                question_text = QuestionComponent.format_chemical_formula(
                    question.get('question', '')
                )
                st.markdown(question_text)
                
                # 選択肢表示
                choices = question.get('choices', [])
                if choices:
                    st.markdown("**選択肢:**")
                    for choice_index, choice in enumerate(choices):
                        label = QuestionComponent.get_choice_label(choice_index)
                        # 正解の選択肢をハイライト
                        if choice in correct_answer or str(choice_index + 1) in correct_answer or label in correct_answer:
                            st.markdown(f"✅ **{label}. {choice}** (正解)")
                        elif choice in user_answer:
                            if is_correct:
                                st.markdown(f"✅ {label}. {choice} (あなたの選択)")
                            else:
                                st.markdown(f"❌ {label}. {choice} (あなたの選択)")
                        else:
                            st.markdown(f"{label}. {choice}")
                
                # 画像表示（選択肢の後）
                image_urls = question.get('image_urls', [])
                if image_urls:
                    for img_index, img_url in enumerate(image_urls):
                        try:
                            st.image(
                                img_url, 
                                caption=f"問題 {question_number} の図 {img_index + 1}",
                                use_container_width=True
                            )
                        except Exception as e:
                            st.warning(f"画像を読み込めませんでした: {img_url}")
                
                # 結果ステータス表示
                if is_correct:
                    st.markdown(
                        f"""
                        <div style="
                            background-color: #e8f5e8; 
                            border-left: 4px solid #4caf50; 
                            padding: 16px; 
                            border-radius: 8px; 
                            margin: 16px 0;
                        ">
                            <span style="color: #2e7d32; font-size: 1.2rem; font-weight: 600;">
                                ✅ 正解！
                            </span>
                        </div>
                        """, 
                        unsafe_allow_html=True
                    )
                else:
                    formatted_answer = QuestionUtils.format_answer_display(correct_answer)
                    st.markdown(
                        f"""
                        <div style="
                            background-color: #ffeaea; 
                            border-left: 4px solid #f44336; 
                            padding: 16px; 
                            border-radius: 8px; 
                            margin: 16px 0;
                        ">
                            <span style="color: #c62828; font-size: 1.2rem; font-weight: 600;">
                                ❌ 不正解
                            </span><br>
                            <span style="color: #1976d2; font-weight: 500; margin-top: 8px; display: block;">
                                正解: {formatted_answer}
                            </span>
                        </div>
                        """, 
                        unsafe_allow_html=True
                    )
                
                # ユーザーの解答表示（無効化されたチェックボックス）
                st.markdown("**あなたの解答:**")
                
                # 選択肢の表示（無効化）
                choices = question.get('choices', [])
                if choices:
                    shuffle_key = f"shuffled_choices_{qid}_{group_id}"
                    shuffled_choices = st.session_state.get(shuffle_key, choices)
                    
                    for choice_index, choice in enumerate(shuffled_choices):
                        label = QuestionComponent.get_choice_label(choice_index)
                        is_user_selected = choice in (user_answer if isinstance(user_answer, list) else [])
                        
                        # 無効化されたチェックボックスの表示
                        st.checkbox(
                            f"{label}. {choice}",
                            value=is_user_selected,
                            disabled=True,
                            key=f"result_choice_{qid}_{choice_index}_{group_id}"
                        )
                
                # 解説表示
                explanation = question.get('explanation', '')
                if explanation:
                    st.markdown(
                        f"""
                        <div style="
                            background-color: #f8f9fa; 
                            padding: 16px; 
                            border-radius: 8px; 
                            margin: 16px 0;
                        ">
                            <h6 style="color: #1976d2; margin-bottom: 8px;">💡 解説:</h6>
                            <p style="margin: 0;">{explanation}</p>
                        </div>
                        """, 
                        unsafe_allow_html=True
                    )
                
                # 問題間の区切り
                if q_index < len(questions) - 1:
                    st.markdown("---")
        
        # 自己評価エリア
        return ResultModeComponent._render_self_evaluation(group_id)
    
    @staticmethod
    def _render_self_evaluation(group_id: str) -> Dict[str, Any]:
        """自己評価フォームの描画"""
        
        st.markdown(
            """
            <div style="
                background-color: #f8f9fa; 
                padding: 24px; 
                border-radius: 12px; 
                margin-top: 32px;
            ">
            """, 
            unsafe_allow_html=True
        )
        
        with st.form(key=f"evaluation_form_{group_id}"):
            st.markdown("#### 📊 学習の自己評価")
            st.markdown("この問題グループの理解度を評価してください：")
            
            # 自己評価の選択肢
            quality_options = [
                "🔄 もう一度（要復習）",
                "😅 難しい（部分的理解）", 
                "👍 普通（概ね理解）",
                "🔥 簡単（完全に理解）"
            ]
            
            # デフォルト値の決定（結果に基づく）
            default_index = 2  # 普通をデフォルト
            
            quality = st.radio(
                "理解度：",
                options=quality_options,
                index=default_index,
                key=f"quality_{group_id}",
                horizontal=True  # 横並び表示
            )
            
            st.markdown("### ")  # スペース
            
            # 次の問題へボタン
            col1, col2, col3 = st.columns([2, 3, 2])
            with col2:
                next_submitted = st.form_submit_button(
                    "➡️ 次の問題へ", 
                    type="primary",
                    help="自己評価を記録して次の問題に進みます"
                )
        
        st.markdown("</div>", unsafe_allow_html=True)
        
        return {
            'quality': quality,
            'next_submitted': next_submitted
        }


class PracticeSession:
    """練習セッションを管理するクラス"""
    
    def __init__(self):
        self.firestore_manager = get_firestore_manager()
    
    def get_next_q_group(self) -> List[str]:
        """次の問題グループを取得"""
        now = datetime.datetime.now(datetime.timezone.utc)
        
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
                return item.get("group", [])
        
        # 通常時：復習30%、新規70%の確率で選択
        elif review_count > 0 and new_count > 0:
            if random.random() < 0.3:  # 30%の確率で復習
                i, item = ready_reviews[0]
                stq.pop(i)
                return item.get("group", [])
            else:
                return main_queue.pop(0) if main_queue else []
        
        # 復習問題のみ利用可能
        elif ready_reviews:
            i, item = ready_reviews[0]
            stq.pop(i)
            return item.get("group", [])
        
        # 新規問題のみ利用可能
        elif main_queue:
            return main_queue.pop(0)
        
        # 問題がない場合
        return []
    
    def enqueue_short_review(self, group: List[str], minutes: int):
        """短期復習キューに追加"""
        ready_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=minutes)
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
            # Cloud Function失敗時はローカルでフォールバック
            st.warning("Cloud Functionでの生成に失敗しました。ローカル生成にフォールバック中...")
            return self._fallback_local_quiz_generation()
    
    def _fallback_local_quiz_generation(self) -> bool:
        """ローカルでのクイズ生成（フォールバック）"""
        try:
            uid = st.session_state.get("uid")
            if not uid:
                return False
            
            cards = st.session_state.get("cards", {})
            if not cards:
                # カードデータを読み込み
                cards = self.firestore_manager.load_user_cards(uid)
                st.session_state["cards"] = cards
            
            # 新規カード選択
            new_cards_per_day = st.session_state.get("new_cards_per_day", 10)
            recent_qids = list(st.session_state.get("result_log", {}).keys())[-10:]
            
            selected_new = CardSelectionUtils.pick_new_cards_for_today(
                ALL_QUESTIONS, cards, new_cards_per_day, recent_qids
            )
            
            # 復習カード選択（期限切れのもの）
            now = datetime.datetime.now(datetime.timezone.utc)
            due_cards = []
            for qid, card in cards.items():
                next_review = card.get("next_review")
                if next_review:
                    try:
                        next_dt = datetime.datetime.fromisoformat(next_review)
                        if next_dt <= now:
                            due_cards.append(qid)
                    except (ValueError, TypeError):
                        continue
            
            # グループ化（5問ずつ）
            all_cards = selected_new + due_cards
            random.shuffle(all_cards)
            
            main_queue = []
            for i in range(0, len(all_cards), 5):
                group = all_cards[i:i+5]
                if group:
                    main_queue.append(group)
            
            st.session_state["main_queue"] = main_queue
            st.session_state["current_q_group"] = []
            st.session_state["short_term_review_queue"] = []
            
            st.success(f"📚 ローカル学習キューを生成しました（{len(main_queue)}グループ）")
            return True
            
        except Exception as e:
            st.error(f"ローカルクイズ生成エラー: {e}")
            return False


def render_practice_page(auth_manager=None):
    """練習ページのメイン描画関数（uid統一版）"""
    practice_session = PracticeSession()
    
    # ユーザー認証チェック
    if auth_manager is None:
        auth_manager = AuthManager()
    if not auth_manager.ensure_valid_session():
        st.error("セッションが無効です。再ログインしてください。")
        return
    
    uid = st.session_state.get("uid")
    if not uid:
        st.error("ユーザーIDが見つかりません。")
        return
    
    # 前回セッション復帰処理
    if st.session_state.get("continue_previous") and st.session_state.get("session_choice_made"):
        st.success("🔄 前回のセッションを復帰しました")
        st.session_state.pop("continue_previous", None)
        
        if st.session_state.get("current_question_index") is not None:
            st.info(f"問題 {st.session_state.get('current_question_index', 0) + 1} から継続します")
    
    # サイドバーで学習モードが選択されていない場合の案内
    if not st.session_state.get("session_choice_made") and not st.session_state.get("main_queue"):
        st.info("📌 サイドバーから学習モードを選択して、学習を開始してください。")
        st.markdown("""
        ### 🎯 学習モードについて
        
        **おまかせ学習（推奨）**
        - AIが最適な問題を自動選択
        - 復習スケジュールを考慮
        - 効率的な学習が可能
        
        **自由演習**
        - 分野や回数を自由に設定
        - 苦手分野の集中学習
        - カスタマイズされた練習
        """)
        return
    
    # アクティブセッション表示
    _render_active_session(practice_session, uid)


def _render_active_session(practice_session: PracticeSession, uid: str):
    """アクティブな学習セッションの表示"""
    session_type = st.session_state.get("session_type", "")
    
    if session_type == "おまかせ演習" or session_type == "自動学習":
        _render_omakase_session(practice_session, uid)
    elif session_type == "カスタム演習":
        _render_custom_session(practice_session, uid)
    elif session_type.startswith("自由演習"):
        _render_free_learning_session(practice_session, uid)
    else:
        st.error("セッションタイプが不明です")


def _render_omakase_session(practice_session: PracticeSession, uid: str):
    """おまかせ演習セッションの表示"""
    st.header("おまかせ演習")
    
    # セッションリセットボタン
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("🔄 セッションリセット", help="新しいセッションを開始"):
            _reset_session()
            return
    
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
    
    # セッションリセットボタン
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("🔄 セッションリセット", help="新しいセッションを開始"):
            _reset_session()
            return
    
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


def _render_custom_settings():
    """カスタム演習の設定UIを表示"""
    try:
        # 年度選択
        col1, col2 = st.columns(2)
        
        with col1:
            years = ["2024", "2023", "2022", "2021", "2020"]
            selected_years = st.multiselect(
                "📅 出題年度",
                years,
                default=["2024", "2023"],
                help="問題の出題年度を選択してください"
            )
        
        with col2:
            # 問題数選択
            num_questions = st.slider(
                "📝 問題数",
                min_value=5,
                max_value=100,
                value=20,
                step=5,
                help="演習する問題数を選択してください"
            )
        
        # 分野選択
        subjects = [
            "歯科理工学", "歯科保存学", "歯科補綴学", "口腔外科学",
            "歯科矯正学", "小児歯科学", "歯周病学", "口腔病理学",
            "歯科放射線学", "歯科麻酔学", "高齢者歯科学", "歯科法医学"
        ]
        
        selected_subjects = st.multiselect(
            "📚 出題分野",
            subjects,
            default=subjects[:4],  # デフォルトで最初の4つを選択
            help="演習したい分野を選択してください"
        )
        
        # 難易度選択
        difficulty_levels = ["基礎", "標準", "応用", "すべて"]
        selected_difficulty = st.selectbox(
            "⭐ 難易度",
            difficulty_levels,
            index=3,  # デフォルトで「すべて」
            help="問題の難易度を選択してください"
        )
        
        # 設定ボタン
        if st.button("🎯 問題を生成", type="primary", use_container_width=True):
            if not selected_years:
                st.error("❌ 出題年度を選択してください")
                return
            
            if not selected_subjects:
                st.error("❌ 出題分野を選択してください")
                return
            
            # カスタム設定を保存
            st.session_state["custom_settings"] = {
                "years": selected_years,
                "subjects": selected_subjects,
                "difficulty": selected_difficulty,
                "num_questions": num_questions
            }
            
            # 問題生成フラグを設定
            st.session_state["custom_questions_selected"] = True
            
            st.success(f"✅ {num_questions}問の問題を生成しました！")
            st.rerun()
            
    except Exception as e:
        st.error(f"カスタム設定でエラーが発生しました: {str(e)}")


def _render_custom_session(practice_session: PracticeSession, uid: str):
    """カスタム演習セッションの表示"""
    st.header("🎯 カスタム演習")
    
    # セッションリセットボタン
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("🔄 セッションリセット", help="新しいセッションを開始"):
            _reset_session()
            return
    
    # カスタム演習の設定UI
    with st.expander("⚙️ 演習設定", expanded=True):
        _render_custom_settings()
    
    # 問題表示
    if st.session_state.get("custom_questions_selected"):
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
                        "session_type": "カスタム演習",
                        "session_duration_seconds": session_duration,
                        "questions_completed": len(st.session_state.get("main_queue", [])),
                        "completion_method": "all_questions_finished"
                    })
                    
                    st.session_state["session_completed_logged"] = True
                
                st.info("📚 全ての問題が完了しました！新しいセッションを開始してください。")
                if st.button("新しいセッションを開始"):
                    _reset_session()
                return
        
        _display_current_question(practice_session, uid)
    else:
        st.info("上記の設定で問題を選択してください。")


def _display_current_question(practice_session: PracticeSession, uid: str):
    """現在の問題を表示（コンポーネントベースの実装）"""
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
    is_checked = st.session_state.get(f"checked_{group_id}", False)
    
    # 2. 状態による表示分岐：解答モード vs 結果表示モード
    if not is_checked:
        # 解答モード（問題表示も含む）
        answer_result = AnswerModeComponent.render(q_objects, group_id, case_data)
        
        # ボタンアクションの処理
        if answer_result['check_submitted']:
            _process_group_answer_improved(
                q_objects, 
                answer_result['user_selections'], 
                group_id, 
                practice_session, 
                uid
            )
        elif answer_result['skip_submitted']:
            _skip_current_group(practice_session)
    
    else:
        # 結果表示モード
        result_data = st.session_state.get(f"result_{group_id}", {})
        evaluation_result = ResultModeComponent.render(q_objects, group_id, result_data, case_data)
        
        if evaluation_result['next_submitted']:
            _process_self_evaluation_improved(
                q_objects,
                evaluation_result['quality'],
                group_id,
                practice_session,
                uid
            )


def _process_group_answer_improved(q_objects: List[Dict], user_selections: Dict, 
                                 group_id: str, practice_session: PracticeSession, uid: str):
    """改善された解答処理"""
    result_data = {}
    
    for question in q_objects:
        qid = question.get('number', '')
        user_answer = user_selections.get(qid, '')
        correct_answer = question.get('answer', '')
        
        # 解答形式の調整
        if isinstance(user_answer, list):
            # チェックボックスの場合、選択された項目から文字を抽出
            user_answer_str = ''.join([
                choice.split('.')[0].strip() if '.' in choice else choice[0] 
                for choice in user_answer
            ])
        else:
            user_answer_str = str(user_answer).strip()
        
        # 正誤判定（複数解答対応）
        is_correct = QuestionUtils.check_answer(user_answer_str, correct_answer)
        
        result_data[qid] = {
            'user_answer': user_answer,
            'user_answer_str': user_answer_str,
            'correct_answer': correct_answer,
            'is_correct': is_correct
        }
    
    # 結果をセッションに保存
    st.session_state[f"result_{group_id}"] = result_data
    st.session_state[f"checked_{group_id}"] = True
    
    # Google Analytics ログ（詳細追跡）
    session_type = st.session_state.get("session_type", "unknown")
    session_start_time = st.session_state.get("session_start_time", time.time())
    session_duration = time.time() - session_start_time
    
    for qid, result in result_data.items():
        question_data = ALL_QUESTIONS_DICT.get(qid, {})
        
        log_to_ga("question_answered", uid, {
            "question_id": qid,
            "question_number": question_data.get("number", "unknown"),
            "is_correct": result['is_correct'],
            "subject": question_data.get("subject", "unknown"),
            "session_type": session_type,
            "session_duration_seconds": session_duration,
            "answer_count": len(result_data),
            "user_answer": result.get("user_answer", "unknown"),
            "correct_answer": result.get("correct_answer", "unknown")
        })
        
        # Firebase Analytics統合
        FirebaseAnalytics.log_question_answered(
            uid=uid,
            question_id=qid,
            is_correct=result['is_correct'],
            quality=0,  # 自己評価前なので0
            metadata={
                "session_type": session_type,
                "question_number": question_data.get("number", "unknown"),
                "subject": question_data.get("subject", "unknown"),
                "session_duration_seconds": session_duration,
                "answer_method": "multiple_choice",
                "group_id": group_id
            }
        )
        
        # Google Analytics統合
        AnalyticsUtils.track_question_answered(qid, result['is_correct'])
    
    # 成功メッセージ
    all_correct = all(result['is_correct'] for result in result_data.values())
    if all_correct:
        st.success("🎉 全問正解です！")
    else:
        correct_count = sum(1 for result in result_data.values() if result['is_correct'])
        total_count = len(result_data)
        st.info(f"📊 {correct_count}/{total_count} 問正解")
    
    st.rerun()


def _process_self_evaluation_improved(q_objects: List[Dict], quality_text: str, 
                                    group_id: str, practice_session: PracticeSession, uid: str):
    """改善された自己評価処理"""
    # 品質スコアの変換（絵文字対応）
    quality_mapping = {
        "🔥 簡単（完全に理解）": 5,
        "👍 普通（概ね理解）": 4,
        "😅 難しい（部分的理解）": 2,
        "🔄 もう一度（要復習）": 1
    }
    quality = quality_mapping.get(quality_text, 3)
    
    # 各問題のSM2更新
    cards = st.session_state.get("cards", {})
    updated_cards = []
    
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
        
        # Firestoreに保存
        save_user_data(uid, qid, updated_card)
        
        # Firebase Analytics: 自己評価ログ
        result_data = st.session_state.get(f"result_{group_id}", {}).get(qid, {})
        FirebaseAnalytics.log_question_answered(
            uid=uid,
            question_id=qid,
            is_correct=result_data.get('is_correct', False),
            quality=quality,
            metadata={
                "session_type": st.session_state.get("session_type", "unknown"),
                "quality_text": quality_text,
                "self_evaluation": True,
                "group_id": group_id,
                "ef_after": updated_card.get("EF", 2.5),
                "interval_after": updated_card.get("interval", 0)
            }
        )
    
    st.session_state["cards"] = cards
    
    # 学習ログに記録
    result_log = st.session_state.get("result_log", {})
    for question in q_objects:
        qid = question.get('number', '')
        result_data = st.session_state.get(f"result_{group_id}", {}).get(qid, {})
        
        result_log[qid] = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "correct": result_data.get('is_correct', False),
            "selected": result_data.get('user_answer_str', ''),
            "quality": quality
        }
    
    st.session_state["result_log"] = result_log
    
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
    
    st.rerun()


def _get_case_data(case_id: str) -> Dict[str, Any]:
    """症例データを取得"""
    # 症例データの取得ロジック（実装に応じて調整）
    for question in ALL_QUESTIONS:
        if question.get('case_id') == case_id and question.get('scenario_text'):
            return {
                'scenario_text': question.get('scenario_text', ''),
                'case_id': case_id
            }
    return None


def _skip_current_group(practice_session: PracticeSession):
    """現在の問題グループをスキップ"""
    current_group = st.session_state.get("current_q_group", [])
    
    if current_group:
        # スキップした問題をキューの末尾に戻す
        main_queue = st.session_state.get("main_queue", [])
        main_queue.append(current_group)
        st.session_state["main_queue"] = main_queue
        st.info("📚 問題をスキップしました。後ほど再出題されます。")
    
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
        "main_queue", "short_term_review_queue", "custom_questions_selected",
        "session_completed_logged", "session_start_time"
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
    try:
        uid = st.session_state.get("uid")
        if not uid:
            st.warning("ユーザーIDが見つかりません")
            return
            
        has_gakushi_permission = check_gakushi_permission(uid)
        
        # 🎓 1. 学習モードの選択
        learning_mode = st.radio(
            "学習モード",
            ['おまかせ学習（推奨）', '自由演習（分野・回数指定）'],
            key="learning_mode"
        )
        
        st.divider()
        
        if learning_mode == 'おまかせ学習（推奨）':
            _render_auto_learning_mode()
        else:
            _render_free_learning_mode(has_gakushi_permission)
        
        # 📋 4. 共通のUI要素
        _render_session_status()
        
        # 👤 プロフィール設定セクション
        st.divider()
        with st.expander("👤 プロフィール設定"):
            _render_profile_settings_in_sidebar(uid)
        
    except Exception as e:
        st.error(f"学習ハブでエラーが発生しました: {str(e)}")
        st.exception(e)


def _render_auto_learning_mode():
    """🚀 2. 「おまかせ学習」モードのUI（個人データ対応）"""
    try:
        st.markdown("### 📊 本日の学習状況")
        
        uid = st.session_state.get("uid")
        if not uid:
            st.warning("ユーザーIDが見つかりません")
            return
        
        # Firestoreから個人の学習データを取得
        firestore_manager = get_firestore_manager()
        try:
            user_cards = firestore_manager.get_user_cards(uid)
            session_cards = st.session_state.get("cards", {})
            # セッションデータを優先して統合
            cards = {**user_cards, **session_cards}
        except Exception as e:
            st.warning(f"学習データの取得に失敗: {str(e)}")
            cards = st.session_state.get("cards", {})
        
        new_cards_per_day = st.session_state.get("new_cards_per_day", 10)
        
        # リアルタイム計算
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        
        # 復習カード数（期限切れ）
        review_count = 0
        # 新規カード数（今日学習予定）
        new_count = 0
        # 完了数（今日学習済み）
        completed_count = 0
        
        for q_id, card in cards.items():
            # 復習期限チェック
            next_review = card.get("next_review", "")
            if next_review and next_review <= today:
                review_count += 1
            
            # 今日の学習記録チェック
            history = card.get("history", [])
            today_studied = any(h.get("date", "").startswith(today) for h in history)
            if today_studied:
                completed_count += 1
            elif len(history) == 0:  # 未学習カード
                new_count += 1
        
        # 新規カード数を上限で制限
        new_count = min(new_count, new_cards_per_day)
        total_target = review_count + new_count
        
        # メトリクス表示
        col1, col2 = st.columns(2)
        with col1:
            st.metric("復習", f"{review_count}問", help="期限が来た復習問題")
            st.metric("完了", f"{completed_count}問", help="今日学習済みの問題")
        
        with col2:
            st.metric("新規", f"{new_count}問", help="今日の新規学習予定")
            if total_target > 0:
                progress = min(completed_count / total_target, 1.0)
                st.metric("達成率", f"{progress:.1%}", help="本日の学習進捗")
        
        # 学習開始ボタン
        if st.button("📚 今日の学習を開始する", type="primary", use_container_width=True):
            _start_auto_learning()
            
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
                ["全て", "国試", "学士試験"],
                key="free_target_exam"
            )
        else:
            target_exam = st.radio(
                "対象試験",
                ["全て", "国試"],
                key="free_target_exam"
            )
            st.info("📚 学士試験機能を利用するには権限が必要です")
        
        # 出題形式の選択
        quiz_format = st.radio(
            "出題形式",
            ["全て", "回数別", "科目別", "必修問題のみ", "キーワード検索"],
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
            kaisu_options = [f"{i}回" for i in range(95, 118)]  # 95回〜117回
            selected_kaisu = st.selectbox("国試回数", kaisu_options, 
                                        index=len(kaisu_options)-1, key="free_kaisu")
            
            # 領域選択
            area_options = ["全領域", "A領域", "B領域", "C領域", "D領域"]
            selected_area = st.selectbox("領域", area_options, key="free_area")
        else:
            # 学士試験の年度・回数選択
            year_options = [f"{y}年度" for y in range(2020, 2025)]
            selected_year = st.selectbox("年度", year_options, 
                                       index=len(year_options)-1, key="free_gakushi_year")
            
            kaisu_options = ["1回", "2回"]
            selected_kaisu = st.selectbox("回数", kaisu_options, key="free_gakushi_kaisu")
            
            area_options = ["全領域", "A領域", "B領域"]
            selected_area = st.selectbox("領域", area_options, key="free_gakushi_area")
    
    elif quiz_format == "科目別":
        # 科目グループ選択
        group_options = ["基礎系", "臨床系"]
        selected_group = st.selectbox("科目グループ", group_options, key="free_subject_group")
        
        # 具体的な科目選択（実際のデータから取得）
        if selected_group == "基礎系":
            subject_options = [
                "解剖学", "生理学", "生化学", "病理学", "微生物学・免疫学", 
                "薬理学", "歯科理工学", "組織学", "発生学・加齢老年学"
            ]
        else:
            subject_options = [
                "保存修復学", "歯内治療学", "歯周病学", "クラウンブリッジ学", 
                "部分床義歯学", "全部床義歯学", "口腔外科学", "矯正歯科学", 
                "小児歯科学", "歯科麻酔学", "歯科放射線学", "衛生学", "インプラント学"
            ]
        
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
    
    # 最近の評価ログ
    result_log = st.session_state.get("result_log", {})
    if result_log:
        st.markdown("### 🔄 最近の評価")
        recent_results = list(result_log.items())[-10:]  # 最新10件
        
        # 問題番号ボタンを3列で表示
        cols = st.columns(3)
        for i, (q_id, result) in enumerate(recent_results):
            with cols[i % 3]:
                # 評価に応じたアイコン
                if result.get("quality") == 5:
                    icon = "🔥"
                elif result.get("quality") == 4:
                    icon = "👍"
                elif result.get("quality") == 2:
                    icon = "😅"
                else:
                    icon = "🔄"
                
                if st.button(f"{icon} {q_id}", key=f"recent_{q_id}", use_container_width=True):
                    # 問題に直接ジャンプ
                    _jump_to_question(q_id)


def _render_profile_settings_in_sidebar(uid: str):
    """サイドバー用のプロフィール設定UIを描画"""
    # 現在のプロフィールを取得
    current_profile = get_user_profile_for_ranking(uid)
    
    # デフォルト値の設定
    default_nickname = ""
    default_show_on_leaderboard = True
    
    if current_profile:
        default_nickname = current_profile.get("nickname", "")
        default_show_on_leaderboard = current_profile.get("show_on_leaderboard", True)
    
    with st.form("sidebar_profile_form"):
        st.write("**ランキング表示設定**")
        
        # ニックネーム入力
        nickname = st.text_input(
            "ニックネーム",
            value=default_nickname,
            help="ランキングに表示される名前です",
            placeholder="例: 勇敢なパンダ123"
        )
        
        # ランキング参加設定
        show_on_leaderboard = st.checkbox(
            "ランキングに参加する",
            value=default_show_on_leaderboard,
            help="チェックを外すとランキングに表示されません"
        )
        
        # 保存ボタン
        if st.form_submit_button("💾 保存", type="primary"):
            if nickname.strip():
                try:
                    success = save_user_profile(uid, nickname.strip(), show_on_leaderboard)
                    if success:
                        st.success("プロフィールを更新しました！")
                        # セッションの名前も更新
                        st.session_state["name"] = nickname.strip()
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("プロフィール更新に失敗しました")
                except Exception as e:
                    st.error(f"プロフィール更新エラー: {e}")
            else:
                st.error("ニックネームを入力してください")


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
        if uid and check_gakushi_permission(uid):
            available_questions = ALL_QUESTIONS
        else:
            # 学士以外の問題のみ
            available_questions = [q for q in ALL_QUESTIONS if q.get("exam_type") != "学士"]
    
    if not available_questions:
        st.error("利用可能な問題がありません。")
        return
    
    selected_questions = random.sample(available_questions, 
                                     min(new_cards_per_day, len(available_questions)))
    
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
            st.info(f"デバッグ: 全問題数: {len(available_questions)}")
            
            # 問題番号のサンプルを表示
            sample_numbers = [q.get("number") for q in available_questions[:10]]
            st.info(f"デバッグ: 問題番号例: {sample_numbers}")
            
            # 学士問題の数を確認
            gakushi_count = sum(1 for q in available_questions if q.get("number", "").startswith("G"))
            kokushi_count = sum(1 for q in available_questions if not q.get("number", "").startswith("G"))
            st.info(f"デバッグ: 学士問題: {gakushi_count}問, 国試問題: {kokushi_count}問")
            
            if uid and not check_gakushi_permission(uid):
                # 学士以外の問題のみ（番号が'G'で始まらない問題）
                available_questions = [q for q in ALL_QUESTIONS if not q.get("number", "").startswith("G")]
                st.info(f"デバッグ: 学士除外後: {len(available_questions)}")
            
            # 対象試験での絞り込み
            if target_exam != "全て":
                if target_exam == "国試":
                    # 国試問題：番号が'G'で始まらない問題
                    available_questions = [q for q in available_questions if not q.get("number", "").startswith("G")]
                elif target_exam == "学士試験":
                    # 学士試験問題：番号が'G'で始まる問題
                    available_questions = [q for q in available_questions if q.get("number", "").startswith("G")]
                elif target_exam == "CBT":
                    # CBT問題：現在は実装されていないため空リスト
                    available_questions = []
                st.info(f"デバッグ: 試験種別({target_exam})絞り込み後: {len(available_questions)}")
                
                # 絞り込み後の問題のexam_typeを確認
                if len(available_questions) == 0 and target_exam == "CBT":
                    st.warning("CBT問題は現在データベースに含まれていません。")
            
            # 出題形式での絞り込み
            if quiz_format != "全て":
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
                        
                        st.info(f"デバッグ: {selected_kaisu}{selected_area}絞り込み後: {len(available_questions)}")
                        
                    elif target_exam == "学士試験":
                        selected_year = st.session_state.get("free_gakushi_year", "24年")
                        selected_kaisu = st.session_state.get("free_gakushi_kaisu", "1回")
                        selected_area = st.session_state.get("free_gakushi_area", "全領域")
                        
                        # "24年" -> "24", "1回" -> "1" に変換
                        year_number = selected_year.replace("年", "")
                        kaisu_number = selected_kaisu.replace("回", "")
                        
                        # 学士試験の問題番号形式: G24-1-... など
                        available_questions = [q for q in available_questions 
                                             if q.get("number", "").startswith(f"G{year_number}-{kaisu_number}-")]
                        
                        # 領域の絞り込み
                        if selected_area != "全領域":
                            area_letter = selected_area.replace("領域", "")  # "A領域" -> "A"
                            available_questions = [q for q in available_questions 
                                                 if f"-{area_letter}-" in q.get("number", "")]
                        
                        st.info(f"デバッグ: 学士{selected_year}{selected_kaisu}{selected_area}絞り込み後: {len(available_questions)}")
                        
                elif quiz_format == "科目別":
                    # 科目別の詳細条件を取得
                    selected_subject = st.session_state.get("free_subject", "")
                    if selected_subject:
                        available_questions = [q for q in available_questions 
                                             if q.get("subject", "") == selected_subject]
                        st.info(f"デバッグ: 科目({selected_subject})絞り込み後: {len(available_questions)}")
                    pass
                elif quiz_format == "必修問題のみ":
                    # 必修問題のみ
                    if target_exam == "国試" or target_exam == "全て":
                        hisshu_numbers = HISSHU_Q_NUMBERS_SET
                        available_questions = [q for q in available_questions if q.get("number") in hisshu_numbers]
                    elif target_exam == "学士試験":
                        hisshu_numbers = GAKUSHI_HISSHU_Q_NUMBERS_SET
                        available_questions = [q for q in available_questions if q.get("number") in hisshu_numbers]
                    st.info(f"デバッグ: 必修問題絞り込み後: {len(available_questions)}")
                elif quiz_format == "キーワード検索":
                    # キーワード検索の詳細条件は後で追加実装
                    # 現在は何もしない（全ての問題を対象とする）
                    pass
            
            st.info(f"デバッグ: 最終的な利用可能問題数: {len(available_questions)}")
            
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
                from app import get_natural_sort_key
                available_questions = sorted(available_questions, key=get_natural_sort_key)
            
            # セッション設定
            new_cards_per_day = st.session_state.get("new_cards_per_day", 10)
            selected_questions = available_questions[:new_cards_per_day]
            
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
