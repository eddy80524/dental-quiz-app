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
from modules.ranking_page import render_ranking_page


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
/* ライトモード固定設定 */
.stApp {
    background-color: #ffffff;
    color: #000000;
}

.stSidebar {
    background-color: #f0f2f6;
}

/* サイドバーのボタン色を統一 */
.stSidebar .stButton > button[kind="primary"] {
    background-color: #0066cc !important;
    color: white !important;
    border: none !important;
}

.stSidebar .stButton > button[kind="primary"]:hover {
    background-color: #0052a3 !important;
    color: white !important;
}

.stSidebar .stButton > button[kind="primary"]:focus {
    background-color: #0066cc !important;
    color: white !important;
    box-shadow: 0 0 0 0.2rem rgba(0, 102, 204, 0.25) !important;
}

/* 問題カードのスタイル */
.question-card {
    background-color: #f8f9fa;
    border: 1px solid #dee2e6;
    border-radius: 8px;
    padding: 20px;
    margin: 10px 0;
}

/* メトリクスのスタイル */
.metric-container {
    background-color: #f8f9fa;
    padding: 15px;
    border-radius: 8px;
    border-left: 4px solid #0066cc;
}
</style>""", unsafe_allow_html=True)


class DentalApp:
    """歯科国家試験対策アプリのメインクラス"""
    
    def __init__(self):
        self.auth_manager = AuthManager()
        self.cookie_manager = CookieManager()
        self.firestore_manager = get_firestore_manager()
        
        # セッション状態の初期化
        self._initialize_session_state()
    
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
            "level_filter": ["未学習", "レベル0", "レベル1", "レベル2", "レベル3", "レベル4", "レベル5", "習得済み"],  # 全レベルをデフォルトで表示
            "new_cards_per_day": 10,
            "result_log": {},
            "auto_login_attempted": False  # 自動ログイン試行フラグを追加
        }
        
        for key, value in default_values.items():
            if key not in st.session_state:
                st.session_state[key] = value
        
        # 科目の初期化
        self._initialize_available_subjects()
    
    def _initialize_available_subjects(self):
        """利用可能な科目を初期化"""
        if 'available_subjects' not in st.session_state:
            uid = st.session_state.get("uid")
            has_gakushi_permission = check_gakushi_permission(uid) if uid else False
            analysis_target = st.session_state.get("analysis_target", "国試")
            
            # 分析対象に応じて科目を取得
            subjects_set = set()
            for q in ALL_QUESTIONS:
                q_num = q.get("number", "")
                
                # 権限チェック
                if q_num.startswith("G") and not has_gakushi_permission:
                    continue
                
                # 分析対象フィルタ
                if analysis_target == "学士試験":
                    if not q_num.startswith("G"):
                        continue
                elif analysis_target == "国試":
                    if q_num.startswith("G"):
                        continue
                
                subject = q.get("subject", "未分類")
                if subject:
                    subjects_set.add(subject)
            
            available_subjects = sorted(list(subjects_set))
            st.session_state.available_subjects = available_subjects
            
            # 科目フィルターのデフォルト設定
            if 'subject_filter' not in st.session_state:
                st.session_state.subject_filter = available_subjects
    
    def run(self):
        """アプリケーションのメイン実行"""
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
                st.rerun()
        
        # ログイン状態をチェック
        if not st.session_state.get("user_logged_in") or not self.auth_manager.ensure_valid_session():
            # ログイン画面ではサイドバーを非表示
            self._hide_sidebar()
            self._render_login_page()
            AnalyticsUtils.track_page_view("Login Page")
        else:
            # ログイン済みの場合はサイドバーとメインコンテンツを表示
            # 科目が初期化されていない場合は初期化
            if not hasattr(st.session_state, 'available_subjects') or not st.session_state.available_subjects:
                self._initialize_available_subjects()
            
            self._render_sidebar()
            self._render_main_content()
            
            # ログイン後のページビュー追跡
            current_page = st.session_state.get("current_page", "演習")
            AnalyticsUtils.track_page_view(f"Main App - {current_page}")
    
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
        
        # ページが変更された場合はイベントを送信
        if new_page and new_page != st.session_state.get("page"):
            st.session_state["page"] = new_page
            st.session_state["current_page"] = new_page  # _track_user_activityで使用
            
            if uid:
                log_to_ga("page_change", uid, {
                    "previous_page": current_page,
                    "new_page": new_page,
                    "navigation_method": "sidebar"
                })
        
        st.divider()
        
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
            
            # 分析対象フィルター
            if has_gakushi_permission:
                # 分析対象変更時のコールバック
                def on_analysis_target_change():
                    # 科目リストを更新
                    if 'available_subjects' in st.session_state:
                        del st.session_state['available_subjects']
                    if 'subject_filter' in st.session_state:
                        del st.session_state['subject_filter']
                    # 科目を再初期化
                    self._initialize_available_subjects()
                
                analysis_target = st.radio(
                    "分析対象",
                    ["国試", "学士試験"],
                    key="analysis_target",
                    on_change=on_analysis_target_change
                )
            else:
                # 権限がない場合は自動的に国試に設定
                analysis_target = "国試"
                if 'analysis_target' not in st.session_state:
                    st.session_state.analysis_target = "国試"
            
            # 学習レベルフィルター
            level_options = ["未学習", "レベル0", "レベル1", "レベル2", "レベル3", "レベル4", "レベル5", "習得済み"]
            level_filter = st.multiselect(
                "学習レベル",
                level_options,
                default=level_options,  # 全ての選択肢をデフォルトで選択
                key="level_filter"
            )
            
            # 科目フィルター（動的UI）
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
        else:
            # 練習ページのサイドバー
            from modules.practice_page import render_practice_sidebar
            render_practice_sidebar()
        
        # ログアウトボタン
        st.divider()
        if st.button("🚪 ログアウト", type="secondary", use_container_width=True):
            self._handle_logout()
    
    def _handle_logout(self):
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
                self._start_auto_learning()
                
        except Exception as e:
            st.error(f"おまかせ学習モードでエラー: {str(e)}")
            st.exception(e)
    
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
        
        with st.spinner("最適な問題を選択中..."):
            # Cloud Function呼び出しを再有効化（URLを修正したため）
            use_local_fallback = False
            
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
                next_review = card.get("next_review", "")
                history = card.get("history", [])
                
                # 復習期限チェック
                if next_review and next_review <= today:
                    review_questions.append(q_id)
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
                selected_year = st.session_state.get("free_gakushi_year", "2024年度").replace("年度", "")
                selected_kaisu = st.session_state.get("free_gakushi_kaisu", "1回")
                selected_area = st.session_state.get("free_gakushi_area", "全領域")
                
                for q in ALL_QUESTIONS:
                    q_num = q.get("number", "")
                    # 学士問題のみ
                    if not q_num.startswith("G"):
                        continue
                    
                    # 年度と回数フィルタ（例：G24-1-1）
                    year_short = str(int(selected_year) - 2000)  # 2024 -> 24
                    kaisu_num = selected_kaisu.replace("回", "")
                    pattern = f"G{year_short}-{kaisu_num}"
                    
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
    
    def _handle_logout(self):
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
        level_options = ["未学習", "レベル0", "レベル1", "レベル2", "レベル3", "レベル4", "レベル5", "習得済み"]
        # デフォルトは学習済みデータ重視（未学習除外）
        default_levels = ["レベル0", "レベル1", "レベル2", "レベル3", "レベル4", "レベル5", "習得済み"]
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
            render_ranking_page(self.auth_manager)
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
    app = DentalApp()
    app.run()


if __name__ == "__main__":
    main()
