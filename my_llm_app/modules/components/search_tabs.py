import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import datetime
import random
import re
from typing import List, Dict, Any

from utils import (
    ALL_QUESTIONS, 
    HISSHU_Q_NUMBERS_SET, 
    GAKUSHI_HISSHU_Q_NUMBERS_SET,
    _gather_images_for_questions,
    _image_block_latex,
    export_questions_to_latex_tcb_jsarticle,
    compile_latex_to_pdf,
    extract_year_from_question_number,
    get_japan_today,
    get_japan_datetime_from_timestamp
)
from constants import (
    LEVEL_ORDER, LEVEL_COLORS, 
    KOKUSHI_BASIC_SUBJECTS, KOKUSHI_CLINICAL_SUBJECTS,
    GAKUSHI_BASIC_SUBJECTS, GAKUSHI_CLINICAL_SUBJECTS
)
from modules.logic.sm2_service import SM2Service


class SearchTabs:
    """検索ページのタブ描画を担当するクラス"""

    @staticmethod
    def render_overview_tab_perfect(filtered_df: pd.DataFrame, base_df: pd.DataFrame, all_questions: List, analysis_target: str):
        """
        概要タブ - 学習状況サマリー
        """
        st.subheader("📊 学習状況サマリー")
        
        # 正答率計算ヘルパー関数
        def calculate_accuracy(df):
            if df.empty:
                return 0.0
            
            total_correct = 0
            total_attempts = 0
            
            for _, row in df.iterrows():
                history = row.get('history', [])
                if history:
                    # 最新の学習履歴を使用するか、全履歴を使用するか
                    # ここでは全履歴からの正答率を計算（ユーザーの要望に合わせて調整可能）
                    correct_count = sum(1 for h in history if h.get('quality', 0) >= 3)
                    total_correct += correct_count
                    total_attempts += len(history)
            
            return (total_correct / total_attempts * 100) if total_attempts > 0 else 0.0

        # 1. 全体の正答率
        total_accuracy = calculate_accuracy(base_df)
        
        # 2. 必修の平均正答率
        hisshu_df = base_df[base_df['is_hisshu']]
        hisshu_accuracy = calculate_accuracy(hisshu_df)
        
        # 3. 一般の平均正答率
        general_df = base_df[base_df['is_general']]
        general_accuracy = calculate_accuracy(general_df)
        
        # 4. 臨実の平均正答率
        clinical_df = base_df[base_df['is_clinical']]
        clinical_accuracy = calculate_accuracy(clinical_df)
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("全体の正答率", f"{total_accuracy:.1f}%")
        with col2:
            st.metric("必修の平均正答率", f"{hisshu_accuracy:.1f}%")
        with col3:
            st.metric("一般の平均正答率", f"{general_accuracy:.1f}%")
        with col4:
            st.metric("臨実の平均正答率", f"{clinical_accuracy:.1f}%")

        # レベル分布の可視化
        level_counts = filtered_df['level'].value_counts().reindex(LEVEL_ORDER, fill_value=0)
        
        level_colors_map = {
            "未学習": "#757575", "レベル0": "#FF9800", "レベル1": "#FFC107",
            "レベル2": "#8BC34A", "レベル3": "#9C27B0", "レベル4": "#03A9F4",
            "レベル5": "#1E88E5", "習得済み": "#4CAF50"
        }
        
        fig = px.bar(
            x=level_counts.index,
            y=level_counts.values,
            labels={'x': '学習レベル', 'y': '問題数'},
            title=f"{analysis_target} レベル別分布",
            color=level_counts.index,
            color_discrete_map=level_colors_map
        )
        st.plotly_chart(fig, use_container_width=True, key="overview_level_dist")

    @staticmethod
    def render_graph_analysis_tab_perfect(filtered_df: pd.DataFrame, base_df: pd.DataFrame, analysis_target: str):
        """
        グラフ分析タブ - 学習データの可視化
        """
        st.subheader("📈 詳細分析")
        
        if filtered_df.empty:
            st.info("データがありません。")
            return

        # 科目別進捗
        subject_counts = filtered_df.groupby('subject').size().reset_index(name='count')
        subject_studied = filtered_df[filtered_df['level'] != '未学習'].groupby('subject').size().reset_index(name='studied')
        
        subject_data = pd.merge(subject_counts, subject_studied, on='subject', how='left').fillna(0)
        subject_data['progress'] = subject_data['studied'] / subject_data['count'] * 100
        
        # --- レーダーチャートの追加 ---
        
        # analysis_targetに基づいて科目リストを選択
        if analysis_target == "学士試験":
            basic_subjects = GAKUSHI_BASIC_SUBJECTS
            clinical_subjects = GAKUSHI_CLINICAL_SUBJECTS
        else:
            basic_subjects = KOKUSHI_BASIC_SUBJECTS
            clinical_subjects = KOKUSHI_CLINICAL_SUBJECTS
            
        # 科目ごとの正答率を計算
        subject_accuracy_map = {}
        for subject in subject_counts['subject']:
            # その科目の問題を抽出
            subject_df = filtered_df[filtered_df['subject'] == subject]
            if subject_df.empty:
                subject_accuracy_map[subject] = 0.0
                continue
                
            total_correct = 0
            total_attempts = 0
            
            for _, row in subject_df.iterrows():
                history = row.get('history', [])
                if history:
                    correct_count = sum(1 for h in history if h.get('quality', 0) >= 3)
                    total_correct += correct_count
                    total_attempts += len(history)
            
            accuracy = (total_correct / total_attempts * 100) if total_attempts > 0 else 0.0
            subject_accuracy_map[subject] = accuracy
            
        # データフレームに正答率を追加
        subject_data['accuracy'] = subject_data['subject'].map(subject_accuracy_map)
        
        # 基礎科目と臨床科目のデータ抽出（正答率を使用）
        basic_data = subject_data[subject_data['subject'].isin(basic_subjects)].copy()
        clinical_data = subject_data[subject_data['subject'].isin(clinical_subjects)].copy()
        
        def create_radar_chart(df, title):
            if df.empty:
                return None
            
            # 閉じた多角形にするために最初のデータを最後に追加
            subjects = df['subject'].tolist()
            values = df['accuracy'].tolist()  # 正答率を使用
            
            # データが1つ以上ある場合のみ処理
            if not subjects:
                return None
                
            subjects.append(subjects[0])
            values.append(values[0])
            
            fig = go.Figure(data=go.Scatterpolar(
                r=values,
                theta=subjects,
                fill='toself',
                name=title
            ))
            
            fig.update_layout(
                polar=dict(
                    radialaxis=dict(
                        visible=True,
                        range=[0, 100]
                    )
                ),
                title=title,
                showlegend=False
            )
            return fig

        col1, col2 = st.columns(2)
        
        with col1:
            fig_basic = create_radar_chart(basic_data, "基礎科目 正答率")
            if fig_basic:
                st.plotly_chart(fig_basic, use_container_width=True, key="radar_basic")
            else:
                st.info("基礎科目のデータがありません")
                
        with col2:
            fig_clinical = create_radar_chart(clinical_data, "臨床科目 正答率")
            if fig_clinical:
                st.plotly_chart(fig_clinical, use_container_width=True, key="radar_clinical")
            else:
                st.info("臨床科目のデータがありません")
        
        st.divider()
        st.subheader("📊 全科目詳細")

        subject_data = subject_data.sort_values('progress', ascending=True)
        
        fig_progress = px.bar(
            subject_data,
            x='progress',
            y='subject',
            orientation='h',
            title=f"{analysis_target} 科目別進捗率",
            labels={'progress': '進捗率 (%)', 'subject': '科目'},
            text=subject_data['progress'].apply(lambda x: f"{x:.1f}%")
        )
        st.plotly_chart(fig_progress, use_container_width=True, key="analysis_subject_progress")
        
        # 正解率分析（学習履歴がある場合）
        st.markdown("#### 科目別正解率")
        
        # 各問題の最新の正解率を計算（quality >= 3 を正解とする）
        subject_accuracy = []
        
        for subject in filtered_df['subject'].unique():
            subject_df = filtered_df[filtered_df['subject'] == subject]
            total_attempts = 0
            correct_attempts = 0
            
            for _, row in subject_df.iterrows():
                history = row.get('history', [])
                if history:
                    total_attempts += len(history)
                    correct_attempts += sum(1 for h in history if h.get('quality', 0) >= 3)
            
            if total_attempts > 0:
                accuracy = (correct_attempts / total_attempts * 100)
                subject_accuracy.append({'subject': subject, 'accuracy': accuracy, 'attempts': total_attempts})
        
        if subject_accuracy:
            acc_df = pd.DataFrame(subject_accuracy).sort_values('accuracy', ascending=True)
            
            fig_acc = px.bar(
                acc_df,
                x='accuracy',
                y='subject',
                orientation='h',
                title=f"{analysis_target} 科目別正解率",
                labels={'accuracy': '正解率 (%)', 'subject': '科目'},
                text=acc_df['accuracy'].apply(lambda x: f"{x:.1f}%"),
                color='accuracy',
                color_continuous_scale='RdYlGn'
            )
            st.plotly_chart(fig_acc, use_container_width=True, key="analysis_subject_accuracy")
        else:
            st.info("学習履歴がまだありません。")

    @staticmethod
    def render_question_list_tab_perfect(filtered_df: pd.DataFrame, analysis_target: str = "国試"):
        """
        問題リストタブ - 問題リスト
        """
        st.subheader("問題リスト")
        level_colors = {
            "未学習": "#757575", "レベル0": "#FF9800", "レベル1": "#FFC107",
            "レベル2": "#8BC34A", "レベル3": "#9C27B0", "レベル4": "#03A9F4",
            "レベル5": "#1E88E5", "習得済み": "#4CAF50"
        }

        # 権限チェック
        has_gakushi_permission = st.session_state.get("has_gakushi_permission", False)

        # サイドバーのフィルターを適用
        if not filtered_df.empty:
            st.markdown(f"**{len(filtered_df)}件の問題が見つかりました**")
            
            def sort_key(row_id):
                m_gakushi = re.match(r'^(G)(\d+)[–\-]([\d–\-再]+)[–\-]([A-Z])[–\-](\d+)$', str(row_id))
                if m_gakushi: return (m_gakushi.group(1), int(m_gakushi.group(2)), m_gakushi.group(3), m_gakushi.group(4), int(m_gakushi.group(5)))
                m_normal = re.match(r"(\d+)([A-D])(\d+)", str(row_id))
                if m_normal: return ('Z', int(m_normal.group(1)), m_normal.group(2), '', int(m_normal.group(3)))
                return ('Z', 0, '', '', 0)

            detail_filtered_sorted = filtered_df.copy()
            detail_filtered_sorted['sort_key'] = detail_filtered_sorted['id'].apply(sort_key)
            detail_filtered_sorted = detail_filtered_sorted.sort_values(by='sort_key').drop(columns=['sort_key'])
            
            # ページネーション（簡易的）
            page_size = 50
            total_pages = (len(detail_filtered_sorted) - 1) // page_size + 1
            page = st.number_input("ページ", min_value=1, max_value=total_pages, value=1) if total_pages > 1 else 1
            
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            
            current_page_df = detail_filtered_sorted.iloc[start_idx:end_idx]
            
            for _, row in current_page_df.iterrows():
                # 権限チェック：学士試験の問題で権限がない場合はスキップ
                if str(row.id).startswith("G") and not has_gakushi_permission:
                    continue

                st.markdown(
                    f"<div style='margin-bottom: 5px; padding: 5px; border-left: 5px solid {level_colors.get(row.level, '#888')};'>"
                    f"<span style='display:inline-block;width:80px;font-weight:bold;color:{level_colors.get(row.level, '#888')};'>{row.level}</span>"
                    f"<span style='font-size:1.1em;'>{row.id}</span>"
                    f"</div>",
                    unsafe_allow_html=True
                )
        else:
            st.info("表示する問題がありません。")

    @staticmethod
    def render_keyword_search_tab_perfect(analysis_target: str):
        """
        キーワード検索タブ - キーワード検索
        """
        # 権限チェック
        has_gakushi_permission = st.session_state.get("has_gakushi_permission", False)
        
        # キーワード検索フォーム（サイドバーフィルター連動）
        st.subheader("🔍 キーワード検索")
        st.info(f"🎯 検索対象: {analysis_target} （サイドバーの分析対象フィルターで変更可能）")

        col1, col2 = st.columns([4, 1])
        with col1:
            search_keyword = st.text_input("検索キーワード", placeholder="検索したいキーワードを入力", key="search_keyword_input")
        with col2:
            shuffle_results = st.checkbox("結果をシャッフル", key="shuffle_checkbox")

        search_btn = st.button("検索実行", type="primary", use_container_width=True)

        # キーワード検索の実行と結果表示
        if search_btn and search_keyword.strip():
            # キーワード検索を実行
            search_words = [word.strip() for word in search_keyword.strip().split() if word.strip()]

            keyword_results = []
            for q in ALL_QUESTIONS:
                # 権限チェック：学士試験の問題で権限がない場合はスキップ
                question_number = q.get('number', '')
                if question_number.startswith("G") and not has_gakushi_permission:
                    continue

                # 分析対象フィルタチェック（サイドバーの設定を使用）
                if analysis_target == "学士試験" and not question_number.startswith("G"):
                    continue
                elif analysis_target == "国試" and question_number.startswith("G"):
                    continue

                # キーワード検索
                text_to_search = f"{q.get('question', '')} {q.get('subject', '')} {q.get('number', '')}"
                if any(word.lower() in text_to_search.lower() for word in search_words):
                    keyword_results.append(q)

            # シャッフル処理
            if shuffle_results:
                random.shuffle(keyword_results)

            # 結果をセッション状態に保存
            st.session_state["search_results"] = keyword_results
            st.session_state["search_query"] = search_keyword.strip()
            st.session_state["search_page_analysis_target"] = analysis_target
            st.session_state["search_page_shuffle_setting"] = shuffle_results

        # 検索結果の表示
        if "search_results" in st.session_state:
            results = st.session_state["search_results"]
            query = st.session_state.get("search_query", "")
            search_type = st.session_state.get("search_page_analysis_target", "国試")
            shuffle_info = "（シャッフル済み）" if st.session_state.get("search_page_shuffle_setting", False) else "（順番通り）"

            if results:
                st.success(f"「{query}」で{len(results)}問見つかりました（{search_type}）{shuffle_info}")

                # 結果の統計を表示
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("検索結果", f"{len(results)}問")
                with col2:
                    subjects = [q.get("subject", "未分類") for q in results]
                    unique_subjects = len(set(subjects))
                    st.metric("関連科目", f"{unique_subjects}科目")
                with col3:
                    years = []
                    for q in results:
                        year = extract_year_from_question_number(q.get("number", ""))
                        if year is not None:
                            years.append(int(year))

                    year_range = f"{min(years)}-{max(years)}" if years else "不明"
                    st.metric("年度範囲", year_range)

                # 検索結果の詳細表示
                st.subheader("検索結果")

                # レベル別色分け定義
                level_colors = {
                    "未学習": "#757575", "レベル0": "#FF9800", "レベル1": "#FFC107",
                    "レベル2": "#8BC34A", "レベル3": "#9C27B0", "レベル4": "#03A9F4",
                    "レベル5": "#1E88E5", "習得済み": "#4CAF50"
                }

                for i, q in enumerate(results[:20]):  # 最初の20件を表示
                    # 権限チェック：学士試験の問題で権限がない場合はスキップ
                    question_number = q.get('number', '')
                    if question_number.startswith("G") and not has_gakushi_permission:
                        continue

                    # 学習レベルの取得
                    card = st.session_state.get('cards', {}).get(question_number, {})
                    if not card:
                        level = "未学習"
                    else:
                        card_level = SM2Service.calculate_card_level(card)
                        if card_level == "習得済み" or (isinstance(card_level, int) and card_level >= 6):
                            level = "習得済み"
                        elif isinstance(card_level, int):
                            level = f"レベル{card_level}"
                        else:
                            level = card_level

                    # 必修問題チェック
                    if search_type == "学士試験":
                        is_hisshu = question_number in GAKUSHI_HISSHU_Q_NUMBERS_SET
                    else:
                        is_hisshu = question_number in HISSHU_Q_NUMBERS_SET

                    level_color = level_colors.get(level, "#888888")
                    hisshu_mark = "🔥" if is_hisshu else ""

                    with st.expander(f"● {q.get('number', 'N/A')} - {q.get('subject', '未分類')} {hisshu_mark}"):
                        # レベルを大きく色付きで表示  
                        st.markdown(f"**学習レベル:** <span style='color: {level_color}; font-weight: bold; font-size: 1.2em;'>{level}</span>", unsafe_allow_html=True)
                        st.markdown(f"**問題:** {q.get('question', '')[:100]}...")
                        if q.get('choices'):
                            st.markdown("**選択肢:**")
                            for j, choice in enumerate(q['choices']):  # 全ての選択肢を表示
                                choice_text = choice.get('text', str(choice)) if isinstance(choice, dict) else str(choice)
                                st.markdown(f"  {chr(65+j)}. {choice_text[:50]}...")

                        # 学習履歴の表示
                        if card and card.get('history'):
                            st.markdown(f"**学習履歴:** {len(card['history'])}回")
                            for j, review in enumerate(card['history'][-3:]):  # 最新3件
                                if isinstance(review, dict):
                                    timestamp = review.get('timestamp', '不明')
                                    quality = review.get('quality', 0)
                                    quality_emoji = "✅" if quality >= 4 else "❌"
                                    st.markdown(f"  {j+1}. {timestamp} - 評価: {quality} {quality_emoji}")
                        else:
                            st.markdown("**学習履歴:** なし")

                if len(results) > 20:
                    st.info(f"表示は最初の20件です。全{len(results)}件中")

                # PDF生成とダウンロード機能
                st.markdown("#### 📄 PDF生成")

                colA, colB = st.columns(2)
                with colA:
                    if st.button("📄 PDFを生成", key="pdf_tcb_js_generate"):
                        with st.spinner("PDFを生成中..."):
                            # 1) LaTeX本文（右上は固定の'◯◯◯◯◯'を表示）
                            latex_tcb = export_questions_to_latex_tcb_jsarticle(results)
                            # 2) 画像収集（URL/Storage問わず）
                            assets, per_q_files = _gather_images_for_questions(results)
                            # 3) 画像スロットを includegraphics に差し替え
                            for i, files in enumerate(per_q_files, start=1):
                                block = _image_block_latex(files)
                                latex_tcb = latex_tcb.replace(rf"%__IMAGES_SLOT__{i}__", block)
                            # 4) コンパイル
                            pdf_bytes, log = compile_latex_to_pdf(latex_tcb, assets=assets)
                            if pdf_bytes:
                                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                                st.session_state["pdf_bytes_tcb_js"] = pdf_bytes
                                st.session_state["pdf_filename_tcb_js"] = f"dental_questions_tcb_js_{ts}.pdf"
                                st.success("✅ PDFの生成に成功しました。右のボタンからDLできます。")
                            else:
                                st.error("❌ PDF生成に失敗しました。")
                                with st.expander("ログを見る"):
                                    st.code(log or "no log", language="text")

                with colB:
                    if "pdf_bytes_tcb_js" in st.session_state:
                        # 統一されたPDFダウンロード（新タブで開く）
                        pdf_data = st.session_state["pdf_bytes_tcb_js"]
                        filename = st.session_state.get("pdf_filename_tcb_js", "dental_questions_tcb_js.pdf")

                        # Base64エンコード
                        import base64
                        b64_pdf = base64.b64encode(pdf_data).decode()

                        # Data URI を持つHTMLリンクを生成（新タブで開く）
                        href = f'<a href="data:application/pdf;base64,{b64_pdf}" download="{filename}" target="_blank" style="display: inline-block; padding: 12px; background-color: #ff6b6b; color: white; text-decoration: none; border-radius: 6px; text-align: center; width: 100%; font-size: 16px; font-weight: bold; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">📥 PDFをダウンロード</a>'

                        st.markdown(href, unsafe_allow_html=True)
                    else:
                        st.button("⬇️ PDFをDL", disabled=True, use_container_width=True)

            else:
                st.warning(f"「{query}」に該当する問題が見つかりませんでした")
        else:
            st.info("キーワードを入力して検索してください")
