"""
歯科国家試験対策アプリ - メインファイル（リファクタリング版）

主な変更点:
- モジュール化された構造
- UID統一によるユーザー管理
- パフォーマンス最適化
- セキュリティ強化
"""

import streamlit as st
import datetime
import time
import re
import random
from typing import Optional

# モジュールのインポート
from auth import AuthManager, CookieManager, call_cloud_function
from firestore_db import get_firestore_manager, check_gakushi_permission
from utils import (
    ALL_QUESTIONS, 
    log_to_ga, 
    HISSHU_Q_NUMBERS_SET, 
    GAKUSHI_HISSHU_Q_NUMBERS_SET, 
    AnalyticsUtils
)
from modules.practice_page import render_practice_page, render_practice_sidebar
from modules.updated_ranking_page import render_updated_ranking_page
# from enhanced_analytics import enhanced_ga, EnhancedGoogleAnalytics

# 最適化モジュールのインポート
from enhanced_firestore_optimizer import get_cached_firestore_optimizer
from optimized_weekly_ranking import OptimizedWeeklyRankingSystem
from complete_migration_system import CompleteMigrationSystem
from performance_optimizer import (
    PerformanceOptimizer, 
    CachedDataManager, 
    UIOptimizer, 
    apply_performance_optimizations
)

# 科目マッピングのインポート
from subject_mapping import get_standardized_subject, get_all_standardized_subjects, analyze_subject_mapping


def apply_sidebar_button_styles():
    """
    サイドバーのボタンにスタイリッシュなデザインを適用する関数
    """
    st.markdown("""
    <style>
    /* サイドバーのプライマリボタンのスタイル */
    .stSidebar .stButton > button[kind="primary"] {
        background-color: #0066cc !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        padding: 0.5rem 1rem !important;
        transition: all 0.3s ease !important;
        box-shadow: 0 2px 4px rgba(0, 102, 204, 0.2) !important;
    }

    /* プライマリボタンのホバー効果 */
    .stSidebar .stButton > button[kind="primary"]:hover {
        background-color: #0052a3 !important;
        color: white !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 8px rgba(0, 82, 163, 0.3) !important;
    }

    /* セカンダリボタンのスタイル */
    .stSidebar .stButton > button[kind="secondary"] {
        background-color: #f8f9fa !important;
        color: #0066cc !important;
        border: 2px solid #0066cc !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        padding: 0.5rem 1rem !important;
        transition: all 0.3s ease !important;
    }

    /* セカンダリボタンのホバー効果 */
    .stSidebar .stButton > button[kind="secondary"]:hover {
        background-color: #0066cc !important;
        color: white !important;
        border-color: #0052a3 !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 8px rgba(0, 102, 204, 0.2) !important;
    }

    /* 通常ボタンのスタイル */
    .stSidebar .stButton > button {
        background-color: #6c757d !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 500 !important;
        padding: 0.5rem 1rem !important;
        transition: all 0.3s ease !important;
        width: auto !important;
        min-width: 120px !important;
        max-width: 200px !important;
    }

    /* 通常ボタンのホバー効果 */
    .stSidebar .stButton > button:hover {
        background-color: #5a6268 !important;
        color: white !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 8px rgba(108, 117, 125, 0.2) !important;
    }

    /* フォーカス時のアウトライン除去 */
    .stSidebar .stButton > button:focus {
        outline: none !important;
        box-shadow: 0 0 0 3px rgba(0, 102, 204, 0.3) !important;
    }
    </style>
    """, unsafe_allow_html=True)


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


# アプリバージョン
APP_VERSION = "2024-08-24-refactored"

# ページ設定
st.set_page_config(
    page_title="歯科国試アプリ | AI対策システム",
    page_icon="🦷",
    layout="wide",
    initial_sidebar_state="expanded"
)

