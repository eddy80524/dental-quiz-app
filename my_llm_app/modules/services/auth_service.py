"""
Authentication Service Module

Handles all authentication-related UI and logic extracted from app.py.
This module provides a clean interface for user authentication including:
- Login with email/password
- New user signup
- Password reset
- Automatic login via cookies
"""

import streamlit as st
import time
from auth import AuthManager, CookieManager
from utils import log_to_ga


class AuthService:
    """
    Service class for handling authentication UI and logic.
    
    This class manages the complete authentication flow including:
    - Rendering login/signup/reset UI
    - Processing authentication requests
    - Managing cookies for auto-login
    - Tracking authentication events
    """
    
    def __init__(self):
        """Initialize the authentication service with required managers."""
        self.auth_manager = AuthManager()
        self.cookie_manager = CookieManager()
    
    def render_login_page(self) -> bool:
        """
        Render the complete login page with tabs for login, signup, and password reset.
        
        Returns:
            bool: True if user is authenticated, False otherwise
        """
        st.title("🦷 歯科国家試験AI対策アプリ")
        st.markdown("### 🔐 ログイン／新規登録")
        
        tab_login, tab_signup, tab_reset = st.tabs(["ログイン", "新規登録", "パスワードリセット"])
        
        with tab_login:
            self._render_login_tab()
        
        with tab_signup:
            self._render_signup_tab()
        
        with tab_reset:
            self._render_reset_tab()
        
        # Check if authentication was successful
        return st.session_state.get("uid") is not None
    
    def _render_login_tab(self):
        """Render the login tab with email/password form."""
        # Create a container for the form
        login_container = st.empty()
        
        # Initialize session state for input values
        if "login_email_value" not in st.session_state:
            # Get saved email from cookies
            saved_email = self.cookie_manager.get_saved_email()
            st.session_state["login_email_value"] = saved_email
        
        if "login_password_value" not in st.session_state:
            st.session_state["login_password_value"] = ""
        
        with login_container.container():
            # Show password saved status
            has_saved_password = self.cookie_manager.has_saved_password()
            if has_saved_password:
                st.info("🔐 ログイン情報が保存されています。通常はアプリ起動時に自動ログインされます。")
            
            # CSS for browser password autofill
            st.markdown("""
            <style>
            /* Enable browser password autofill */
            input[type="password"] {
                autocomplete: current-password !important;
            }
            /* Enable email autofill */
            input[data-testid="textInput"]:first-of-type {
                autocomplete: email !important;
            }
            /* Form identification */
            form[data-testid="form"] {
                name: "login-form";
            }
            </style>
            """, unsafe_allow_html=True)
            
            # Login form
            with st.form("login_form", clear_on_submit=False):
                email = st.text_input(
                    "メールアドレス", 
                    value=st.session_state["login_email_value"],
                    placeholder="your-email@example.com",
                    key="login_email_input"
                )
                
                password = st.text_input(
                    "パスワード", 
                    type="password",
                    value=st.session_state["login_password_value"],
                    placeholder="パスワードを入力",
                    key="login_password_input"
                )
                
                # Save password option
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
                
                # Login button
                login_submitted = st.form_submit_button("ログイン", type="primary", use_container_width=True)
                
            # JavaScript for autocomplete attributes
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
                
            # Handle login submission
            if login_submitted:
                if email and password:
                    # Update session state
                    st.session_state["login_email_value"] = email
                    st.session_state["login_password_value"] = password
                    
                    # Replace form with spinner
                    login_container.empty()
                    with login_container.container():
                        with st.spinner("ログイン中..."):
                            # Perform login
                            result = self.auth_manager.signin(email, password)
                            
                            if "error" in result:
                                # Login failed
                                error_message = result["error"]["message"]
                                if "INVALID_PASSWORD" in error_message or "INVALID_LOGIN_CREDENTIALS" in error_message:
                                    st.error("メールアドレスまたはパスワードが正しくありません")
                                elif "USER_DISABLED" in error_message:
                                    st.error("このアカウントは無効化されています")
                                elif "EMAIL_NOT_FOUND" in error_message:
                                    st.error("このメールアドレスは登録されていません")
                                else:
                                    st.error(f"ログインエラー: {error_message}")
                            else:
                                # Login successful
                                # AuthManager.signin() already updated session_state
                                uid = st.session_state.get("uid")
                                
                                # Save password if requested
                                if save_password and uid:
                                    refresh_token = st.session_state.get("refresh_token", "")
                                    login_data = {
                                        "uid": uid,
                                        "email": email,
                                        "refresh_token": refresh_token,
                                        "password": password
                                    }
                                    self.cookie_manager.save_login_cookies(login_data, save_password=True)
                                
                                # Track login success
                                if uid:
                                    log_to_ga("login", uid, {"method": "email"})
                                
                                st.success("✅ ログインしました！")
                                
                                # Reset styles flag
                                st.session_state["styles_applied"] = False
                                
                                # Reload app
                                time.sleep(0.5)
                                st.rerun()
                else:
                    st.error("メールアドレスとパスワードを入力してください")
    
    def _render_signup_tab(self):
        """Render the signup tab for new user registration."""
        # Temporary signup disable flag
        SIGNUP_TEMPORARILY_DISABLED = False
        
        if SIGNUP_TEMPORARILY_DISABLED:
            st.warning("🚧 新規登録は一時的に停止中です")
            st.info("既存のアカウントをお持ちの方は「ログイン」タブからログインしてください。")
        else:
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
        """Render the password reset tab."""
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
    
    def _handle_signup(self, email: str, password: str):
        """
        Handle new user signup.
        
        Args:
            email: User's email address
            password: User's password
        """
        with st.spinner("アカウント作成中..."):
            result = self.auth_manager.signup(email, password)
            
            if "error" in result:
                # Signup failed
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
                # Signup successful
                st.success("🎉 アカウントを作成しました！「ログイン」タブからサインインしてください。")
    
    def _handle_password_reset(self, email: str):
        """
        Handle password reset request.
        
        Args:
            email: User's email address
        """
        with st.spinner("リセットメール送信中..."):
            result = self.auth_manager.reset_password(email)
            
            if result["success"]:
                # Reset successful
                st.success("📧 パスワードリセットメールを送信しました。メールをご確認ください。")
            else:
                # Reset failed
                error_message = result["message"]
                if "EMAIL_NOT_FOUND" in error_message:
                    st.error("このメールアドレスは登録されていません")
                elif "INVALID_EMAIL" in error_message:
                    st.error("メールアドレスの形式が正しくありません")
                else:
                    st.error(f"エラー: {error_message}")
    
    def try_auto_login(self) -> bool:
        """
        Attempt automatic login using saved cookies.
        
        Returns:
            bool: True if auto-login successful, False otherwise
        """
        return self.cookie_manager.try_auto_login()
    
    def handle_quick_login(self, email: str) -> bool:
        """
        Handle quick login (deprecated, kept for compatibility).
        
        Args:
            email: User's email address
            
        Returns:
            bool: True if login successful, False otherwise
        """
        with st.spinner("簡単ログイン中..."):
            if self.cookie_manager.try_auto_login():
                st.success("簡単ログインしました！")
                
                # Track login
                uid = st.session_state.get("uid")
                if uid:
                    log_to_ga("login", uid, {"method": "quick_login_deprecated"})
                
                # Reset styles flag
                st.session_state["styles_applied"] = False
                
                time.sleep(0.5)
                st.rerun()
                return True
            else:
                st.error("簡単ログインに失敗しました。通常のログインをお試しください。")
                self.cookie_manager.clear_saved_password()
                return False
