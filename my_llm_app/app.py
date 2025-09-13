"""
歯科国家試験対策アプリ - メインファイル（高速最適化版）

主な変更点:
- モジュール化された構造
- UID統一によるユーザー管理
- 高速パフォーマンス最適化（練習ページ同等）
- セキュリティ強化
- practice_page.py UnboundLocalError修正済み (2025-08-30)
- 検索・進捗ページ高速化対応
"""

import streamlit as st
import datetime
import pytz
import time
from typing import List
import re
import random
from typing import Optional
from collections import Counter

# 日本時間用のタイムゾーン
JST = pytz.timezone('Asia/Tokyo')

# ローカル開発用デバッグフラグ
LOCAL_DEBUG_MODE = False  # Firebaseをスキップしてローカルテスト可能

def get_japan_now() -> datetime.datetime:
    """日本時間の現在時刻を取得"""
    return datetime.datetime.now(JST)

# Streamlit設定 - サイドバーを自動展開
st.set_page_config(
    page_title="歯科国家試験AI対策アプリ",
    page_icon="🦷",
    layout="wide",
    initial_sidebar_state="expanded"  # サイドバーを展開状態で開始
)

# 早期にGoogle Analyticsを初期化
try:
    from utils import AnalyticsUtils, GA_MEASUREMENT_ID
    
    # HTMLヘッダーにGoogle Analyticsタグを挿入
    ga_head_html = f"""
    <script async src="https://www.googletagmanager.com/gtag/js?id={GA_MEASUREMENT_ID}"></script>
    <script>
      window.dataLayer = window.dataLayer || [];
      function gtag(){{dataLayer.push(arguments);}}
      gtag('js', new Date());
      gtag('config', '{GA_MEASUREMENT_ID}');
    </script>
    """
    st.markdown(ga_head_html, unsafe_allow_html=True)
    
    # ページロード時に即座にAnalyticsを初期化
    if 'ga_early_init' not in st.session_state:
        AnalyticsUtils.inject_ga_script()
        st.session_state['ga_early_init'] = True
except ImportError:
    pass

# モジュールのインポート
from auth import AuthManager, CookieManager, call_cloud_function, get_user_permission
from firestore_db import get_firestore_manager, check_gakushi_permission, save_user_data, get_user_profile_for_ranking, save_user_profile
from utils import (
    ALL_QUESTIONS,
    log_to_ga, 
    AnalyticsUtils,
    get_natural_sort_key
)

# 必修問題セットは後でインポート（循環import回避）
try:
    from utils import HISSHU_Q_NUMBERS_SET, GAKUSHI_HISSHU_Q_NUMBERS_SET
except ImportError:
    # フォールバック: 空のセットを定義
    HISSHU_Q_NUMBERS_SET = set()
    GAKUSHI_HISSHU_Q_NUMBERS_SET = set()
    print("[WARNING] HISSHU_Q_NUMBERS_SET と GAKUSHI_HISSHU_Q_NUMBERS_SET のインポートに失敗しました")

# ページモジュールのインポート（高速化対応）
from modules.practice_page import render_practice_page, render_practice_sidebar
from modules.updated_ranking_page import render_updated_ranking_page

# パフォーマンス最適化は無効化
OPTIMIZATION_ENABLED = False
print("[INFO] パフォーマンス最適化モジュールは無効化されています")

# from enhanced_analytics import enhanced_ga, EnhancedGoogleAnalytics

# 最適化モジュールのインポート (不要なものはコメントアウト)
# from enhanced_firestore_optimizer import get_cached_firestore_optimizer
# from optimized_weekly_ranking import OptimizedWeeklyRankingSystem
# from complete_migration_system import CompleteMigrationSystem
# パフォーマンス最適化は無効化
def apply_performance_optimizations():
    """パフォーマンス最適化の無効化版"""
    pass

# 科目マッピングのインポート
from subject_mapping import get_standardized_subject, get_all_standardized_subjects, analyze_subject_mapping


def apply_sidebar_button_styles():
    """
    サイドバーのボタンにシンプルなスタイリングを適用する関数
    """
    # デフォルトのスタイルを使用するため、何も適用しない
    pass


def render_profile_settings_in_sidebar(uid: str):
    """全ページ共通のサイドバー用プロフィール設定UIを描画"""
    import time
    
    # 現在のプロフィールを取得
    current_profile = get_user_profile_for_ranking(uid)
    
    # デフォルト値の設定
    default_nickname = ""
    default_show_on_leaderboard = True
    
    if current_profile:
        default_nickname = current_profile.get("nickname", "")
        default_show_on_leaderboard = current_profile.get("show_on_leaderboard", True)
    
    # ランキング表示設定は updated_ranking_page.py で統合管理


# アプリバージョン
APP_VERSION = "2024-08-24-refactored"