# スタイル設定
st.markdown("""
<style>
/* カラーパレット定義 */
:root {
    --primary-color: #1c83e1;     /* 明るい青 (Streamlitのアクセント色に近い) */
    --primary-hover: #1a73c7;     /* 少し暗い青 */
    --primary-light: rgba(28, 131, 225, 0.1);  /* 淡い青背景 */
    --secondary-color: #4caf50;   /* 緑（正解表示等に使用） */
    --danger-color: #f44336;      /* 赤（エラー表示等に使用） */
    --warning-color: #ff9800;     /* オレンジ（警告表示等に使用） */
    --background-light: #f8f9fa;  /* 明るいグレー背景 */
    --border-color: #e0e0e0;      /* ボーダーカラー */
    --text-primary: #2c3e50;      /* 濃いグレー文字 */
    --text-secondary: #6c757d;    /* セカンダリ文字 */
}

/* ライトモード固定設定 */
.stApp {
    background-color: #ffffff;
    color: var(--text-primary);
}

.stSidebar {
    background-color: var(--background-light);
}

/* プライマリボタンのスタイル統一 */
.stButton > button[kind="primary"] {
    background-color: var(--primary-color) !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 500 !important;
    transition: all 0.2s ease !important;
    box-shadow: 0 2px 4px rgba(28, 131, 225, 0.2) !important;
}

.stButton > button[kind="primary"]:hover {
    background-color: var(--primary-hover) !important;
    color: white !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 8px rgba(28, 131, 225, 0.3) !important;
}

.stButton > button[kind="primary"]:focus {
    background-color: var(--primary-color) !important;
    color: white !important;
    box-shadow: 0 0 0 0.2rem rgba(28, 131, 225, 0.25) !important;
}

/* セカンダリボタンのスタイル */
.stButton > button[kind="secondary"] {
    background-color: transparent !important;
    color: var(--primary-color) !important;
    border: 2px solid var(--primary-color) !important;
    border-radius: 8px !important;
    font-weight: 500 !important;
    transition: all 0.2s ease !important;
}

.stButton > button[kind="secondary"]:hover {
    background-color: var(--primary-light) !important;
    color: var(--primary-hover) !important;
    border-color: var(--primary-hover) !important;
}

/* セレクトボックスのスタイル改善 */
.stSelectbox > div > div {
    border-radius: 8px !important;
    border-color: var(--border-color) !important;
}

.stSelectbox > div > div:focus-within {
    border-color: var(--primary-color) !important;
    box-shadow: 0 0 0 0.2rem rgba(28, 131, 225, 0.25) !important;
}

/* マルチセレクトのスタイル改善 */
.stMultiSelect > div > div {
    border-radius: 8px !important;
    border-color: var(--border-color) !important;
}

.stMultiSelect > div > div:focus-within {
    border-color: var(--primary-color) !important;
    box-shadow: 0 0 0 0.2rem rgba(28, 131, 225, 0.25) !important;
}

/* アラートのスタイル統一 */
.stAlert {
    border-radius: 8px !important;
    border: 1px solid var(--border-color) !important;
}

/* 情報アラート */
.stAlert[data-baseweb="notification"] {
    background-color: var(--primary-light) !important;
    border-color: var(--primary-color) !important;
}

/* 問題カードのスタイル */
.question-card {
    background-color: var(--background-light);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    padding: 24px;
    margin: 16px 0;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
    transition: all 0.2s ease;
}

.question-card:hover {
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
    transform: translateY(-2px);
}

/* メトリクスのスタイル */
.metric-container {
    background-color: var(--background-light);
    padding: 20px;
    border-radius: 12px;
    border-left: 4px solid var(--primary-color);
    margin: 12px 0;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
}

/* 正解・不正解の色 */
.correct-answer {
    color: var(--secondary-color) !important;
    font-weight: 600 !important;
}

.incorrect-answer {
    color: var(--danger-color) !important;
    font-weight: 600 !important;
}

/* プログレスバーのスタイル */
.stProgress > div > div > div > div {
    background-color: var(--primary-color) !important;
}

/* タブのスタイル改善 - シンプルなデザイン */
.stTabs [data-baseweb="tab-list"] {
    gap: 0px;
    border-bottom: 1px solid var(--border-color);
}

.stTabs [data-baseweb="tab"] {
    border-radius: 0px !important;
    padding: 12px 20px !important;
    background-color: transparent !important;
    color: var(--text-secondary) !important;
    border: none !important;
    border-bottom: 2px solid transparent !important;
    transition: all 0.2s ease !important;
    font-weight: 400 !important;
}

.stTabs [data-baseweb="tab"]:hover {
    background-color: transparent !important;
    color: var(--primary-color) !important;
    border-bottom: 2px solid var(--primary-color) !important;
}

.stTabs [aria-selected="true"] {
    background-color: transparent !important;
    color: var(--primary-color) !important;
    border-bottom: 2px solid var(--primary-color) !important;
    font-weight: 600 !important;
}

/* タブハイライト要素を非表示にして重複下線を除去 */
.stTabs [data-baseweb="tab-highlight"] {
    display: none !important;
}

/* 代替案: ハイライト要素の高さを0にして非表示 */
.stTabs .st-c2.st-cz {
    height: 0 !important;
    opacity: 0 !important;
    visibility: hidden !important;
}

/* シンプルなデフォルトラジオボタン */
.stRadio {
    /* デフォルトのStreamlitラジオボタンを使用 */
}

/* 通常ボタンのスタイル（青色統一） */
.stButton > button {
    background-color: var(--primary-color) !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 500 !important;
    padding: 0.5rem 1rem !important;
    transition: all 0.2s ease !important;
    box-shadow: 0 2px 4px rgba(28, 131, 225, 0.2) !important;
}

.stButton > button:hover {
    background-color: var(--primary-hover) !important;
    color: white !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 8px rgba(28, 131, 225, 0.3) !important;
}

.stButton > button:focus {
    background-color: var(--primary-color) !important;
    color: white !important;
    box-shadow: 0 0 0 0.2rem rgba(28, 131, 225, 0.25) !important;
}


/* チェックボックスのスタイル統一 */
.stCheckbox > div > label {
    display: flex !important;
    align-items: center !important;
    gap: 12px !important;
    padding: 8px 12px !important;
    border-radius: 8px !important;
    border: 2px solid transparent !important;
    background-color: transparent !important;
    transition: all 0.2s ease !important;
    cursor: default !important;
    margin: 4px 0 !important;
    pointer-events: none !important; /* ラベル全体のクリックを無効化 */
}

/* チェックボックス本体のスタイル（クリック可能な部分のみ） */
.stCheckbox > div > label > div:first-child {
    width: 24px !important;
    height: 24px !important;
    border: 2px solid var(--border-color) !important;
    border-radius: 6px !important;
    background-color: white !important;
    transition: all 0.2s ease !important;
    cursor: pointer !important;
    flex-shrink: 0 !important;
    position: relative !important;
    pointer-events: auto !important; /* チェックボックス本体のみクリック可能 */
}

.stCheckbox > div > label > div:first-child:hover {
    border-color: var(--primary-hover) !important;
    background-color: var(--primary-light) !important;
}

/* チェックマーク表示 */
.stCheckbox > div > label[data-checked="true"] > div:first-child {
    border-color: var(--primary-color) !important;
    background-color: var(--primary-color) !important;
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 16 16' fill='white' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M13.854 3.646a.5.5 0 0 1 0 .708l-7 7a.5.5 0 0 1-.708 0l-3.5-3.5a.5.5 0 1 1 .708-.708L6.5 10.293l6.646-6.647a.5.5 0 0 1 .708 0z'/%3E%3C/svg%3E") !important;
    background-repeat: no-repeat !important;
    background-position: center !important;
    background-size: 16px 16px !important;
}

/* テキスト部分は非クリック可能 */
.stCheckbox > div > label > span {
    cursor: text !important;
    pointer-events: none !important;
    user-select: text !important; /* テキスト選択可能 */
}

/* 選択状態のラベル全体の背景削除 */
.stCheckbox > div > label[data-checked="true"] {
    border-color: transparent !important;
    background-color: transparent !important;
}


}

/* ヘッダーのスタイル */
h1 {
    color: var(--text-primary) !important;
    font-weight: 700 !important;
}

h2, h3 {
    color: var(--text-primary) !important;
    font-weight: 600 !important;
}

/* サイドバー専用のスタイル */
.stSidebar .stButton > button[kind="primary"] {
    width: 100% !important;
    margin: 4px 0 !important;
}

.stSidebar h1, .stSidebar h2, .stSidebar h3 {
    color: var(--text-primary) !important;
}

/* カスタムコンポーネントのスタイル */
.case-info-box {
    background-color: var(--primary-light) !important;
    padding: 16px 20px !important;
    border-radius: 12px !important;
    border-left: 4px solid var(--primary-color) !important;
    margin-bottom: 20px !important;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05) !important;
}

.case-info-box strong,
.case-info-box span {
    color: var(--text-primary) !important;
}

/* 選択肢ボタンのスタイル */
.choice-button {
    margin: 4px 0 !important;
    width: 100% !important;
}

.choice-button button {
    text-align: left !important;
    padding: 12px 16px !important;
    border-radius: 8px !important;
}

/* 結果表示のスタイル */
.result-correct {
    background-color: rgba(76, 175, 80, 0.1) !important;
    border: 2px solid var(--secondary-color) !important;
    border-radius: 8px !important;
    padding: 16px !important;
    margin: 12px 0 !important;
}

.result-incorrect {
    background-color: rgba(244, 67, 54, 0.1) !important;
    border: 2px solid var(--danger-color) !important;
    border-radius: 8px !important;
    padding: 16px !important;
    margin: 12px 0 !important;
}

/* 統計カードのスタイル */
.stats-card {
    background: linear-gradient(135deg, var(--primary-light), rgba(255, 255, 255, 0.8)) !important;
    border-radius: 12px !important;
    padding: 20px !important;
    margin: 12px 0 !important;
    border: 1px solid var(--border-color) !important;
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1) !important;
}

/* ダークモード防止 */
@media (prefers-color-scheme: dark) {
    .stApp {
        background-color: #ffffff !important;
        color: var(--text-primary) !important;
    }
}



/* 余白を最小限に - さらなる最適化 */
.st-emotion-cache-zy6yx3 {
    padding: 0.5rem 0.5rem 0.5rem !important;
}

.st-emotion-cache-4rsbii {
    padding-top: 0.5rem !important;
}

.st-emotion-cache-1u02ojh {
    gap: 0.25rem !important;
    row-gap: 0.25rem !important;
    column-gap: 0.25rem !important;
}

[data-testid="stElementContainer"] {
    margin-top: 0 !important;
    margin-bottom: 0.25rem !important;
}

/* 新規問題表示と問題表示の間の余白を削除 */
.st-emotion-cache-r44huj {
    margin-top: 0 !important;
    margin-bottom: 0 !important;
    padding-top: 0 !important;
    padding-bottom: 0 !important;
}

/* Markdownコンテナの余白調整 */
.stMarkdown {
    margin-top: 0 !important;
    margin-bottom: 0 !important;
}

/* 情報ボックス（st.info）の余白調整 */
.stAlert {
    margin-top: 0 !important;
    margin-bottom: 0.5rem !important;
}

/* アラートボックス内のテキストを中央揃え */
.stAlert .st-emotion-cache-r44huj {
    text-align: center !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
}

/* アラートコンテナ全体を中央揃え */
.stAlert [data-testid="stMarkdownContainer"] {
    text-align: center !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
}

/* アラートボックスのコンテンツ中央揃え */
.stAlert [data-testid="stAlertContainer"] {
    text-align: center !important;
}

/* アラートボックス内のpタグも中央揃え */
.stAlert p {
    text-align: center !important;
    margin: 0 !important;
}

/* サイドバー内のアラートのみシンプルに左寄せ */
.stSidebar .stAlert {
    text-align: left;
}

.st-emotion-cache-13gev4o {
    margin: 0 !important;
    padding: 0 !important;
}

/* 新規問題表示のコンテナスタイル調整 */
div[style*="background-color: rgb(250, 250, 250)"] {
    margin-top: 0 !important;
    padding-top: 12px !important;
}

/* 問題表示エリアの余白調整 */
.stContainer {
    margin-top: 0 !important;
    padding-top: 0 !important;
}

/* アプリ全体の高さ調整 */
.st-emotion-cache-6px8kg {
    min-height: auto !important;
    height: auto !important;
}

/* メインコンテナの調整 */
.element-container {
    margin: 0 !important;
    padding: 0 !important;
}

/* iframeコンテナの調整 */
.stIFrame {
    margin: 0 !important;
    padding: 0 !important;
}

/* 連続する要素間の余白を最小化 */
.stElementContainer + .stElementContainer {
    margin-top: 0 !important;
}

/* 情報ボックスの直後の要素の余白を削除 */
.stAlert + .stElementContainer {
    margin-top: 0 !important;
}

/* 新規問題/復習問題表示の直後の余白を削除 */
.stAlert + .stMarkdown {
    margin-top: 0 !important;
}

/* ログイン後のメインコンテンツエリアの上部マージン追加 */
.stVerticalBlock.st-emotion-cache-1u02ojh {
    margin-top: 1rem !important;
    padding-top: 0.5rem !important;
}

/* メインコンテンツエリアのヘッダー調整 */
.stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {
    margin-top: 0.5rem !important;
    padding-top: 0.25rem !important;
}

/* アラートコンテナの上部マージン */
.stAlert {
    margin-top: 0.5rem !important;
}

/* ダウンロードボタンの統一スタイル */
.stDownloadButton > button {
    background: linear-gradient(135deg, var(--primary-color), var(--primary-hover)) !important;
    color: white !important;
    border: 2px solid var(--primary-color) !important;
    border-radius: 8px !important;
    padding: 0.5rem 1rem !important;
    font-weight: 600 !important;
    box-shadow: 0 2px 4px rgba(28, 131, 225, 0.3) !important;
    transition: all 0.3s ease !important;
}

.stDownloadButton > button:hover {
    background: linear-gradient(135deg, var(--primary-hover), var(--primary-color)) !important;
    border-color: var(--primary-hover) !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 8px rgba(28, 131, 225, 0.4) !important;
}

/* ボタンのフォーカス状態を統一 */
.stButton > button:focus,
.stDownloadButton > button:focus {
    outline: none !important;
    box-shadow: 0 0 0 3px rgba(28, 131, 225, 0.3) !important;
}

/* その他のフォーム要素の統一 */
.stSelectbox > div > div {
    border-color: var(--border-color) !important;
    background-color: var(--background-light) !important;
}

.stSelectbox > div > div:focus-within {
    border-color: var(--primary-color) !important;
    box-shadow: 0 0 0 2px rgba(28, 131, 225, 0.2) !important;
}
</style>""", unsafe_allow_html=True)

