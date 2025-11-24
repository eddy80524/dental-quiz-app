import streamlit as st
import re
from typing import List, Dict, Any, Optional
from utils import QuestionUtils, get_secure_image_url
from modules.notes_manager import NotesManager
from .question_display import QuestionComponent

class AnswerModeComponent:
    """解答、結果表示、自己評価のUIをすべて管理する統合コンポーネント"""

    @staticmethod
    def _normalize_question_text(text: Optional[str]) -> str:
        """改行や空白を除去したテキストを返す"""
        if not text:
            return ""
        return re.sub(r'\s+', '', text)

    @staticmethod
    def _get_input_mode(question: Dict[str, Any]) -> str:
        """選択肢方式か入力方式かを判定"""
        choices = question.get('choices') or []
        question_text = question.get('question', '') or ''

        # 並べ替え系の問題は入力方式を優先
        if QuestionUtils.is_ordering_question(question):
            return 'text'

        if not choices:
            return 'text'

        normalized_text = AnswerModeComponent._normalize_question_text(question_text)
        selection_pattern = re.compile(r'([一二三四五六七八九十]|[0-9０-９])+つ選べ')

        if selection_pattern.search(normalized_text):
            return 'choices'

        return 'text'

    @staticmethod
    def _get_text_input_placeholder(question: Dict[str, Any]) -> str:
        """入力欄のプレースホルダーを決定"""
        question_text = question.get('question', '') or ''
        answer = (question.get('answer', '') or '').strip()

        if QuestionUtils.is_ordering_question(question):
            return '例: ABDCE （順番通りに入力）'

        numeric_pattern = re.compile(r'^[-+]?\d+(?:\.\d+)?$')
        translation_table = str.maketrans({
            '０': '0', '１': '1', '２': '2', '３': '3', '４': '4',
            '５': '5', '６': '6', '７': '7', '８': '8', '９': '9',
            '．': '.', '－': '-', '＋': '+'
        })
        normalized_answer = answer.translate(translation_table)

        if numeric_pattern.match(answer) or numeric_pattern.match(normalized_answer):
            return '数値を入力（例: 60）'

        return '解答を入力（例: ABC）'

    @staticmethod
    def _render_text_answer_field(question: Dict[str, Any], qid: str, group_id: str, is_checked: bool) -> str:
        """入力形式の回答欄を描画し、入力値を返す"""
        raw_choices = question.get('choices') or []
        if raw_choices:
            st.markdown("**選択肢**")
            for idx, choice_text in enumerate(raw_choices):
                label = QuestionComponent.get_choice_label(idx)
                st.markdown(f"- {label}. {choice_text}")

        text_key = f"text_answer_{qid}_{group_id}"
        placeholder = AnswerModeComponent._get_text_input_placeholder(question)
        st.text_input(
            "解答を入力",
            key=text_key,
            placeholder=placeholder,
            disabled=is_checked
        )
        return st.session_state.get(text_key, '')

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
                
                input_mode = AnswerModeComponent._get_input_mode(question)

                if input_mode == 'choices':
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
                else:
                    # 入力形式の問題
                    st.session_state.pop(f"shuffled_mapping_{qid}_{group_id}", None)
                    st.session_state.pop(f"label_mapping_{qid}_{group_id}", None)
                    user_input = AnswerModeComponent._render_text_answer_field(
                        question, qid, group_id, is_checked
                    )
                    user_selections[qid] = user_input

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
                        
                        # 問題の選択肢情報を取得
                        question = next((q for q in questions if q.get('number') == qid), None)
                        question_choices = question.get('choices', []) if question else []
                        
                        main_msg, additional_info = QuestionUtils.get_answer_feedback_message(
                            user_ans, correct_answer, True, question_choices
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
                        
                        # 問題の選択肢情報を取得
                        question = next((q for q in questions if q.get('number') == qid), None)
                        question_choices = question.get('choices', []) if question else []
                        
                        main_msg, additional_info = QuestionUtils.get_answer_feedback_message(
                            user_ans, correct_answer, False, question_choices
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
                                
                                # 問題の選択肢情報を取得
                                question = next((q for q in questions if q.get('number') == qid), None)
                                question_choices = question.get('choices', []) if question else []
                                
                                _, additional_info = QuestionUtils.get_answer_feedback_message(
                                    user_ans, correct_answer, False, question_choices
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
        
        # メモセクションを自己評価後に表示
        if is_checked:
            AnswerModeComponent._render_notes_section(questions, group_id)
        
        # 画像はフォームの外（常に最後）に表示
        for question in questions:
            all_images = (question.get('image_urls', []) or []) + (question.get('image_paths', []) or [])
            if all_images:
                with st.expander(f"📸 {question.get('number', '')}の図を見る", expanded=is_checked):
                    for img_url in all_images:
                        secure_url = get_secure_image_url(img_url)
                        if secure_url:
                            st.image(
                                secure_url, 
                                use_container_width=True  # コンテナ幅に合わせてレスポンシブ表示
                            )
                            
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
                
                input_mode = AnswerModeComponent._get_input_mode(question)

                if input_mode == 'choices':
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
                else:
                    st.session_state.pop(f"shuffled_mapping_{qid}_{group_id}", None)
                    st.session_state.pop(f"label_mapping_{qid}_{group_id}", None)
                    user_input = AnswerModeComponent._render_text_answer_field(
                        question, qid, group_id, is_checked
                    )
                    user_selections[qid] = user_input

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
                        
                        # 問題の選択肢情報を取得
                        question = next((q for q in questions if q.get('number') == qid), None)
                        question_choices = question.get('choices', []) if question else []
                        
                        main_msg, additional_info = QuestionUtils.get_answer_feedback_message(
                            user_ans, correct_answer, True, question_choices
                        )
                        
                        if additional_info:
                            st.success(f"{main_msg} {additional_info}")
                        else:
                            st.success(main_msg)
                    else:
                        # 複数問題の場合：全問正解＋各問題の正解を表示
                        st.success("✅ 全問正解！")
                        
                        # 各問題の正解を表示
                        st.markdown("#### 各問題の正解")
                        for qid, q_result in result_data.items():
                            user_ans = ''.join(q_result.get('user_answer', [])) or '無回答'
                            
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
                                correct_answer = q_result.get('correct_answer', '')
                                _, additional_info = QuestionUtils.get_answer_feedback_message(
                                    user_ans, correct_answer, True, question_choices
                                )
                                correct_display = additional_info or f"正解：{correct_answer}"
                            
                            st.success(f"**{qid}**: ✅ 正解！ あなたの解答: `{user_ans}` | 正解：{correct_display}")
                else:
                    # 不正解の場合
                    if total_count == 1:
                        # 単一問題の場合、シンプルな表示
                        qid = list(result_data.keys())[0]
                        q_result = result_data[qid]
                        user_ans = ''.join(q_result.get('user_answer', [])) or '無回答'
                        correct_answer = q_result.get('correct_answer', '')
                        
                        # 問題の選択肢情報を取得
                        question = next((q for q in questions if q.get('number') == qid), None)
                        question_choices = question.get('choices', []) if question else []
                        
                        main_msg, additional_info = QuestionUtils.get_answer_feedback_message(
                            user_ans, correct_answer, False, question_choices
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
                        # 複数問題の場合：全問題の結果を表示
                        st.error(f"❌ {total_count}問中{correct_count}問正解")
                        
                        # 各問題の詳細を表示
                        st.markdown("#### 各問題の解答結果")
                        for qid, q_result in result_data.items():
                            user_ans = ''.join(q_result.get('user_answer', [])) or '無回答'
                            correct_answer = q_result.get('correct_answer', '')
                            is_correct = q_result.get('is_correct', False)
                            
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
                                # 問題の選択肢情報を取得
                                question = next((q for q in questions if q.get('number') == qid), None)
                                question_choices = question.get('choices', []) if question else []
                                
                                _, additional_info = QuestionUtils.get_answer_feedback_message(
                                    user_ans, correct_answer, False, question_choices
                                )
                                correct_display = additional_info or f"正解：{correct_answer}"
                            
                            # 正誤による表示の色分け
                            if is_correct:
                                st.success(f"**{qid}**: ✅ 正解！ あなたの解答: `{user_ans}` | 正解：{correct_display}")
                            else:
                                st.error(f"**{qid}**: ❌ 不正解 あなたの解答: `{user_ans}` | 正解：{correct_display}")

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
        
        # メモセクションを自己評価後に表示
        if is_checked:
            AnswerModeComponent._render_notes_section(questions, group_id)
        
        # 症例画像をフォームの外に表示（通常の問題画像と同じ扱い）
        if case_data and case_data.get('image_urls'):
            with st.expander("📸 症例画像を見る", expanded=is_checked):
                for img_url in case_data.get('image_urls', []):
                    secure_url = get_secure_image_url(img_url)
                    if secure_url:
                        st.image(
                            secure_url, 
                            use_container_width=True  # コンテナ幅に合わせてレスポンシブ表示
                        )
        
        # 各問題の画像（症例画像以外）はフォームの外に表示
        for question in questions:
            all_images = (question.get('image_urls', []) or []) + (question.get('image_paths', []) or [])
            if all_images:
                with st.expander(f"📸 {question.get('number', '')}の図を見る", expanded=is_checked):
                    for img_url in all_images:
                        secure_url = get_secure_image_url(img_url)
                        if secure_url:
                            st.image(
                                secure_url, 
                                use_container_width=True  # コンテナ幅に合わせてレスポンシブ表示
                            )
        
        return action_result

    @staticmethod
    def _render_notes_section(questions: List[Dict], group_id: str) -> None:
        """回答チェック後に表示するメモ入力セクション"""
        st.markdown("---")
        st.markdown("#### 📝 メモ・振り返り")

        uid = st.session_state.get("uid")
        if not uid:
            st.info("ログインするとメモ機能が利用できます。")
            return

        for question in questions:
            qid = question.get('number', '')

            # 過去のメモを表示
            existing_notes = NotesManager.get_question_notes(uid, qid)
            if existing_notes:
                with st.expander(f"📝 {qid}のメモ ({len(existing_notes)}件)", expanded=True):
                    for i, note in enumerate(existing_notes):
                        NotesManager.render_note_display(note)

                        col1, col2 = st.columns([4, 1])
                        with col2:
                            if st.button("🗑️", key=f"del_note_{qid}_{i}_{group_id}"):
                                if NotesManager.delete_note(uid, qid, i):
                                    st.success("削除しました")
                                    st.rerun()

                        st.markdown("---")

            # 新規メモ追加
            st.markdown(f"##### ✍️ {qid}のメモを追加")

            new_note_text = st.text_area(
                f"{qid}のメモ（テキスト）",
                key=f"note_input_{qid}_{group_id}",
                placeholder="間違えた理由、覚えるべきポイント、気づきなどを記録...",
                help="マークダウン記法が使えます（**太字**, - 箇条書き など）"
            )

            uploaded_images = st.file_uploader(
                "画像を追加（複数可）",
                type=["png", "jpg", "jpeg", "gif"],
                accept_multiple_files=True,
                key=f"image_upload_{qid}_{group_id}",
                help="参考画像やスクリーンショットを添付できます"
            )

            if st.button(f"💾 メモを保存", key=f"save_note_{qid}_{group_id}"):
                if new_note_text or uploaded_images:
                    image_urls = []
                    if uploaded_images:
                        with st.spinner("画像をアップロード中..."):
                            for img_file in uploaded_images:
                                img_url = NotesManager.upload_image_to_firebase(uid, qid, img_file)
                                if img_url:
                                    image_urls.append(img_url)

                    if NotesManager.add_note(uid, qid, new_note_text, images=image_urls):
                        st.success(f"✅ メモを保存しました！（画像: {len(image_urls)}枚）")
                        st.rerun()
                    else:
                        st.error("メモの保存に失敗しました")
                else:
                    st.warning("テキストまたは画像を入力してください")
