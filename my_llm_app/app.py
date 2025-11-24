"""
歯科国家試験対策アプリ - メインファイル（リファクタリング版）

主な変更点:
- サービスクラスによるモジュール化
- 責任の分離による保守性向上
- クリーンアーキテクチャの適用
"""

import streamlit as st
import datetime
import pytz
import time

# 日本時間用のタイムゾーン
JST = pytz.timezone('Asia/Tokyo')

# ローカル開発用デバッグフラグ
LOCAL_DEBUG_MODE = False

def get_japan_now() -> datetime.datetime:
    """日本時間の現在時刻を取得"""
    return datetime.datetime.now(JST)

# Streamlit設定
st.set_page_config(
    page_title="歯科国家試験AI対策アプリ",
    page_icon="🦷",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Google Analytics初期化
try:
    from utils import AnalyticsUtils, GA_MEASUREMENT_ID
    
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
    
    if 'ga_early_init' not in st.session_state:
        AnalyticsUtils.inject_ga_script()
        st.session_state['ga_early_init'] = True
except ImportError:
    pass

# Service imports
from modules.services.auth_service import AuthService
from modules.services.navigation_manager import NavigationManager
from modules.services.app_initializer import AppInitializer
from modules.services.tracking_service import TrackingService

# Other imports
from auth import AuthManager, get_user_permission
from firestore_db import get_firestore_manager
from utils import AnalyticsUtils


class DentalApp:
    """
    歯科国家試験対策アプリのメインクラス（リファクタリング版）
    
    このクラスは各サービスクラスを調整し、アプリケーションの
    高レベルフローを管理します。
    """
    
    def __init__(self):
        """Initialize the application and its services."""
        # Services will be initialized after authentication
        self.auth_service = None
        self.nav_manager = None
        self.initializer = None
        self.tracker = None
        
        # Initialize authentication manager for local debug mode
        if LOCAL_DEBUG_MODE:
            self._setup_debug_mode()
    
    def _setup_debug_mode(self):
        """Setup debug mode with dummy user."""
        st.session_state["user_logged_in"] = True
        st.session_state["uid"] = "debug_user"
        st.session_state["email"] = "debug@example.com"
        st.session_state["name"] = "デバッグユーザー"
    
    def run(self):
        """
        Main application entry point.
        
        Orchestrates the authentication, initialization, and page rendering flow.
        """
        # Initialize Google Analytics
        AnalyticsUtils.inject_ga_script()
        
        # Check authentication status
        if not self._is_authenticated():
            self._handle_unauthenticated()
            return
        
        # User is authenticated - initialize services and render main app
        self._handle_authenticated()
    
    def _is_authenticated(self) -> bool:
        """
        Check if user is authenticated.
        
        Returns:
            bool: True if user is logged in
        """
        if LOCAL_DEBUG_MODE:
            return True
        
        # Try auto-login first (if not already attempted)
        if not st.session_state.get("auto_login_attempted"):
            st.session_state["auto_login_attempted"] = True
            
            auth_service = AuthService()
            if auth_service.try_auto_login():
               # Initialize services after successful auto-login
                self._initialize_services_after_login()
                st.rerun()
        
        # Check if user has valid session
        is_auth = (st.session_state.get("user_logged_in") and 
                st.session_state.get("uid") is not None)
        print(f"[DEBUG] _is_authenticated result: {is_auth}, user_logged_in: {st.session_state.get('user_logged_in')}, uid: {st.session_state.get('uid')}")
        return is_auth
    
    def _handle_unauthenticated(self):
        """Handle unauthenticated state - show login page."""
        if not self.auth_service:
            self.auth_service = AuthService()
        
        # デバッグ: セッション状態を確認
        print(f"[DEBUG] _handle_unauthenticated - user_logged_in: {st.session_state.get('user_logged_in')}, uid: {st.session_state.get('uid')}")
        
        # Render login page
        authenticated = self.auth_service.render_login_page()
        
        if authenticated:
            print(f"[DEBUG] Authenticated! Initializing services...")
            # User just logged in - initialize services
            self._initialize_services_after_login()
            st.rerun()
        
        # Track login page view
        if not LOCAL_DEBUG_MODE:
            tracker = TrackingService(local_debug_mode=LOCAL_DEBUG_MODE)
            tracker.track_page_navigation("login")
    
    def _handle_authenticated(self):
        """Handle authenticated state - show main app."""
        print(f"[DEBUG] _handle_authenticated called")
        
        # Get user ID
        uid = st.session_state.get("uid")
        email = st.session_state.get("email", "")
        print(f"[DEBUG] uid: {uid}, email: {email}")
        
        # Initialize services if not already done
        if not self.initializer:
            print(f"[DEBUG] Initializing services...")
            self._initialize_services(uid, email)
        else:
            print(f"[DEBUG] Services already initialized")
        
        # Lazy load user data and subjects
        print(f"[DEBUG] Ensuring data loaded...")
        self._ensure_data_loaded()
        
        # Track user activity
        if not LOCAL_DEBUG_MODE:
            print(f"[DEBUG] Tracking user activity...")
            self.tracker.track_user_activity()
        
        # Render main content first
        print(f"[DEBUG] Rendering main content...")
        self.nav_manager.render_main_content()
        
        # Then render sidebar
        print(f"[DEBUG] Rendering sidebar...")
        selected_page = self.nav_manager.render_sidebar()
        print(f"[DEBUG] Sidebar rendered, selected_page: {selected_page}")
        
        # Track page navigation
        if not LOCAL_DEBUG_MODE:
            self.tracker.track_page_navigation(selected_page)
    
    def _initialize_services_after_login(self):
        """Initialize services after successful login."""
        uid = st.session_state.get("uid")
        
        if uid:
            # Initialize user profile
            initializer = AppInitializer(uid)
            initializer.initialize_user_profile()
            
            # Track login success
            if not LOCAL_DEBUG_MODE:
                tracker = TrackingService(uid, LOCAL_DEBUG_MODE)
                user_info = {
                    'uid': uid,
                    'email': st.session_state.get('email'),
                    'has_gakushi_permission': get_user_permission()
                }
                tracker.track_user_login_success(user_info)
                
                # Track with Google Analytics
                AnalyticsUtils.track_user_login(uid, 'auto_login')
                AnalyticsUtils.track_page_view('main_app_auto_login')
            
            # Reset styles flag
            st.session_state["styles_applied"] = False
    
    def _initialize_services(self, uid: str, email: str):
        """
        Initialize all service instances.
        
        Args:
            uid: User ID
            email: User email
        """
        # Initialize services
        self.initializer = AppInitializer(uid)
        self.tracker = TrackingService(uid, LOCAL_DEBUG_MODE)
        
        # Initialize tracking
        if not LOCAL_DEBUG_MODE:
            self.tracker.initialize_tracking()
        
        # Create navigation manager with tracking callback
        def tracking_callback(event_type: str, data):
            if event_type == "page_navigation":
                self.tracker.track_page_navigation(data)
            elif event_type == "feature_interaction":
                self.tracker.track_feature_interaction(
                    data.get("feature"),
                    data.get("action"),
                    data.get("context")
                )
        
        self.nav_manager = NavigationManager(uid, email, tracking_callback)
        
        # Initialize session state if needed
        if not st.session_state.get("user_profile"):
            self.initializer.initialize_user_profile()
    
    def _ensure_data_loaded(self):
        """Ensure user data and subjects are loaded (lazy loading)."""
        # Load cards data if not already loaded
        if not st.session_state.get("cards"):
            if LOCAL_DEBUG_MODE:
                st.session_state["cards"] = {}
            else:
                with st.spinner("学習データを読み込んでいます..."):
                    self.initializer.load_user_data()
        
        # Initialize subjects if not already done
        if not st.session_state.get("available_subjects"):
            self.initializer.initialize_available_subjects()


def main():
    """Application entry point."""
    app = DentalApp()
    app.run()


if __name__ == "__main__":
    main()