class DentalApp:
    """歯科国家試験対策アプリのメインクラス"""
    
    def __init__(self):
        # パフォーマンス最適化を最初に適用
        apply_performance_optimizations()
        
        # ローカルデバッグモードの場合はFirebaseをスキップ
        if LOCAL_DEBUG_MODE:
            self.auth_manager = None
            self.cookie_manager = None  
            self.firestore_manager = None
            # ダミーユーザー情報を設定
            st.session_state["user_logged_in"] = True
            st.session_state["uid"] = "debug_user"
            st.session_state["email"] = "debug@example.com"
            st.session_state["name"] = "デバッグユーザー"
        else:
            self.auth_manager = AuthManager()
            self.cookie_manager = CookieManager()
            self.firestore_manager = get_firestore_manager()
        
        # 強化されたGoogle Analytics統合
        # self.analytics = enhanced_ga
        
        # セッション状態の初期化
        self._initialize_session_state()
        
        # ユーザー行動追跡の初期化
        if not LOCAL_DEBUG_MODE:
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
            "level_filter": ["未学習", "レベル0", "レベル1", "レベル2", "レベル3", "レベル4", "レベル5", "習得済み"],  # 統一7レベル分類
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
        # Google Analytics ページビュー
        AnalyticsUtils.track_page_view(page_name)
        
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
        """ログイン成功追跡（日本時間ベース）"""
        user_properties = {
            'user_type': 'registered' if user_info.get('uid') else 'anonymous',
            'login_timestamp': get_japan_now().isoformat(),  # 日本時間で記録
            'has_gakushi_permission': user_info.get('has_gakushi_permission', False)
        }
        
        # Google Analytics追跡
        uid = user_info.get('uid')
        if uid:
            AnalyticsUtils.track_user_login(uid, 'manual_login')
            AnalyticsUtils.track_page_view('main_app_manual_login')
        
        # self.analytics.track_user_login(
        #     login_method='firebase',
        #     user_properties=user_properties
        # )
        
        # ユーザープロパティ更新
        # self.analytics.user_id = user_info.get('uid', 'anonymous')
    
    def track_study_activity(self, activity_type: str, details: dict = None):
        """学習活動追跡（日本時間ベース）"""
        base_params = {
            'activity_type': activity_type,
            'timestamp': get_japan_now().isoformat(),  # 日本時間で記録
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
        has_gakushi_permission = get_user_permission() if uid else False
        analysis_target = st.session_state.get("analysis_target", "国試")
        
        # 既に同じ条件で初期化済みの場合はスキップ
        cache_key = f"{uid}_{has_gakushi_permission}_{analysis_target}"
        if (st.session_state.get('available_subjects') and 
            st.session_state.get('subjects_cache_key') == cache_key):
            return
        
        # キャッシュから科目を取得
        try:
            # 分析対象に応じた科目リストを取得
            available_subjects = self._get_subjects_for_target(analysis_target)
            st.session_state.available_subjects = available_subjects
            st.session_state.subjects_cache_key = cache_key
            
            # 科目フィルターのデフォルト設定
            if 'subject_filter' not in st.session_state:
                st.session_state.subject_filter = available_subjects
                
        except Exception:
            # フォールバック処理
            st.session_state.available_subjects = ["一般"]
            st.session_state.subject_filter = ["一般"]
            st.session_state.subjects_cache_key = cache_key
    
    def _initialize_subjects_for_target(self, analysis_target: str):
        """特定の分析対象に対する科目リストを初期化"""
        uid = st.session_state.get("uid")
        has_gakushi_permission = get_user_permission() if uid else False
        
        try:
            # 分析対象に応じた科目リストを直接取得
            available_subjects = self._get_subjects_for_target(analysis_target)
            st.session_state.available_subjects = available_subjects
            st.session_state.subject_filter = available_subjects  # 全て選択状態でリセット
            
            # キャッシュキーを更新
            cache_key = f"{uid}_{has_gakushi_permission}_{analysis_target}"
            st.session_state.subjects_cache_key = cache_key
            
        except Exception:
            # フォールバック
            st.session_state.available_subjects = ["一般"]
            st.session_state.subject_filter = ["一般"]
    
    def _get_subjects_for_target(self, analysis_target: str) -> List[str]:
        """分析対象に応じた科目リストを取得"""
        from utils import ALL_QUESTIONS
        
        subjects = set()
        for question in ALL_QUESTIONS:
            q_number = question.get('number', '')
            
            # 分析対象に応じてフィルタリング
            if analysis_target == "学士試験":
                if q_number.startswith('G'):
                    subjects.add(question.get('subject', '未分類'))
            else:  # 国試
                if not q_number.startswith('G'):
                    subjects.add(question.get('subject', '未分類'))
        
        # 科目をソートして返す
        return sorted(list(subjects)) if subjects else ["一般"]
    
    def _load_user_data(self):
        """ユーザーの演習データを読み込み（最適化されたスキーマ対応・Streamlit Cloud対応）"""
        uid = st.session_state.get("uid")
        if not uid:
            return
        
        # 既にデータが読み込まれている場合はスキップ（強化版）
        if st.session_state.get("cards") and len(st.session_state.get("cards", {})) > 0:
            return
        
        try:
            # Firestore接続の確認（Streamlit Cloud対応）
            firestore_manager = get_firestore_manager()
            if not firestore_manager:
                print("[ERROR] _load_user_data: Firestoreマネージャーの取得に失敗")
                st.session_state["cards"] = {}
                return
                
            db = firestore_manager.db
            if not db:
                print("[ERROR] _load_user_data: Firestoreデータベース接続に失敗")
                st.session_state["cards"] = {}
                return
            
            # 最適化されたstudy_cardsコレクションからユーザーデータを読み込み
            study_cards_ref = db.collection("study_cards")
            user_cards_query = study_cards_ref.where("uid", "==", uid)
            user_cards_docs = user_cards_query.get()
            
            # カードデータを変換（既存の形式に合わせる）
            cards = {}
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
            
            # セッション状態に保存
            st.session_state["cards"] = cards
            
        except Exception as e:
            st.session_state["cards"] = {}
    
    def _initialize_user_profile(self):
        """ユーザープロフィールをセッション状態に初期化"""
        try:
            uid = st.session_state.get("uid")
            if uid:
                # データベースからプロフィールを取得
                profile = get_user_profile_for_ranking(uid)
                if profile:
                    st.session_state["user_profile"] = {
                        "uid": uid,
                        "nickname": profile.get("nickname", f"ユーザー{uid[:8]}"),
                        "show_on_leaderboard": profile.get("show_on_leaderboard", True),
                        "email": st.session_state.get("email", "")
                    }
                else:
                    # プロフィールが存在しない場合はデフォルト値で作成
                    default_nickname = f"ユーザー{uid[:8]}"
                    st.session_state["user_profile"] = {
                        "uid": uid,
                        "nickname": default_nickname,
                        "show_on_leaderboard": True,
                        "email": st.session_state.get("email", "")
                    }
                    # データベースにもデフォルト値を保存
                    save_user_profile(uid, default_nickname, True)
            else:
                st.session_state["user_profile"] = {}
        except Exception as e:
            print(f"ユーザープロフィール初期化エラー: {e}")
            st.session_state["user_profile"] = {}
    
    def run(self):
        """アプリケーションのメイン実行（デフォルト設定版）"""
        # デフォルトのStreamlit設定を使用
        # Google Analytics初期化（最初に実行して確実にロード）
        AnalyticsUtils.inject_ga_script()
        
        # パフォーマンス最適化の適用
        apply_performance_optimizations()
        
        # ユーザーのアクティビティ追跡
        self._track_user_activity()
        
        # 🔄 1. Automatic Login Attempt - ログイン画面表示前に最優先で実行
        if LOCAL_DEBUG_MODE:
            # ローカルデバッグモードの場合は自動的にログイン済み状態
            pass
        elif (not st.session_state.get("user_logged_in") and 
            not st.session_state.get("auto_login_attempted")):
            
            st.session_state["auto_login_attempted"] = True
            # 自動ログインを試行
            if self.cookie_manager.try_auto_login():
                # ★★★ 重い処理はここでは実行しない ★★★
                # self._initialize_available_subjects() # 削除
                # self._load_user_data() # 削除
                
                # ユーザープロフィールをセッション状態に設定
                self._initialize_user_profile()
                
                # ログイン成功追跡
                uid = st.session_state.get('uid')
                if uid:
                    AnalyticsUtils.track_user_login(uid, 'auto_login')
                    AnalyticsUtils.track_page_view('main_app_auto_login')
                user_info = {
                    'uid': st.session_state.get('uid'),
                    'email': st.session_state.get('email'),
                    'has_gakushi_permission': get_user_permission()
                }
                self.track_user_login_success(user_info)
                
                # 自動ログイン成功時は直接メインコンテンツに移行
                st.rerun()
        
        # ログイン状態をチェック
        if LOCAL_DEBUG_MODE or (st.session_state.get("user_logged_in") and (not self.auth_manager or self.auth_manager.ensure_valid_session())):
            # ログイン済みの場合はサイドバーとメインコンテンツを表示
            
            # --- ▼▼▼ 遅延読み込みロジック ▼▼▼ ---
            
            # 1. ユーザープロフィールがなければ初期化
            if not st.session_state.get('user_profile'):
                self._initialize_user_profile()
                
            # 2. 学習データ(cards)がなければ読み込む (最も重い処理)
            if not st.session_state.get("cards"):
                if LOCAL_DEBUG_MODE:
                    # ローカルデバッグモードでは空の学習データ
                    st.session_state["cards"] = {}
                else:
                    with st.spinner("学習データを読み込んでいます..."):
                        self._load_user_data()
            
            # 3. 科目リストがなければ初期化
            if not st.session_state.get('available_subjects'):
                self._initialize_available_subjects()
            
            # --- ▲▲▲ 遅延読み込みロジック ▲▲▲ ---
            
            # メインコンテンツを先に描画
            self._render_main_content()
            
            # その後でサイドバーを描画
            self._render_sidebar()
            
            # ログイン後のページビュー追跡
            current_page = st.session_state.get("page", "練習")
            if not LOCAL_DEBUG_MODE:
                self.track_page_navigation(current_page)
        else:
            # 自動ログインが失敗した場合のみログイン画面を表示
            self._render_login_page()
            
            # ログインページビュー追跡
            if not LOCAL_DEBUG_MODE:
                self.track_page_navigation("login")
    
    def _track_user_activity(self):
        """ユーザーアクティビティの追跡"""
        if LOCAL_DEBUG_MODE:
            return  # ローカルデバッグモードでは追跡をスキップ
            
        try:
            uid = st.session_state.get("uid")
            if uid:
                # セッションの開始追跡（初回のみ）
                if not st.session_state.get("session_tracked"):
                    log_to_ga("session_start", uid, {
                        "session_type": "web_app",
                        "timestamp": get_japan_now().isoformat(),  # 日本時間で記録
                        "user_agent": st.context.headers.get("User-Agent", "unknown") if hasattr(st.context, 'headers') else "unknown"
                    })
                    
                    # Google Analytics セッション開始
                    AnalyticsUtils.track_event('session_start', {
                        'session_type': 'web_app',
                        'user_id': uid
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
                    
                    # Google Analytics エンゲージメント
                    AnalyticsUtils.track_app_engagement()
                    st.session_state["last_activity_logged"] = current_time
                    
        except Exception:
            pass
    
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
        """ログインタブの描画（UI重複防止対応版）"""
        # フォーム全体を配置するための空のコンテナを作成
        login_container = st.empty()
        
        # セッション状態を使って入力値を保持
        if "login_email_value" not in st.session_state:
            # クッキーから保存されたメールアドレスを取得
            saved_email = self.cookie_manager.get_saved_email()
            st.session_state["login_email_value"] = saved_email
        
        if "login_password_value" not in st.session_state:
            st.session_state["login_password_value"] = ""
        
        with login_container.container():
            # パスワード保存状態の表示
            has_saved_password = self.cookie_manager.has_saved_password()
            if has_saved_password:
                st.info("🔐 ログイン情報が保存されています。通常はアプリ起動時に自動ログインされます。")
            
            # ブラウザのパスワード自動入力を有効にするためのCSS
            st.markdown("""
            <style>
            /* ブラウザのパスワード自動入力を有効化 */
            input[type="password"] {
                autocomplete: current-password !important;
            }
            /* メールアドレス入力も自動入力を有効化 */
            input[data-testid="textInput"]:first-of-type {
                autocomplete: email !important;
            }
            /* フォーム識別のための名前属性を設定 */
            form[data-testid="form"] {
                name: "login-form";
            }
            </style>
            """, unsafe_allow_html=True)
            
            # フォーム内で入力フィールドをグループ化
            with st.form("login_form", clear_on_submit=False):
                email = st.text_input(
                    "メールアドレス", 
                    value=st.session_state["login_email_value"],
                    placeholder="your-email@example.com",
                    key="login_email_input"
                )
                
                # パスワード入力（ブラウザの自動入力を抑制）
                password = st.text_input(
                    "パスワード", 
                    type="password",
                    value=st.session_state["login_password_value"],
                    placeholder="パスワードを入力",
                    key="login_password_input"
                )
                
                # パスワード保存オプション
                col1, col2 = st.columns([3, 1])
                with col1:
                    save_password = st.checkbox(
                        "30日間ログイン状態を維持する",
                        value=has_saved_password,
                        key="login_save_password",
                        help="チェックすると、次回からアプリ起動時に自動的にログインされます。共用PCでは使用しないでください。"
                    )
                with col2:
                    if has_saved_password:
                        clear_saved = st.button("🗑️", help="保存されたログイン情報を削除")
                        if clear_saved:
                            self.cookie_manager.clear_saved_password()
                            st.success("保存されたログイン情報を削除しました")
                            st.rerun()
                
                # ログインボタン（シンプルな1つのボタンのみ）
                login_submitted = st.form_submit_button("ログイン", type="primary", use_container_width=True)
                
            # JavaScriptでautocomplete属性を動的に設定（ブラウザの自動入力を有効化）
            st.markdown("""
            <script>
            setTimeout(function() {
                const emailInput = document.querySelector('input[data-testid="textInput"]');
                const passwordInput = document.querySelector('input[type="password"]');
                const form = document.querySelector('form[data-testid="form"]');
                
                if (emailInput) {
                    emailInput.setAttribute('autocomplete', 'email');
                    emailInput.setAttribute('name', 'email');
                }
                if (passwordInput) {
                    passwordInput.setAttribute('autocomplete', 'current-password');
                    passwordInput.setAttribute('name', 'password');
                }
                if (form) {
                    form.setAttribute('name', 'login-form');
                }
            }, 100);
            </script>
            """, unsafe_allow_html=True)
                
            # ログイン処理
            if login_submitted:
                if email and password:
                    # セッション状態を更新
                    st.session_state["login_email_value"] = email
                    st.session_state["login_password_value"] = password
                    
                    # ログインボタンが押されたら、まずフォームをスピナーに置き換える
                    login_container.empty()
                    with login_container.container():
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
                                
                                time.sleep(2)  # エラーメッセージ表示のための待機
                                st.rerun()  # フォームを再表示
                                
                            else:
                                # ✅ Success: ログイン成功
                                st.success("ログインしました！")
                                
                                # Cookie Saving: 長期間有効なリフレッシュトークンをCookieに保存
                                if save_password:
                                    cookie_data = {
                                        "refresh_token": result.get("refreshToken", ""),
                                        "uid": st.session_state.get("uid", ""),
                                        "email": email,
                                        "password": password  # 永続ログイン用にパスワードも保存
                                    }
                                    # 長期間有効なCookieとして保存（30日間）
                                    self.cookie_manager.save_login_cookies(cookie_data, save_password=True)
                                    
                                    # Google Analytics イベント
                                    uid = st.session_state.get("uid")
                                    if uid:
                                        log_to_ga("login", uid, {
                                            "method": "email",
                                            "password_saved": str(save_password)
                                        })
                                    
                                    # ★★★ 重い処理はここでは実行しない ★★★
                                    # self._initialize_available_subjects() # 削除
                                    # self._load_user_data() # 削除
                                    
                                    # ユーザープロフィールは比較的軽量なため、ここで初期化しても良い
                                    self._initialize_user_profile()
                                    
                                    # スタイルを再初期化するためのフラグをリセット
                                    st.session_state["styles_applied"] = False
                                    
                                    time.sleep(0.5)  # 成功メッセージ表示のための短い待機
                                    st.rerun()  # メインページに遷移
                    
                elif not email:
                    st.error("メールアドレスを入力してください")
                elif not password:
                    st.error("パスワードを入力してください")
    
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
        with st.form("reset_form", clear_on_submit=False):
            email = st.text_input(
                "メールアドレス", 
                placeholder="your-email@example.com",
                key="reset_email_input"
            )
            
            submitted = st.form_submit_button("パスワードリセットメールを送信", type="primary", use_container_width=True)
            
            if submitted:
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
        
        selected_page = st.selectbox(
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
        
        # ページが変更された場合はイベントを送信（簡素化版）
        if new_page and new_page != st.session_state.get("page"):
            old_page = st.session_state.get("page", "unknown")
            
            # ページ遷移を実行（デバウンス処理を回避）
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
            
            # ページ変更時に強制リロード
            st.rerun()
        
        # 選択されたページに応じて異なるサイドバーコンテンツを表示
        if st.session_state.get("page") == "ランキング":
            st.markdown("**週間ランキング**で他の学習者と競い合いましょう！")
            
            # ランキング表示設定をここに配置
            st.divider()
            st.markdown("#### 🎭 ランキング表示設定")
            
            # ユーザープロフィール取得
            user_profile = st.session_state.get("user_profile", {})
            
            if user_profile:
                current_nickname = user_profile.get("nickname", f"ユーザー{user_profile.get('uid', '')[:8]}")
                
                # ニックネーム変更
                new_nickname = st.text_input(
                    "ランキング表示名",
                    value=current_nickname,
                    help="ランキングで表示される名前を変更できます",
                    key="ranking_nickname_input"
                )
                
                # ニックネーム更新ボタン
                if st.button("💾 表示名を更新", type="secondary"):
                    if new_nickname and new_nickname != current_nickname:
                        try:
                            # Firestoreのユーザープロフィールを更新
                            from firestore_db import get_firestore_manager
                            uid = user_profile.get("uid")
                            db = get_firestore_manager().db
                            db.collection("users").document(uid).update({
                                "nickname": new_nickname
                            })
                            
                            # セッション状態も更新
                            st.session_state["user_profile"]["nickname"] = new_nickname
                            
                            # ランキングキャッシュをクリア（即座にUI反映のため）
                            if hasattr(st.session_state, '_cache'):
                                st.session_state._cache.clear()
                            
                            st.success(f"✅ 表示名を「{new_nickname}」に更新しました！")
                            st.info("📌 全体ランキングへの反映は毎朝3時の定期更新で行われます。")
                            
                            # ページをリロードして即座に反映
                            st.rerun()
                            
                        except Exception as e:
                            st.error(f"❌ 表示名の更新に失敗しました: {e}")
            else:
                st.info("ユーザープロフィールが読み込まれていません")
                
        elif st.session_state.get("page") == "検索・進捗":
            # --- 検索・進捗ページのサイドバー ---
            # 検索・分析用のフィルター機能のみ
            uid = st.session_state.get("uid")
            has_gakushi_permission = get_user_permission()

            st.markdown("#### 🔍 表示フィルター")

            # 対象範囲
            if has_gakushi_permission:
                analysis_target = st.radio("分析対象", ["国試", "学士試験"], key="analysis_target")
            else:
                analysis_target = "国試"

            # 分析対象が変更された場合、科目リストを更新
            if analysis_target != st.session_state.get("previous_analysis_target"):
                st.session_state["previous_analysis_target"] = analysis_target
                # 科目データを再初期化
                self._initialize_subjects_for_target(analysis_target)
                st.rerun()

            # 学習レベルフィルター
            level_filter = st.multiselect(
                "学習レベル",
                ["未学習", "レベル0", "レベル1", "レベル2", "レベル3", "レベル4", "レベル5", "習得済み"],
                default=["未学習", "レベル0", "レベル1", "レベル2", "レベル3", "レベル4", "レベル5", "習得済み"],
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
            
        else:
            # 練習ページのサイドバー
            from modules.practice_page import render_practice_sidebar
            render_practice_sidebar()
        
        # 学習記録セクション
        st.divider()
        st.markdown("#### 📈 学習記録")
        
        # サイドバーの強制更新チェック
        sidebar_refresh = st.session_state.get("sidebar_refresh_needed", False)
        if sidebar_refresh:
            st.session_state["sidebar_refresh_needed"] = False
        
        # cardsの存在確認を強化
        cards = st.session_state.get("cards", {})
        if cards and len(cards) > 0:
            quality_to_mark = {1: "×", 2: "△", 4: "◯", 5: "◎"}
            mark_to_label = {"◎": "簡単", "◯": "普通", "△": "難しい", "×": "もう一度"}
            
            # カードデータから評価を取得（複数のパターンに対応）
            evaluated_marks = []
            cards_with_evaluations = 0
            
            # セッション状態から最新のcardsを取得
            current_cards = st.session_state.get("cards", cards)
            
            for card_id, card in current_cards.items():
                evaluation_found = False
                
                # パターン1: historyから最新の評価を取得
                history = card.get('history', [])
                if history:
                    last_eval = history[-1]
                    quality = last_eval.get('quality')
                    if quality and quality in quality_to_mark:
                        evaluated_marks.append(quality_to_mark[quality])
                        evaluation_found = True
                        cards_with_evaluations += 1
                
                # パターン2: 直接qualityフィールドから取得
                if not evaluation_found and card.get('quality'):
                    quality = card.get('quality')
                    if quality in quality_to_mark:
                        evaluated_marks.append(quality_to_mark[quality])
                        evaluation_found = True
                        cards_with_evaluations += 1
            
            # パターン3: result_logからも評価を取得（最新の自己評価を反映）
            result_log = st.session_state.get("result_log", {})
            for q_id, result in result_log.items():
                if q_id not in current_cards:  # cardsに既に含まれている場合はスキップ
                    continue
                
                quality = result.get("quality")
                if quality and quality in quality_to_mark:
                    # 既にこの問題の評価が processed されていない場合のみ追加
                    if q_id not in [cid for cid, _ in current_cards.items() if any(h.get('quality') == quality for h in _.get('history', []))]:
                        evaluated_marks.append(quality_to_mark[quality])
                        cards_with_evaluations += 1
            
            total_evaluated = len(evaluated_marks)
            counter = Counter(evaluated_marks)

            with st.expander("自己評価の分布", expanded=True):
                st.markdown(f"**合計評価数：{total_evaluated}問**")
                if total_evaluated > 0:
                    for mark, label in mark_to_label.items():
                        count = counter.get(mark, 0)
                        percent = int(round(count / total_evaluated * 100)) if total_evaluated else 0
                        st.markdown(f"{mark} {label}：{count}問 ({percent}％)")
                else:
                    st.info("まだ評価された問題がありません。")

            with st.expander("最近の評価ログ", expanded=False):
                # 学習履歴があるカードを取得
                cards_with_history = []
                for q_num, card in st.session_state.cards.items():
                    history = card.get('history', [])
                    if history and len(history) > 0:
                        last_history = history[-1]
                        # qualityとtimestampがある履歴のみ有効
                        if last_history.get('quality') and last_history.get('timestamp'):
                            cards_with_history.append((q_num, card))
                
                if cards_with_history:
                    # タイムスタンプでソート（最新順）
                    def get_timestamp_for_sort(item):
                        try:
                            last_history = item[1]['history'][-1]
                            timestamp = last_history.get('timestamp')
                            
                            if hasattr(timestamp, 'isoformat'):
                                return timestamp.isoformat()
                            elif isinstance(timestamp, str):
                                return timestamp
                            else:
                                return "1970-01-01T00:00:00"
                        except Exception:
                            return "1970-01-01T00:00:00"
                    
                    sorted_cards = sorted(cards_with_history, key=get_timestamp_for_sort, reverse=True)
                    
                    for q_num, card in sorted_cards[:10]:
                        last_history = card['history'][-1]
                        quality = last_history.get('quality')
                        eval_mark = quality_to_mark.get(quality, "?")
                        
                        # タイムスタンプ表示
                        timestamp = last_history.get('timestamp')
                        try:
                            if hasattr(timestamp, 'strftime'):
                                timestamp_str = timestamp.strftime('%Y-%m-%d %H:%M')
                            elif isinstance(timestamp, str):
                                timestamp_str = datetime.datetime.fromisoformat(timestamp.replace('Z', '+00:00')).strftime('%Y-%m-%d %H:%M')
                            else:
                                timestamp_str = "不明"
                        except Exception:
                            timestamp_str = "不明"
                        
                        # ジャンプボタンと評価表示
                        col1, col2 = st.columns([1, 4])
                        with col1:
                            jump_btn = st.button(f"{q_num}", key=f"jump_{q_num}")
                        with col2:
                            st.markdown(f"**{eval_mark}** ({timestamp_str})")
                        
                        if jump_btn:
                            st.session_state.current_q_group = [q_num]
                            # 演習関連のセッション状態をクリア
                            for key in list(st.session_state.keys()):
                                if key.startswith(("checked_", "user_selection_", "shuffled_", "free_input_")):
                                    del st.session_state[key]
                            st.rerun()
                else:
                    st.info("まだ学習した問題がありません。")
        else:
            st.info("まだ学習した問題がありません。")
        
        # プロフィール設定セクション
        st.divider()
        uid = st.session_state.get("uid")
        if uid:
            render_profile_settings_in_sidebar(uid)
        
        # ログアウトボタン（保存されたパスワード情報の処理選択肢付き）
        st.divider()
        has_saved_password = self.cookie_manager.has_saved_password()
        
        if has_saved_password:
            st.markdown("#### ⚠️ ログアウト設定")
            keep_password = st.checkbox(
                "パスワード情報を保持する",
                value=True,
                help="チェックを外すと、保存されたパスワード情報も削除されます"
            )
            
            col1, col2 = st.columns([1, 1])
            with col1:
                if st.button("ログアウト", key="logout_btn"):
                    uid = st.session_state.get("uid")
                    save_user_data(uid, session_state=st.session_state)
                    self._handle_logout_real(keep_password)
            with col2:
                if st.button("完全ログアウト", key="full_logout_btn", help="パスワード情報も含めて完全にログアウト"):
                    uid = st.session_state.get("uid")
                    save_user_data(uid, session_state=st.session_state)
                    self._handle_logout_real(False)
        else:
            if st.button("ログアウト", key="logout_btn"):
                uid = st.session_state.get("uid")
                save_user_data(uid, session_state=st.session_state)
                self._handle_logout_real(True)

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
                    from utils import ALL_QUESTIONS
                    questions = [q for q in ALL_QUESTIONS if q.get("number") in question_ids]
                    
                    st.session_state["main_queue"] = questions
                    st.session_state["session_mode"] = "auto_learning"
                    st.session_state["session_choice_made"] = True
                    st.session_state["session_type"] = "おまかせ演習"
                    st.success(f"📚 {len(questions)}問の学習セッションを開始します")
                    AnalyticsUtils.track_study_session_start("auto_learning", len(questions))
                    
                    # Firebase Analytics統合 (無効化)
                    # from firebase_analytics import FirebaseAnalytics
                    # FirebaseAnalytics.log_study_session_start(
                    #     uid=uid,
                    #     session_type="auto_learning",
                    #     metadata={
                    #         "target": st.session_state.get("analysis_target", "国試"),
                    #         "question_count": len(questions),
                    #         "source": "cloud_function"
                    #     }
                    # )
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
                    except Exception:
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
                # utils.pyから問題データを取得（既にインポート済み）
                if ALL_QUESTIONS:
                    # 権限チェック
                    uid = st.session_state.get("uid")
                    if uid and get_user_permission():
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
                # utils.pyから問題データを取得（既にインポート済み）
                uid = st.session_state.get("uid")
                if uid and get_user_permission():
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
        
        # Firebase Analytics統合 (無効化)
        # from firebase_analytics import FirebaseAnalytics
        # FirebaseAnalytics.log_study_session_start(
        #     uid=st.session_state.get("uid"),
        #     session_type="auto_learning_fallback",
        #     metadata={
        #         "target": st.session_state.get("analysis_target", "国試"),
        #         "question_count": len(all_questions),
        #         "source": "local_fallback",
        #         "fallback_reason": "cloud_function_error"
        #     }
        # )
        st.info("📚 ローカル問題選択アルゴリズムを使用しています。")
        st.success(f"📚 {len(all_questions)}問の学習セッションを開始します")
    
    def _render_other_page_settings(self):
        """その他のページでの従来設定表示"""
        uid = st.session_state.get("uid")
        has_gakushi_permission = get_user_permission() if uid else False
        
        if not has_gakushi_permission:
            st.info("📚 学士試験機能を利用するには権限が必要です")
        
        # 設定セクション
        with st.expander("⚙️ 設定"):
            self._render_settings(has_gakushi_permission)
    def _handle_logout_real(self, keep_password: bool = True):
        """ログアウト処理（永続ログイン情報管理付き）"""
        uid = st.session_state.get("uid")
        if uid:
            log_to_ga("logout", uid, {"keep_password": str(keep_password)})
            
            # ログアウト前にセッション状態をFirestoreに保存（完全ログアウト時以外）
            if keep_password and self._has_practice_session():
                try:
                    self._save_current_session_to_firestore()
                    print(f"[LOGOUT] セッション状態をFirestoreに保存しました (uid: {uid})")
                except Exception as e:
                    print(f"[LOGOUT] セッション状態の保存に失敗: {e}")
            
            # 完全ログアウト時はFirestoreのセッション情報も削除
            if not keep_password:
                try:
                    self.firestore_manager.clear_session_state(uid)
                    print(f"[LOGOUT] Firestoreのセッション情報を削除しました (uid: {uid})")
                except Exception as e:
                    print(f"[LOGOUT] Firestoreセッション情報の削除に失敗: {e}")
        
        # セッション状態のクリア
        self.auth_manager.logout()
        
        # Cookie管理: keep_passwordフラグに応じて永続ログイン情報を管理
        if not keep_password:
            # 完全ログアウト: 永続ログイン用のCookieも削除
            self.cookie_manager.clear_saved_password()
            st.success("完全にログアウトしました（永続ログイン情報と演習データも削除）")
        else:
            # 部分ログアウト: 永続ログイン情報は保持
            st.success("ログアウトしました（永続ログイン情報と進行中の演習データは保持）")
        
        # 自動ログイン試行フラグをリセット（次回アクセス時に再試行させる）
        st.session_state.pop("auto_login_attempted", None)
        
        time.sleep(1)
        st.rerun()
    
    def _has_practice_session(self) -> bool:
        """現在進行中の演習セッションがあるかチェック"""
        # 演習関連のセッション状態をチェック
        practice_keys = [
            'questions', 'current_question_index', 'answers', 'confidence_ratings',
            'selected_subjects', 'practice_count', 'correct_answer_displayed',
            'is_practice_complete', 'practice_state'
        ]
        
        # いずれかのキーが存在し、かつ演習が未完了の場合
        has_session = any(key in st.session_state for key in practice_keys)
        is_incomplete = not st.session_state.get('is_practice_complete', False)
        
        return has_session and is_incomplete
    
    def _save_current_session_to_firestore(self):
        """現在のセッション状態をFirestoreに保存"""
        uid = st.session_state.get("uid")
        if not uid:
            return
            
        # 演習セッションのデータを収集
        session_data = {}
        preserve_keys = [
            'questions', 'current_question_index', 'answers', 'confidence_ratings',
            'selected_subjects', 'practice_count', 'correct_answer_displayed',
            'is_practice_complete', 'practice_state', 'practice_start_time'
        ]
        
        for key in preserve_keys:
            if key in st.session_state:
                session_data[key] = st.session_state[key]
        
        if session_data:
            # Firestoreに保存
            try:
                self.firestore_manager.db.collection('user_sessions').document(uid).set({
                    'session_data': session_data,
                    'last_saved': datetime.datetime.now(),
                    'session_type': 'practice'
                })
                print(f"[SESSION_SAVE] セッションデータを保存: {list(session_data.keys())}")
            except Exception as e:
                print(f"[SESSION_SAVE] 保存エラー: {e}")
                raise e
    
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
            render_updated_ranking_page()
        elif current_page == "検索・進捗":
            
            # 遅延インポートで初回ロード高速化
            from modules.search_page import render_search_page
            render_search_page()
        else:
            render_practice_page(self.auth_manager)
    
    def _handle_login(self, email: str, password: str, save_password: bool):
        """ログイン処理（レガシー - 新しいUI統合版で処理されるため簡略化）"""
        # この関数は _render_login_tab 内で直接処理されるようになったため、
        # 基本的には使用されませんが、後方互換性のために残しています
        pass
    
    def _handle_quick_login(self, email: str):
        """
        簡単ログイン処理（非推奨）
        
        注意: この機能は非推奨です。
        現在は app.run() メソッドの開始時に自動的に try_auto_login() が呼び出され、
        有効なCookieがあれば自動的にログイン画面をスキップします。
        """
        with st.spinner("簡単ログイン中..."):
            # 自動ログインを試行
            if self.cookie_manager.try_auto_login():
                st.success("簡単ログインしました！")
                
                # Google Analytics イベント
                uid = st.session_state.get("uid")
                if uid:
                    log_to_ga("login", uid, {"method": "quick_login_deprecated"})
                
                # ★★★ 重い処理はここでは実行しない ★★★
                # self._initialize_available_subjects() # 削除
                # self._load_user_data() # 削除
                
                # ユーザープロフィールを初期化
                self._initialize_user_profile()
                
                # スタイルを再初期化するためのフラグをリセット
                st.session_state["styles_applied"] = False
                
                # Rerun: アプリをリロードしてメインインターフェースへ
                time.sleep(0.5)
                st.rerun()
            else:
                st.error("簡単ログインに失敗しました。通常のログインをお試しください。")
                # 保存されたパスワード情報をクリア
                self.cookie_manager.clear_saved_password()
    
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