# 最小限のスタイル
st.markdown("""
<style>
/* 基本設定のみ */
.stApp {
    background-color: #ffffff;
}
</style>""", unsafe_allow_html=True)


class DentalApp:
    """歯科国家試験対策アプリのメインクラス"""
    
    def __init__(self):
        # パフォーマンス最適化を最初に適用
        apply_performance_optimizations()
        
        self.auth_manager = AuthManager()
        self.cookie_manager = CookieManager()
        self.firestore_manager = get_firestore_manager()
        
        # 強化されたGoogle Analytics統合
        # self.analytics = enhanced_ga
        
        # セッション状態の初期化
        self._initialize_session_state()
        
        # ユーザー行動追跡の初期化
        self._initialize_user_tracking()
    
    def _initialize_session_state(self):
        """セッション状態の初期化"""
        default_values = {
            "user_logged_in": None,
            "uid": None,
            "email": None,
            "name": None,
            "page": "練習",  # デフォルトを演習ページに
            "cards": {},
            "analysis_target": "国試",
            "level_filter": ["未学習", "レベル0", "レベル1", "レベル2", "レベル3", "レベル4", "習得済み"],  # レベル0-4に修正
            "new_cards_per_day": 10,
            "result_log": {},
            "auto_login_attempted": False,  # 自動ログイン試行フラグを追加
            "session_start_time": time.time(),  # セッション開始時間
            "page_interactions": 0,  # ページ相互作用数
            "study_sessions": []  # 学習セッション履歴
        }
        
        for key, value in default_values.items():
            if key not in st.session_state:
                st.session_state[key] = value
    
    def _initialize_user_tracking(self):
        """ユーザー追跡の初期化"""
        if 'tracking_initialized' not in st.session_state:
            st.session_state['tracking_initialized'] = True
            st.session_state['session_start_time'] = time.time()
            st.session_state['page_interactions'] = 0
            
            # セッション開始イベント
            # self.analytics.track_user_engagement(
            #     engagement_type='session_start',
            #     interaction_count=0
            # )
    
    def track_page_navigation(self, page_name: str):
        """ページナビゲーション追跡"""
        # ページビュー追跡
        # self.analytics.track_page_view(
        #     page_name=page_name,
        #     page_title=f"歯科国試アプリ - {page_name}",
        #     additional_params={
        #         'previous_page': st.session_state.get('current_page', 'unknown'),
        #         'session_duration': time.time() - st.session_state.get('session_start_time', time.time())
        #     }
        # )
        
        # 現在のページを記録
        st.session_state['current_page'] = page_name
        
        # 相互作用数増加
        st.session_state['page_interactions'] += 1
    
    def track_user_login_success(self, user_info: dict):
        """ログイン成功追跡"""
        user_properties = {
            'user_type': 'registered' if user_info.get('uid') else 'anonymous',
            'login_timestamp': datetime.datetime.now().isoformat(),
            'has_gakushi_permission': user_info.get('has_gakushi_permission', False)
        }
        
        # self.analytics.track_user_login(
        #     login_method='firebase',
        #     user_properties=user_properties
        # )
        
        # ユーザープロパティ更新
        # self.analytics.user_id = user_info.get('uid', 'anonymous')
    
    def track_study_activity(self, activity_type: str, details: dict = None):
        """学習活動追跡"""
        base_params = {
            'activity_type': activity_type,
            'timestamp': datetime.datetime.now().isoformat(),
            'session_duration': time.time() - st.session_state.get('session_start_time', time.time())
        }
        
        if details:
            base_params.update(details)
        
        # self.analytics._send_event('study_activity', base_params)
    
    def track_feature_interaction(self, feature: str, action: str, context: dict = None):
        """機能相互作用追跡"""
        # self.analytics.track_feature_usage(
        #     feature_name=feature,
        #     action=action,
        #     context=context or {}
        # )
        pass
        
        # 科目の初期化
        self._initialize_available_subjects()
    
    def _initialize_available_subjects(self):
        """利用可能な科目を初期化（最適化版）"""
        uid = st.session_state.get("uid")
        has_gakushi_permission = check_gakushi_permission(uid) if uid else False
        analysis_target = st.session_state.get("analysis_target", "国試問題")
        
        # 既に同じ条件で初期化済みの場合はスキップ
        cache_key = f"{uid}_{has_gakushi_permission}_{analysis_target}"
        if (st.session_state.get('available_subjects') and 
            st.session_state.get('subjects_cache_key') == cache_key):
            return
        
        # キャッシュから科目を取得
        try:
            available_subjects = PerformanceOptimizer.get_cached_subjects(
                uid or "anonymous", 
                has_gakushi_permission, 
                analysis_target
            )
            st.session_state.available_subjects = available_subjects
            st.session_state.subjects_cache_key = cache_key
            
            # 科目フィルターのデフォルト設定
            if 'subject_filter' not in st.session_state:
                st.session_state.subject_filter = available_subjects
                
        except Exception as e:
            print(f"[DEBUG] 科目初期化エラー: {e}")
            # フォールバック処理
            st.session_state.available_subjects = ["一般"]
            st.session_state.subject_filter = ["一般"]
            st.session_state.subjects_cache_key = cache_key
    
    def run(self):
        """アプリケーションのメイン実行（最適化版）"""
        # パフォーマンス最適化の適用
        apply_performance_optimizations()
        
        # CSSスタイルを適用（ページ読み込み時に一度だけ実行）
        if not st.session_state.get("styles_applied"):
            apply_sidebar_button_styles()
            st.session_state["styles_applied"] = True
        
        # Google Analytics初期化（ページ読み込み時に一度だけ実行）
        if not st.session_state.get("ga_initialized"):
            AnalyticsUtils.inject_ga_script()
            st.session_state["ga_initialized"] = True
        
        # ユーザーのアクティビティ追跡
        self._track_user_activity()
        
        # 🔄 1. Automatic Login Attempt
        if (not st.session_state.get("user_logged_in") and 
            not st.session_state.get("auto_login_attempted")):
            
            st.session_state["auto_login_attempted"] = True
            if self.cookie_manager.try_auto_login():
                # 自動ログイン成功時に科目を初期化
                self._initialize_available_subjects()
                
                # ログイン成功追跡
                user_info = {
                    'uid': st.session_state.get('uid'),
                    'email': st.session_state.get('email'),
                    'has_gakushi_permission': check_gakushi_permission(st.session_state.get('uid'))
                }
                self.track_user_login_success(user_info)
                
                st.rerun()
        
        # ログイン状態をチェック
        if not st.session_state.get("user_logged_in") or not self.auth_manager.ensure_valid_session():
            # ログイン画面ではサイドバーを非表示
            self._hide_sidebar()
            self._render_login_page()
            
            # ログインページビュー追跡
            self.track_page_navigation("login")
        else:
            # ログイン済みの場合はサイドバーとメインコンテンツを表示
            # 科目が初期化されていない場合は初期化
            if not hasattr(st.session_state, 'available_subjects') or not st.session_state.available_subjects:
                self._initialize_available_subjects()
            
            # 最適化されたUI描画
            UIOptimizer.render_optimized_sidebar(self._render_sidebar)
            self._render_main_content()
            
            # ログイン後のページビュー追跡
            current_page = st.session_state.get("page", "練習")
            self.track_page_navigation(current_page)
    
    def _track_user_activity(self):
        """ユーザーアクティビティの追跡"""
        try:
            uid = st.session_state.get("uid")
            if uid:
                # セッションの開始追跡（初回のみ）
                if not st.session_state.get("session_tracked"):
                    log_to_ga("session_start", uid, {
                        "session_type": "web_app",
                        "timestamp": datetime.datetime.now().isoformat(),
                        "user_agent": st.context.headers.get("User-Agent", "unknown") if hasattr(st.context, 'headers') else "unknown"
                    })
                    st.session_state["session_tracked"] = True
                
                # アクティブユーザーの追跡（5分ごと）
                import time
                last_activity = st.session_state.get("last_activity_logged", 0)
                current_time = time.time()
                
                if current_time - last_activity > 300:  # 5分 = 300秒
                    log_to_ga("user_active", uid, {
                        "active_duration_seconds": current_time - last_activity,
                        "current_page": st.session_state.get("current_page", "unknown")
                    })
                    st.session_state["last_activity_logged"] = current_time
                    
        except Exception as e:
            print(f"[DEBUG] User activity tracking error: {e}")
    
    def _hide_sidebar(self):
        """サイドバーを非表示にする"""
        st.markdown("""
        <style>
        /* サイドバーを完全に非表示にする */
        .css-1d391kg {display: none !important}
        section[data-testid="stSidebar"] {display: none !important}
        .sidebar .sidebar-content {display: none !important}
        
        /* メインコンテンツエリアを調整（サイドバー分の余白を削除） */
        .css-18e3th9 {padding-left: 1rem !important}
        .css-1lcbmhc {margin-left: 0 !important}
        .main .block-container {padding-left: 1rem !important}
        
        /* Streamlit 1.28+ の新しいサイドバークラス */
        [data-testid="stSidebar"][aria-expanded="true"] {display: none !important}
        [data-testid="stSidebar"][aria-expanded="false"] {display: none !important}
        
        /* サイドバートグルボタンも非表示 */
        .css-1v0mbdj {display: none !important}
        button[kind="header"] {display: none !important}
        
        /* ログイン画面の余白を詰める */
        .st-emotion-cache-zy6yx3 {
            padding: 1rem 1rem 1rem !important;
        }
        
        /* メインコンテナの余白調整 */
        .st-emotion-cache-4rsbii {
            padding-top: 1rem !important;
            justify-content: flex-start !important;
        }
        
        /* 全体の高さ調整 */
        .st-emotion-cache-6px8kg {
            min-height: auto !important;
            height: auto !important;
        }
        
        /* ログイン画面のコンテナ全体 */
        .st-emotion-cache-1u02ojh {
            gap: 0.5rem !important;
            margin-top: 0 !important;
            padding-top: 0 !important;
        }
        
        /* 追加の余白削除 */
        [data-testid="stElementContainer"] {
            margin-top: 0 !important;
            margin-bottom: 0.5rem !important;
        }
        
        /* タイトルや見出しの余白削除 */
        .st-emotion-cache-1u02ojh h1,
        .st-emotion-cache-1u02ojh h2,
        .st-emotion-cache-1u02ojh h3 {
            margin-top: 0 !important;
            margin-bottom: 0.5rem !important;
        }
        
        /* iframeの余白も削除 */
        .st-emotion-cache-13gev4o {
            margin: 0 !important;
            padding: 0 !important;
        }
        </style>
        """, unsafe_allow_html=True)
    
    def _render_sidebar(self):
        """サイドバーの描画（ログイン済みユーザー向け）"""
        with st.sidebar:
            self._render_user_menu()
    
    def _render_login_page(self):
        """🔐 2. Manual Login Screen - タブ形式のログイン画面"""
        st.title("🦷 歯科国家試験AI対策アプリ")
        st.markdown("### 🔐 ログイン／新規登録")
        
        tab_login, tab_signup, tab_reset = st.tabs(["ログイン", "新規登録", "パスワードリセット"])
        
        with tab_login:
            self._render_login_tab()
        
        with tab_signup:
            self._render_signup_tab()
        
        with tab_reset:
            self._render_reset_tab()
    
    def _render_login_tab(self):
        """ログインタブの描画"""
        # クッキーから保存されたメールアドレスを取得
        saved_email = ""
        if self.cookie_manager.cookies:
            try:
                saved_email = self.cookie_manager.cookies.get("email", "")
            except:
                pass
        
        email = st.text_input(
            "メールアドレス", 
            value=saved_email,
            placeholder="your-email@example.com",
            key="login_email"
        )
        password = st.text_input(
            "パスワード", 
            type="password",
            key="login_password"
        )
        remember_me = st.checkbox(
            "ログイン状態を保存する",
            value=False,
            key="login_remember"
        )
        
        if st.button("ログイン", type="primary", use_container_width=True):
            if email and password:
                self._handle_login(email, password, remember_me)
            else:
                st.error("メールアドレスとパスワードを入力してください")
    
    def _render_signup_tab(self):
        """新規登録タブの描画"""
        # 新規登録の一時停止フラグ（必要に応じて True に変更）
        SIGNUP_TEMPORARILY_DISABLED = True  # ← ★この行が重要です
        
        if SIGNUP_TEMPORARILY_DISABLED:
            st.warning("🚧 新規登録は一時的に停止中です")
            st.info("既存のアカウントをお持ちの方は「ログイン」タブからログインしてください。")
        else:
            # ここに新規登録フォームのコードが続く...
            signup_email = st.text_input(
                "メールアドレス", 
                placeholder="your-email@example.com",
                key="signup_email"
            )
            signup_password = st.text_input(
                "パスワード（6文字以上）", 
                type="password",
                key="signup_password"
            )
            
            if st.button("新規登録", type="primary", use_container_width=True, key="signup_btn"):
                if signup_email and signup_password:
                    if len(signup_password) < 6:
                        st.error("パスワードは6文字以上で入力してください")
                    else:
                        self._handle_signup(signup_email, signup_password)
                else:
                    st.error("メールアドレスとパスワードを入力してください")
    
    def _render_reset_tab(self):
        """パスワードリセットタブの描画"""
        email = st.text_input(
            "メールアドレス", 
            placeholder="your-email@example.com",
            key="reset_email"
        )
        
        if st.button("パスワードリセットメールを送信", type="primary", use_container_width=True):
            if email:
                self._handle_password_reset(email)
            else:
                st.error("メールアドレスを入力してください")
    
    def _render_user_menu(self):
        """ユーザーメニューの描画"""
        uid = st.session_state.get("uid")
        email = st.session_state.get("email", "")
        
        # ニックネームを取得（プライバシー配慮）
        name = st.session_state.get("name", "")
        if not name:
            # シンプルなデフォルト名を生成してセッションに保存
            name = f"学習者{uid[:8]}"
            st.session_state["name"] = name
        
        st.success(f"👤 {name} としてログイン中")
        
        # ページ選択をラジオボタン形式に変更
        page_options = ["練習", "検索・進捗", "ランキング"]
        page_labels = ["📚 練習ページ", "📊 検索・進捗", "🏆 ランキング"]
        
        current_page = st.session_state.get("page", "練習")
        current_index = 0
        if current_page == "検索・進捗":
            current_index = 1
        elif current_page == "ランキング":
            current_index = 2
        
        selected_page = st.radio(
            "ページを選択",
            page_labels,
            index=current_index,
            key="page_selector"
        )
        
        # ページ切り替え時のイベント追跡
        new_page = None
        if selected_page == "📚 練習ページ":
            new_page = "練習"
        elif selected_page == "📊 検索・進捗":
            new_page = "検索・進捗"
        elif selected_page == "🏆 ランキング":
            new_page = "ランキング"
        
        # ページが変更された場合はイベントを送信（最適化版）
        if new_page and new_page != st.session_state.get("page"):
            old_page = st.session_state.get("page", "unknown")
            
            # ページ遷移の最適化チェック
            if UIOptimizer.optimize_page_transition(new_page, old_page):
                st.session_state["page"] = new_page
                st.session_state["current_page"] = new_page  # _track_user_activityで使用
                
                # 包括的なページ変更追跡
                self.track_page_navigation(new_page)
                
                # 機能使用追跡
                self.track_feature_interaction(
                    feature="page_navigation",
                    action="page_change",
                    context={
                        "from_page": old_page,
                        "to_page": new_page,
                        "navigation_method": "sidebar"
                    }
                )
                
                if uid:
                    log_to_ga("page_change", uid, {
                        "previous_page": old_page,
                        "new_page": new_page,
                        "navigation_method": "sidebar"
                    })
                
                # 強制リロードを削除してパフォーマンス向上
                # st.rerun() を削除
        
        # 選択されたページに応じて異なるサイドバーコンテンツを表示
        if st.session_state.get("page") == "ランキング":
            st.info("🏆 ランキングページ表示中")
            st.markdown("**週間ランキング**で他の学習者と競い合いましょう！")
        elif st.session_state.get("page") == "検索・進捗":
            st.info("📊 検索・進捗ページ表示中")
            st.markdown("**学習データ分析**と**問題検索**で効率的に学習しましょう！")
            
            # セクションヘッダー
            st.markdown("### 📊 分析・検索ツール")
            
            # 学士試験権限の確認
            has_gakushi_permission = check_gakushi_permission(uid) if uid else False
            
            # 分析対象フィルター（最適化版）
            if has_gakushi_permission:
                # 分析対象変更時のコールバック（最適化版）
                def on_analysis_target_change():
                    # デバウンス処理を適用
                    if PerformanceOptimizer.debounce_action("analysis_target_change", 0.5):
                        # キャッシュをクリア
                        PerformanceOptimizer.get_cached_subjects.clear()
                        # 科目リストを強制再初期化
                        if 'available_subjects' in st.session_state:
                            del st.session_state['available_subjects']
                        if 'subject_filter' in st.session_state:
                            del st.session_state['subject_filter']
                        # 科目を即座に再初期化
                        self._initialize_available_subjects()
                        print(f"[DEBUG] 分析対象変更: {st.session_state.get('analysis_target')}, 利用可能科目数: {len(st.session_state.get('available_subjects', []))}")
                
                analysis_target = st.radio(
                    "分析対象試験",
                    options=["国試問題", "学士試験問題"],
                    index=0,  # 常に国試問題をデフォルトに設定
                    key="analysis_target",
                    on_change=on_analysis_target_change,
                    help="分析や検索を行う試験の種類を選択してください"
                )
            else:
                st.session_state["analysis_target"] = "国試問題"
                st.info("💡 現在は国試問題のみ利用可能です")
            
            # 科目フィルター（最適化版）
            if not hasattr(st.session_state, 'available_subjects') or not st.session_state.available_subjects:
                # 科目が初期化されていない場合は再初期化
                self._initialize_available_subjects()
            
            if hasattr(st.session_state, 'available_subjects') and st.session_state.available_subjects:
                # 現在の科目フィルター値を取得（なければ全選択をデフォルト）
                current_subject_filter = st.session_state.get('subject_filter', st.session_state.available_subjects)
                # 利用可能な科目に含まれないものを除外
                valid_subject_filter = [s for s in current_subject_filter if s in st.session_state.available_subjects]
                if not valid_subject_filter:  # 有効な科目が1つもない場合は全選択
                    valid_subject_filter = st.session_state.available_subjects
                
                subject_filter = st.multiselect(
                    "表示する科目",
                    st.session_state.available_subjects,
                    default=valid_subject_filter,
                    key="subject_filter",
                    help=f"現在利用可能な科目: {len(st.session_state.available_subjects)}科目"
                )
            else:
                st.warning("科目データを読み込み中...")
            
            # 必修問題フィルター
            show_hisshu_only = st.checkbox(
                "必修問題のみ表示",
                value=st.session_state.get('show_hisshu_only', False),
                key="show_hisshu_only"
            )
            
            # レベルフィルター
            st.markdown("### 📈 習熟度フィルター")
            
            level_options = ["未学習", "レベル0", "レベル1", "レベル2", "レベル3", "レベル4", "レベル5", "習得済み"]
            default_levels = st.session_state.get('level_filter', level_options)
            
            level_filter = st.multiselect(
                "表示する習熟度レベル",
                level_options,
                default=default_levels,
                key="level_filter",
                help="表示したい習熟度レベルを選択してください"
            )
            
        else:
            # 練習ページのサイドバー
            print("[DEBUG] app.py: 練習ページのサイドバーを呼び出し中...")
            from modules.practice_page import render_practice_sidebar
            render_practice_sidebar()
        
        # ログアウトボタン
        st.divider()
        if st.button("🚪 ログアウト", type="secondary", use_container_width=True):
            self._handle_logout_real()

    def _render_free_learning_mode(self, has_gakushi_permission: bool):
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
                target_exam = "国試"
                st.info("📚 学士試験機能を利用するには権限が必要です")
            
            # 出題形式の選択
            quiz_format = st.radio(
                "出題形式",
                ["回数別", "科目別", "必修問題のみ", "キーワード検索"],
                key="free_quiz_format"
            )
            
            # 詳細条件の選択（動的UI）
            self._render_detailed_conditions(quiz_format, target_exam)
            
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
                self._start_free_learning(quiz_format, target_exam, question_order)
                
        except Exception as e:
            st.error(f"自由演習モードでエラー: {str(e)}")
            st.exception(e)
    
    def _render_detailed_conditions(self, quiz_format: str, target_exam: str):
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
    
    def _render_session_status(self):
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
            st.markdown("### � 最近の評価")
            recent_results = list(result_log.items())[-10:]  # 最新10件
            
            # 問題番号ボタンを3列で表示
            cols = st.columns(3)
            for i, (q_id, result) in enumerate(recent_results):
                with cols[i % 3]:
                    # 評価に応じたアイコン
                    if result.get("rating") == "Easy":
                        icon = "🟢"
                    elif result.get("rating") == "Good":
                        icon = "🔵"
                    elif result.get("rating") == "Hard":
                        icon = "🟡"
                    else:
                        icon = "🔴"
                    
                    if st.button(f"{icon} {q_id}", key=f"recent_{q_id}", use_container_width=True):
                        # 問題に直接ジャンプ
                        self._jump_to_question(q_id)

    def _start_auto_learning(self):
        """おまかせ学習の開始処理"""
        uid = st.session_state.get("uid")
        use_local_fallback = True  # Cloud Functionを無効化
            
        if not use_local_fallback:
            try:
                # Cloud Function呼び出し
                result = call_cloud_function("getDailyQuiz", {
                    "uid": uid,
                    "target": st.session_state.get("analysis_target", "国試"),
                    "new_cards_per_day": st.session_state.get("new_cards_per_day", 10)
                })
                
                if result and "questionIds" in result and len(result["questionIds"]) > 0:
                    # Cloud Functionから問題リストを取得
                    question_ids = result["questionIds"]
                    # 問題IDから問題データを取得
                    from data import load_data
                    all_data = load_data()
                    questions = [q for q in all_data["questions"] if q["number"] in question_ids]
                    
                    st.session_state["main_queue"] = questions
                    st.session_state["session_mode"] = "auto_learning"
                    st.session_state["session_choice_made"] = True
                    st.session_state["session_type"] = "おまかせ演習"
                    st.success(f"📚 {len(questions)}問の学習セッションを開始します")
                    AnalyticsUtils.track_study_session_start("auto_learning", len(questions))
                    
                    # Firebase Analytics統合
                    from firebase_analytics import FirebaseAnalytics
                    FirebaseAnalytics.log_study_session_start(
                        uid=uid,
                        session_type="auto_learning",
                        metadata={
                            "target": st.session_state.get("analysis_target", "国試"),
                            "question_count": len(questions),
                            "source": "cloud_function"
                        }
                    )
                else:
                    # Cloud Functionが失敗またはデータなし
                    print("Cloud Function returned no valid questions, using fallback")
                    self._fallback_auto_learning()
                    
            except Exception as e:
                print(f"Cloud Function error: {e}")
                # フォールバック処理
                self._fallback_auto_learning()
        else:
            # ローカル処理を直接使用
            print("Using local fallback directly (Cloud Function disabled)")
            self._fallback_auto_learning()
        
        # 学習画面に遷移
        time.sleep(0.5)
        st.rerun()
    
    def _fallback_auto_learning(self):
        """クライアント側でのおまかせ学習フォールバック処理"""
        cards = st.session_state.get("cards", {})
        new_cards_per_day = st.session_state.get("new_cards_per_day", 10)
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        
        # 復習カードと新規カードを選択
        review_questions = []
        new_questions = []
        
        # カードが存在する場合の処理
        if cards:
            for q_id, card in cards.items():
                # SM2データから復習期限を取得
                sm2_data = card.get("sm2", {})
                due_date = sm2_data.get("due_date")
                history = card.get("history", [])
                
                # 復習期限チェック
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
                            review_questions.append(q_id)
                    except Exception as e:
                        print(f"[DEBUG] 日付変換エラー: {due_date}, エラー: {e}")
                        continue
                # 未学習カードチェック
                elif len(history) == 0:
                    new_questions.append(q_id)
            
            # 新規カードを制限
            new_questions = new_questions[:new_cards_per_day]
            all_questions = review_questions + new_questions
        else:
            # カードがない場合、全問題からランダムに選択
            st.info("ユーザーカードが見つからないため、ランダムに問題を選択します。")
            try:
                # data.pyから問題データを取得
                from data import ALL_QUESTIONS
                if ALL_QUESTIONS:
                    # 権限チェック
                    uid = st.session_state.get("uid")
                    if uid and check_gakushi_permission(uid):
                        available_questions = [q.get("id") for q in ALL_QUESTIONS if q.get("id")]
                    else:
                        # 学士以外の問題のみ
                        available_questions = [q.get("id") for q in ALL_QUESTIONS 
                                             if q.get("id") and q.get("exam_type") != "学士"]
                    
                    # ランダムに選択
                    import random
                    all_questions = random.sample(available_questions, 
                                                min(new_cards_per_day, len(available_questions)))
                else:
                    st.error("問題データが見つかりません。")
                    return
            except Exception as e:
                st.error(f"問題選択エラー: {e}")
                return
        
        # 問題が見つからない場合の処理
        if not all_questions:
            st.warning("復習対象の問題が見つかりません。新規問題からランダムに選択します。")
            try:
                from data import ALL_QUESTIONS
                uid = st.session_state.get("uid")
                if uid and check_gakushi_permission(uid):
                    available_questions = [q.get("id") for q in ALL_QUESTIONS if q.get("id")]
                else:
                    available_questions = [q.get("id") for q in ALL_QUESTIONS 
                                         if q.get("id") and q.get("exam_type") != "学士"]
                
                import random
                all_questions = random.sample(available_questions, 
                                            min(new_cards_per_day, len(available_questions)))
            except Exception as e:
                st.error(f"フォールバック問題選択エラー: {e}")
                return
        
        # キューに設定
        st.session_state["main_queue"] = all_questions
        st.session_state["session_mode"] = "auto_learning"
        st.session_state["session_choice_made"] = True
        st.session_state["session_type"] = "おまかせ演習"
        
        # 分析ログの記録
        AnalyticsUtils.track_study_session_start("auto_learning_fallback", len(all_questions))
        
        # Firebase Analytics統合
        from firebase_analytics import FirebaseAnalytics
        FirebaseAnalytics.log_study_session_start(
            uid=st.session_state.get("uid"),
            session_type="auto_learning_fallback",
            metadata={
                "target": st.session_state.get("analysis_target", "国試"),
                "question_count": len(all_questions),
                "source": "local_fallback",
                "fallback_reason": "cloud_function_error"
            }
        )
        st.info("📚 ローカル問題選択アルゴリズムを使用しています。")
        st.success(f"📚 {len(all_questions)}問の学習セッションを開始します")
    
    def _start_free_learning(self, quiz_format: str, target_exam: str, question_order: str):
        """自由演習の開始処理"""
        with st.spinner("問題を準備中..."):
            questions_to_load = self._generate_question_list(quiz_format, target_exam)
            
            if not questions_to_load:
                st.error("条件に一致する問題が見つかりませんでした")
                return
            
            # 出題順の決定（グループ化前にソート）
            if question_order == "順番通り":
                question_dict = {q.get("number", ""): q for q in ALL_QUESTIONS}
                questions_to_load.sort(key=lambda x: get_natural_sort_key(question_dict.get(x, {})))
            elif question_order == "シャッフル":
                random.shuffle(questions_to_load)
            
            # グループ化処理（連問対応）
            grouped_questions = self._group_case_questions(questions_to_load)
            
            # グループレベルでのシャッフル（必要に応じて）
            if question_order == "シャッフル":
                random.shuffle(grouped_questions)
            
            # キューに設定
            st.session_state["main_queue"] = grouped_questions
            total_questions = sum(len(group) for group in grouped_questions)
            
            # カスタム演習セッションの開始
            st.session_state["session_choice_made"] = True
            st.session_state["session_type"] = "カスタム演習"
            st.session_state["custom_questions_selected"] = True
            
            # 最初の問題グループを設定
            if grouped_questions:
                st.session_state["current_q_group"] = grouped_questions[0]
                st.session_state["current_question_index"] = 0
                # main_queueから最初のグループを削除
                st.session_state["main_queue"] = grouped_questions[1:]
            
            st.success(f"🎯 {len(grouped_questions)}グループ（計{total_questions}問）の演習を開始します")
            
            time.sleep(0.5)
            st.rerun()
    
    def _generate_question_list(self, quiz_format: str, target_exam: str):
        """条件に基づく問題リスト生成"""
        questions_to_load = []
        
        if quiz_format == "回数別":
            # 国試回数と領域の取得
            if target_exam == "国試":
                selected_kaisu = st.session_state.get("free_kaisu", "117回").replace("回", "")
                selected_area = st.session_state.get("free_area", "全領域")
                
                for q in ALL_QUESTIONS:
                    q_num = q.get("number", "")
                    # 学士問題は除外
                    if q_num.startswith("G"):
                        continue
                    
                    # 回数フィルタ
                    if not q_num.startswith(selected_kaisu):
                        continue
                    
                    # 領域フィルタ
                    if selected_area != "全領域":
                        area_letter = selected_area.replace("領域", "")
                        if not q_num.startswith(f"{selected_kaisu}{area_letter}"):
                            continue
                    
                    questions_to_load.append(q_num)
            
            else:  # 学士試験
                selected_year = st.session_state.get("free_gakushi_year", "2025年度").replace("年度", "")
                selected_kaisu = st.session_state.get("free_gakushi_kaisu", "1-1")
                selected_area = st.session_state.get("free_gakushi_area", "全領域")
                
                for q in ALL_QUESTIONS:
                    q_num = q.get("number", "")
                    # 学士問題のみ
                    if not q_num.startswith("G"):
                        continue
                    
                    # 年度と回数フィルタ（例：G24-1-1、G24-1-2、G24-1-3、G24-1再、G24-2、G24-2再）
                    year_short = str(int(selected_year) - 2000)  # 2024 -> 24
                    pattern = f"G{year_short}-{selected_kaisu}"
                    
                    if not q_num.startswith(pattern):
                        continue
                    
                    # 領域フィルタ
                    if selected_area != "全領域":
                        area_letter = selected_area.replace("領域", "")
                        if f"-{area_letter}-" not in q_num:
                            continue
                    
                    questions_to_load.append(q_num)
        
        elif quiz_format == "科目別":
            selected_subject = st.session_state.get("free_subject", "解剖学")
            
            for q in ALL_QUESTIONS:
                q_num = q.get("number", "")
                q_subject = q.get("subject", "")
                
                # 対象試験のフィルタ
                if target_exam == "国試" and q_num.startswith("G"):
                    continue
                elif target_exam == "学士試験" and not q_num.startswith("G"):
                    continue
                
                # 科目フィルタ
                if q_subject == selected_subject:
                    questions_to_load.append(q_num)
        
        elif quiz_format == "必修問題のみ":
            if target_exam == "国試":
                questions_to_load = list(HISSHU_Q_NUMBERS_SET)
            else:  # 学士試験
                questions_to_load = list(GAKUSHI_HISSHU_Q_NUMBERS_SET)
        
        elif quiz_format == "キーワード検索":
            keyword = st.session_state.get("free_keyword", "").strip()
            if keyword:
                for q in ALL_QUESTIONS:
                    q_num = q.get("number", "")
                    q_text = q.get("question", "")
                    
                    # 対象試験のフィルタ
                    if target_exam == "国試" and q_num.startswith("G"):
                        continue
                    elif target_exam == "学士試験" and not q_num.startswith("G"):
                        continue
                    
                    # キーワード検索
                    if keyword.lower() in q_text.lower():
                        questions_to_load.append(q_num)
        
        print(f"[DEBUG] 生成された問題リスト: {len(questions_to_load)}問")
        return questions_to_load
    
    def _group_case_questions(self, questions):
        """連問をグループ化"""
        processed_case_ids = set()
        grouped_questions = []
        
        # ALL_QUESTIONSから問題詳細を取得
        question_dict = {q.get("number", ""): q for q in ALL_QUESTIONS}
        
        for q_num in questions:
            if q_num in question_dict:
                question = question_dict[q_num]
                case_id = question.get("case_id")
                
                if case_id and case_id not in processed_case_ids:
                    # 同じcase_idを持つ全ての問題を取得
                    case_questions = []
                    for check_q_num in questions:
                        if check_q_num in question_dict:
                            check_question = question_dict[check_q_num]
                            if check_question.get("case_id") == case_id:
                                case_questions.append(check_q_num)
                    
                    # 連問を自然順でソート
                    case_questions.sort(key=lambda x: get_natural_sort_key(question_dict.get(x, {})))
                    grouped_questions.append(case_questions)
                    processed_case_ids.add(case_id)
                
                elif not case_id:
                    # 単独問題
                    grouped_questions.append([q_num])
        
        print(f"[DEBUG] グループ化結果: {len(grouped_questions)}グループ")
        return grouped_questions
    
    def _jump_to_question(self, q_id: str):
        """指定問題への直接ジャンプ"""
        # 問題を最前面に持ってくる
        current_queue = st.session_state.get("main_queue", [])
        if q_id in current_queue:
            current_queue.remove(q_id)
        
        # 最前面に追加
        st.session_state["main_queue"] = [q_id] + current_queue
        st.success(f"問題 {q_id} にジャンプします")
        time.sleep(0.5)
        st.rerun()
    
    def _render_other_page_settings(self):
        """その他のページでの従来設定表示"""
        uid = st.session_state.get("uid")
        has_gakushi_permission = check_gakushi_permission(uid) if uid else False
        
        if not has_gakushi_permission:
            st.info("📚 学士試験機能を利用するには権限が必要です")
        
        # 設定セクション
        with st.expander("⚙️ 設定"):
            self._render_settings(has_gakushi_permission)
    
    def _handle_logout_real(self):
        """ログアウト処理"""
        uid = st.session_state.get("uid")
        if uid:
            log_to_ga("logout", uid, {})
        
        self.auth_manager.logout()
        st.success("ログアウトしました")
        time.sleep(1)
        st.rerun()
    
    def _render_settings(self, has_gakushi_permission: bool):
        """設定の描画"""
        # 分析対象選択
        if has_gakushi_permission:
            analysis_options = ["国試", "学士試験"]
        else:
            analysis_options = ["国試"]
        
        analysis_target = st.selectbox(
            "分析対象",
            analysis_options,
            index=analysis_options.index(st.session_state.get("analysis_target", "国試"))
            if st.session_state.get("analysis_target") in analysis_options else 0,
            key="analysis_target_selector"
        )
        
        if analysis_target != st.session_state.get("analysis_target"):
            st.session_state["analysis_target"] = analysis_target
        
        # レベルフィルター
        level_options = ["未学習", "レベル0", "レベル1", "レベル2", "レベル3", "レベル4", "習得済み"]
        # デフォルトは学習済みデータ重視（未学習除外）
        default_levels = ["レベル0", "レベル1", "レベル2", "レベル3", "レベル4", "習得済み"]
        level_filter = st.multiselect(
            "表示レベル",
            level_options,
            default=st.session_state.get("level_filter", default_levels),
            key="level_filter_selector"
        )
        
        if level_filter != st.session_state.get("level_filter"):
            st.session_state["level_filter"] = level_filter
        
        # 新規カード数設定
        new_cards_per_day = st.slider(
            "1日の新規カード数",
            min_value=1,
            max_value=50,
            value=st.session_state.get("new_cards_per_day", 10),
            key="new_cards_slider"
        )
        
        if new_cards_per_day != st.session_state.get("new_cards_per_day"):
            st.session_state["new_cards_per_day"] = new_cards_per_day
            st.session_state["settings_changed"] = True
    
    def _render_main_content(self):
        """メインコンテンツの描画（ページ選択対応）"""
        current_page = st.session_state.get("page", "練習")
        
        if current_page == "ランキング":
            render_updated_ranking_page()
        elif current_page == "検索・進捗":
            from modules.search_page import render_search_page
            render_search_page()
        else:
            render_practice_page(self.auth_manager)
    
    def _handle_login(self, email: str, password: str, remember_me: bool):
        """ログイン処理"""
        with st.spinner("ログイン中..."):
            result = self.auth_manager.signin(email, password)
            
            if "error" in result:
                # ❌ Failure: エラーメッセージを表示
                error_message = result["error"]["message"]
                if "INVALID_PASSWORD" in error_message:
                    st.error("パスワードが正しくありません")
                elif "EMAIL_NOT_FOUND" in error_message:
                    st.error("このメールアドレスは登録されていません")
                elif "INVALID_EMAIL" in error_message:
                    st.error("メールアドレスの形式が正しくありません")
                else:
                    st.error(f"ログインエラー: {error_message}")
            else:
                # ✅ Success: ログイン成功
                st.success("ログインしました！")
                
                # Cookie Saving: チェックボックスがオンの場合
                if remember_me:
                    cookie_data = {
                        "refresh_token": result.get("refreshToken", ""),
                        "uid": st.session_state.get("uid", ""),
                        "email": email
                    }
                    self.cookie_manager.save_login_cookies(cookie_data)
                
                # Google Analytics イベント
                uid = st.session_state.get("uid")
                if uid:
                    log_to_ga("login", uid, {"method": "email"})
                
                # 科目の初期化（ログイン後にユーザー権限を反映）
                self._initialize_available_subjects()
                
                # Rerun: アプリをリロードしてメインインターフェースへ
                time.sleep(0.5)
                st.rerun()
    
    def _handle_signup(self, email: str, password: str):
        """新規登録処理"""
        with st.spinner("アカウント作成中..."):
            result = self.auth_manager.signup(email, password)
            
            if "error" in result:
                # ❌ Failure: エラーメッセージを表示
                error_message = result["error"]["message"]
                if "EMAIL_EXISTS" in error_message:
                    st.error("このメールアドレスは既に登録されています")
                elif "WEAK_PASSWORD" in error_message:
                    st.error("パスワードが弱すぎます。6文字以上の強いパスワードを設定してください")
                elif "INVALID_EMAIL" in error_message:
                    st.error("メールアドレスの形式が正しくありません")
                else:
                    st.error(f"登録エラー: {error_message}")
            else:
                # ✅ Success: 成功メッセージを表示
                st.success("🎉 アカウントを作成しました！「ログイン」タブからサインインしてください。")
    
    def _handle_password_reset(self, email: str):
        """パスワードリセット処理"""
        with st.spinner("リセットメール送信中..."):
            result = self.auth_manager.reset_password(email)
            
            if result["success"]:
                # ✅ Success: 成功メッセージを表示
                st.success("📧 パスワードリセットメールを送信しました。メールをご確認ください。")
            else:
                # ❌ Failure: エラーメッセージを表示
                error_message = result["message"]
                if "EMAIL_NOT_FOUND" in error_message:
                    st.error("このメールアドレスは登録されていません")
                elif "INVALID_EMAIL" in error_message:
                    st.error("メールアドレスの形式が正しくありません")
                else:
                    st.error(f"エラー: {error_message}")


def main():
    """メイン関数"""
    # 強化されたGoogle Analytics初期化
    # if enhanced_ga.initialize_ga():
    #     # 初回初期化時にページビューを追跡
    #     enhanced_ga.track_page_view('main_app', '歯科国家試験対策アプリ')
    
    app = DentalApp()
    app.run()


if __name__ == "__main__":
    main()
