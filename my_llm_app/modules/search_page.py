"""
検索・進捗ページのモジュール - UI完全保持最適化版

元のUIと完全に一致しながらパフォーマンスを劇的に改善:
- @st.cache_dataを使った重いデータ処理のキャッシュ化（元のUI保持）
- 演習ページとの連携による差分更新
- 元のrender_*_tab_perfect関数群を完全保持
- UserDataExtractorの統合とキャッシュ最適化
- 元の4つのタブ構造とメトリクス表示を完全再現
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import datetime
import math
import pytz
from typing import Dict, List, Any, Optional, Tuple
import time
from functools import lru_cache
from collections import defaultdict, Counter
import hashlib
import json
import re
import random
import sys
import os
import subprocess
import shutil
import tempfile


# 必要なインポート
from utils import JST, get_japan_today, get_japan_datetime_from_timestamp

try:
    from utils import (
        ALL_QUESTIONS, 
        HISSHU_Q_NUMBERS_SET, 
        GAKUSHI_HISSHU_Q_NUMBERS_SET,
        _gather_images_for_questions,
        _image_block_latex,
        export_questions_to_latex_tcb_jsarticle,
        compile_latex_to_pdf,
        extract_year_from_question_number
    )
except ImportError:
    try:
        from ..utils import (
            ALL_QUESTIONS, 
            HISSHU_Q_NUMBERS_SET, 
            GAKUSHI_HISSHU_Q_NUMBERS_SET,
            _gather_images_for_questions,
            _image_block_latex,
            export_questions_to_latex_tcb_jsarticle,
            compile_latex_to_pdf,
            extract_year_from_question_number
        )
    except ImportError:
        # フォールバック: 最小限の定義
        ALL_QUESTIONS = []
        HISSHU_Q_NUMBERS_SET = set()
        GAKUSHI_HISSHU_Q_NUMBERS_SET = set()

try:
    from firestore_db import get_firestore_manager
except ImportError:
    try:
        from ..firestore_db import get_firestore_manager
    except ImportError:
        get_firestore_manager = None

try:
    from constants import LEVEL_COLORS, UNIFIED_LEVEL_ORDER as LEVEL_ORDER
except ImportError:
    try:
        from ..constants import LEVEL_COLORS, UNIFIED_LEVEL_ORDER as LEVEL_ORDER
    except ImportError:
        LEVEL_COLORS = {}
        LEVEL_ORDER = ["未学習", "レベル0", "レベル1", "レベル2", "レベル3", "レベル4", "レベル5", "習得済み"]

try:
    from auth import get_user_permission
except ImportError:
    try:
        from ..auth import get_user_permission
    except ImportError:
        def get_user_permission(): return False

# UserDataExtractor
try:
    from user_data_extractor import UserDataExtractor
    HAS_USER_DATA_EXTRACTOR = True
except ImportError:
    try:
        from ..user_data_extractor import UserDataExtractor
        HAS_USER_DATA_EXTRACTOR = True
    except ImportError:
        UserDataExtractor = None
        HAS_USER_DATA_EXTRACTOR = False

from modules.logic.sm2_service import SM2Service
from modules.logic.progress_service import ProgressService
from modules.components.search_tabs import SearchTabs

def update_session_evaluation_log(question_id: str, quality: int, timestamp: datetime.datetime = None):
    """
    演習ページから呼び出される関数：学習結果をセッション状態に追加（日本時間ベース）
    """
    if timestamp is None:
        timestamp = datetime.datetime.now(JST)  # 日本時間で記録
    
    # セッション状態の評価ログを初期化（存在しない場合）
    if 'evaluation_logs' not in st.session_state:
        st.session_state['evaluation_logs'] = []
    
    # 新しい評価ログを追加
    new_log = {
        'question_id': question_id,
        'quality': quality,
        'timestamp': timestamp
    }
    
    st.session_state['evaluation_logs'].append(new_log)
    
    # ログが多くなりすぎないよう、古いデータを制限（例：最新1000件）
    if len(st.session_state['evaluation_logs']) > 1000:
        st.session_state['evaluation_logs'] = st.session_state['evaluation_logs'][-1000:]

# レベル順序定義（0-5レベルシステム）
LEVEL_ORDER = ["未学習", "レベル0", "レベル1", "レベル2", "レベル3", "レベル4", "レベル5", "習得済み"]


def inject_search_page_styles():
    """iOSライクな柔らかなUIスタイルを常時適用"""
    st.markdown(
        """
        <style>
        :root {
            --ios-bg-start: #f5f7ff;
            --ios-bg-end: #eef1ff;
            --ios-card-bg: rgba(255, 255, 255, 0.92);
            --ios-card-border: rgba(255, 255, 255, 0.55);
            --ios-accent: #5b7fff;
            --ios-accent-soft: rgba(91, 127, 255, 0.18);
        }

        div[data-testid="stAppViewContainer"] {
            background: linear-gradient(180deg, var(--ios-bg-start) 0%, var(--ios-bg-end) 100%);
        }

        section[data-testid="stSidebar"] {
            background: rgba(255, 255, 255, 0.85) !important;
            backdrop-filter: blur(14px);
        }

        .block-container {
            padding-top: 1.2rem;
            padding-bottom: 3rem;
        }

        .ios-hero {
            border-radius: 28px;
            padding: 30px;
            margin-bottom: 1.2rem;
            background: linear-gradient(135deg, #5b7fff 0%, #7f9bff 45%, #a2b7ff 100%);
            color: #ffffff;
            box-shadow: 0 20px 40px rgba(91, 127, 255, 0.25);
            position: relative;
            overflow: hidden;
        }

        .ios-hero::after {
            content: "";
            position: absolute;
            top: -40%;
            right: -30%;
            width: 55%;
            height: 120%;
            background: rgba(255, 255, 255, 0.18);
            filter: blur(0px);
            transform: rotate(25deg);
        }

        .ios-hero__badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 6px 14px;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.3);
            font-size: 0.85rem;
            font-weight: 500;
            letter-spacing: 0.02em;
        }

        .ios-hero__title {
            font-size: 2rem;
            font-weight: 700;
            margin: 12px 0 6px;
        }

        .ios-hero__subtitle {
            font-size: 1rem;
            opacity: 0.92;
            max-width: 520px;
            line-height: 1.7;
        }

        .ios-section-title {
            font-size: 1.08rem;
            font-weight: 600;
            color: #1c1c1e;
            margin-bottom: 0.4rem;
            letter-spacing: 0.01em;
        }

        .ios-hero__chips {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            margin-top: 18px;
        }

        .ios-chip {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding: 6px 14px;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.3);
            color: #ffffff;
            font-size: 0.82rem;
            font-weight: 500;
            letter-spacing: 0.01em;
        }

        div[data-testid="stMetric"] {
            border-radius: 20px;
            padding: 16px 18px;
            background: var(--ios-card-bg);
            border: 1px solid var(--ios-card-border);
            box-shadow: 0 12px 32px rgba(15, 23, 42, 0.08);
        }

        div[data-testid="stMetric"] > div:nth-child(1) {
            color: #636366;
            font-size: 0.85rem;
            font-weight: 500;
        }

        div[data-testid="stMetricValue"] {
            color: #1c1c1e;
            font-size: 1.6rem;
            font-weight: 600;
        }

        div[data-testid="stMetricDelta"] {
            font-size: 0.85rem;
            font-weight: 500;
        }

        div[data-testid="stSlider"] {
            padding: 14px 18px 10px;
            border-radius: 20px;
            background: var(--ios-card-bg);
            border: 1px solid var(--ios-card-border);
            box-shadow: 0 12px 32px rgba(15, 23, 42, 0.07);
        }

        div[data-testid="stSlider"] label {
            font-weight: 600;
            color: #1c1c1e;
        }

        div[data-testid="stSlider"] span {
            color: #636366;
        }

        .stDataFrame {
            border-radius: 20px;
            overflow: hidden;
            box-shadow: 0 12px 32px rgba(15, 23, 42, 0.07);
        }

        .stCaption {
            color: #3a3a3c;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )



def prepare_data_for_display(uid: str, cards: dict, analysis_target: str, force_refresh: bool = False) -> pd.DataFrame:
    """
    最適化されたデータ準備関数（重い処理をキャッシュ）
    """
    return ProgressService.prepare_data_for_display(uid, cards, analysis_target, force_refresh)

def calculate_card_level(card: Dict[str, Any]) -> str:
    """
    【最終改善版】
    自己評価(quality)を重視し、「不安定な正解」でレベルが上がるのを防ぐレベル計算関数
    """
    return SM2Service.calculate_card_level(card)

def calculate_sm2_review_schedule(cards: dict, days_ahead: int = 7) -> Dict[str, List[str]]:
    """
    SM-2アルゴリズムに基づいて復習スケジュールを計算（日本時間ベース）
    """
    return SM2Service.calculate_sm2_review_schedule(cards, days_ahead)

def get_review_priority_cards(cards: dict, target_date: datetime.date = None) -> List[tuple]:
    """
    指定日の復習優先度付きカードリストを取得（日本時間ベース）
    """
    return SM2Service.get_review_priority_cards(cards, target_date)




def check_gakushi_permission(uid: str) -> bool:
    """学士試験へのアクセス権限をチェック（キャッシュ対応）"""
    try:
        # Streamlitのキャッシュを使用して権限データを保存（表示なし）
        @st.cache_data(ttl=300, show_spinner=False)  # 5分間キャッシュ、スピナー非表示
        def _cached_gakushi_check(uid: str) -> bool:
            db = get_firestore_manager()
            user_ref = db.collection('users').document(uid)
            user_doc = user_ref.get()
            
            if user_doc.exists:
                user_data = user_doc.to_dict()
                return user_data.get('has_gakushi_permission', False)
            
            return True
        
        return _cached_gakushi_check(uid)
    except Exception:
        return True

def calculate_progress_metrics(cards: Dict, base_df: pd.DataFrame, uid: str, analysis_target: str) -> Dict:
    """
    進捗メトリクス計算（元のUIと同様）- 日本時間ベース
    """
    return ProgressService.calculate_progress_metrics(cards, base_df, uid, analysis_target)

def render_search_page():
    """
    検索ページのメイン関数（UI完全保持）
    """
    # セッション状態の取得
    uid = st.session_state.get("uid", "guest")
    cards = st.session_state.get("cards", {})
    analysis_target = st.session_state.get("analysis_target", "国試")
    level_filter = st.session_state.get("level_filter", LEVEL_ORDER)
    subject_filter = st.session_state.get("subject_filter", [])

    inject_search_page_styles()

    today_date = get_japan_today()
    today_label = today_date.strftime("%Y/%m/%d (%a)")
    chip_html = []
    chip_html.append(f"<span class='ios-chip'>対象 {analysis_target}</span>")

    st.markdown(
        f"""
        <div class="ios-hero">
            <span class="ios-hero__badge">進捗ビュー</span>
            <div class="ios-hero__title">学習ダッシュボード</div>
            <div class="ios-hero__subtitle">検索・進捗ページでは、演習データをもとに復習量の偏りや達成状況を確認できます。今日 ({today_label}) の指標をチェックして、次の一手を決めましょう。</div>
            <div class="ios-hero__chips">{''.join(chip_html)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 権限チェック
    has_gakushi_permission = st.session_state.get('has_gakushi_permission', False)

    # 最適化されたデータ準備
    base_df = prepare_data_for_display(uid, cards, analysis_target)
    
    # フィルター適用
    filtered_df = base_df.copy()
    
    # レベルフィルター
    if level_filter and set(level_filter) != set(LEVEL_ORDER):
        filtered_df = filtered_df[filtered_df['level'].isin(level_filter)]
    
    # 科目フィルター
    if subject_filter:
        filtered_df = filtered_df[filtered_df['subject'].isin(subject_filter)]
    
    # 必修問題フィルター
    show_hisshu_only = st.session_state.get('show_hisshu_only', False)
    if show_hisshu_only:
        filtered_df = filtered_df[filtered_df['is_hisshu'] == True]
    
    # メトリクス表示（分析対象に基づく正確な計算）
    if not filtered_df.empty:
        # メトリクス計算には全体データ（フィルタされていない）を使用
        metrics = calculate_progress_metrics(cards, base_df, uid, analysis_target)
        
        # デバッグ情報表示（開発時のみ）
        if st.session_state.get("debug_mode", False):
            st.write(f"デバッグ - 現在学習済み問題数({analysis_target}): {metrics['current_studied_count']}, 昨日時点: {metrics['current_studied_count'] - metrics['progress_delta']}, デルタ: {metrics['progress_delta']}")
            st.write(f"デバッグ - 必修現在: {metrics['current_hisshu_studied_count']}, 必修昨日時点: {metrics['current_hisshu_studied_count'] - metrics['hisshu_delta']}, 必修デルタ: {metrics['hisshu_delta']}")
            
            # 全体の練習記録数と現在の分析対象の関係を表示
            total_practice_records = len(st.session_state.get('evaluation_logs', []))
            all_cards = st.session_state.get("cards", {})
            total_learned_all = sum(1 for card in all_cards.values() if card.get('history') and calculate_card_level(card) != "未学習")
            
            st.write(f"デバッグ - 総練習記録数: {total_practice_records}回 | 全分野学習済み: {total_learned_all}問 | {analysis_target}学習済み: {metrics['current_studied_count']}問")
            st.info(f"💡 表示中: {analysis_target}の学習進捗。全分野の合計は{total_learned_all}問です。")
        
        # 4つの主要指標をst.metricで表示
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            progress_delta_text = f"+{metrics['progress_delta']} 問" if metrics['progress_delta'] > 0 else f"{metrics['progress_delta']} 問" if metrics['progress_delta'] < 0 else "変化なし"
            st.metric(
                f"学習進捗率（{analysis_target}）",
                f"{metrics['current_studied_count']} / {metrics['total_count']} 問",
                delta=progress_delta_text,
                help=f"{analysis_target}で学習済みのユニークな問題数です。同じ問題の復習は重複カウントされません。"
            )
        
        with col2:
            hisshu_delta_text = f"+{metrics['hisshu_delta']} 問" if metrics['hisshu_delta'] > 0 else f"{metrics['hisshu_delta']} 問" if metrics['hisshu_delta'] < 0 else "変化なし"
            st.metric(
                "必修問題の進捗",
                f"{metrics['current_hisshu_studied_count']} / {metrics['hisshu_total_count']} 問",
                delta=hisshu_delta_text
            )
        
        with col3:
            today_delta = metrics['today_study_count'] - metrics['yesterday_study_count']
            today_delta_text = f"+{today_delta}" if today_delta > 0 else f"{today_delta}" if today_delta < 0 else "±0"
            st.metric(
                "今日の学習",
                f"{metrics['today_study_count']} 問",
                delta=f"昨日比 {today_delta_text}"
            )
        
        with col4:
            accuracy_delta_text = f"+{metrics['accuracy_delta']:.1f}%" if metrics['accuracy_delta'] > 0 else f"{metrics['accuracy_delta']:.1f}%" if metrics['accuracy_delta'] < 0 else "±0%"
            st.metric(
                "直近の正解率",
                f"{metrics['recent_accuracy']:.1f}%",
                delta=f"前週比 {accuracy_delta_text}"
            )
        

    
    
    # タブの作成
    tab1, tab2, tab3, tab4 = st.tabs(["📊 進捗グラフ", "📈 分析", "📝 問題リスト", "🔍 キーワード検索"])
    
    with tab1:
        SearchTabs.render_overview_tab_perfect(filtered_df, base_df, ALL_QUESTIONS, analysis_target)
    
    with tab2:
        SearchTabs.render_graph_analysis_tab_perfect(filtered_df, base_df, analysis_target)
    
    with tab3:
        SearchTabs.render_question_list_tab_perfect(filtered_df, analysis_target)
    
    with tab4:
        SearchTabs.render_keyword_search_tab_perfect(analysis_target)

def render_search_sidebar():
    """
    検索・進捗ページのサイドバーを描画
    """
    # 検索・分析用のフィルター機能のみ
    uid = st.session_state.get("uid")
    has_gakushi_permission = st.session_state.get('has_gakushi_permission', False) # Assuming get_user_permission refers to this session state variable

    st.markdown("#### 🔍 表示フィルター")

    # 対象範囲
    if has_gakushi_permission:
        analysis_target = st.radio("分析対象", ["国試", "学士試験"], key="analysis_target")
    else:
        analysis_target = "国試"

    # 分析対象が変更された場合、科目リストを更新
    if analysis_target != st.session_state.get("previous_analysis_target"):
        st.session_state["previous_analysis_target"] = analysis_target
        # 科目データを再初期化するためにリロード
        st.rerun()

    # 学習レベルフィルター
    level_filter = st.multiselect(
        "学習レベル",
        LEVEL_ORDER,
        default=LEVEL_ORDER,
        key="level_filter"
    )

    # 科目フィルター（分析対象に応じて動的に変更）
    if "available_subjects" in st.session_state:
        # subject_filterの初期化（Session State経由で管理）
        if 'subject_filter' not in st.session_state:
            st.session_state.subject_filter = st.session_state.available_subjects
        
        # 分析対象に応じた科目フィルターのラベル
        subject_label = f"表示する科目 ({analysis_target})"
        subject_filter = st.multiselect(
            subject_label,
            st.session_state.available_subjects,
            key="subject_filter"
        )
    else:
        subject_filter = []

    





# メイン関数
def main():
    """モジュールのメイン関数"""
    render_search_page()

if __name__ == "__main__":
    main()
