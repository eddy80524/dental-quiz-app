"""
Navigation Manager Service Module

Handles all page navigation and routing logic extracted from app.py.
This module provides a clean interface for managing page selection and rendering.
"""

import streamlit as st
from typing import Optional
from utils import log_to_ga


class NavigationManager:
    """
    Service class for handling page navigation and routing.
    
    This class manages:
    - Page selection via sidebar
    - User menu rendering
    - Page routing logic
    - Navigation event tracking
    """
    
    # Available pages configuration
    PAGES = {
        "練習": {"label": "📚 練習ページ", "index": 0},
        "検索・進捗": {"label": "📊 検索・進捗", "index": 1},
        "ランキング": {"label": "🏆 ランキング", "index": 2},
        "学習メモ": {"label": "📝 学習メモ", "index": 3}
    }
    
    def __init__(self, uid: str, email: str = "", tracking_callback=None):
        """
        Initialize the navigation manager.
        
        Args:
            uid: User ID
            email: User email address
            tracking_callback: Optional callback for tracking events
        """
        self.uid = uid
        self.email = email
        self.tracking_callback = tracking_callback
    
    def render_sidebar(self) -> str:
        """
        Render the complete sidebar with user menu and page selection.
        
        Returns:
            str: Selected page name
        """
        with st.sidebar:
            self._render_user_menu()
        
        return st.session_state.get("page", "練習")
    
    def _render_user_menu(self):
        """Render the user menu in the sidebar."""
        # Get or create user name
        name = st.session_state.get("name", "")
        if not name:
            name = f"学習者{self.uid[:8]}"
            st.session_state["name"] = name
        
        st.success(f"👤 {name} としてログイン中")
        
        # Page selection
        self._render_page_selector()
        
        # Page-specific sidebar content
        current_page = st.session_state.get("page", "練習")
        
        if current_page == "ランキング":
            self._render_ranking_sidebar_content()
        elif current_page == "検索・進捗":
            # 検索・進捗ページのサイドバーを表示
            from modules.search_page import render_search_sidebar
            render_search_sidebar()
        else:
            # デフォルト（練習ページ、学習メモなど）は練習ページのサイドバーを表示
            from modules.practice_page import render_practice_sidebar
            render_practice_sidebar()
    
    def _render_page_selector(self):
        """Render the page selection dropdown."""
        current_page = st.session_state.get("page", "練習")
        
        # Get current index
        current_index = self.PAGES.get(current_page, {}).get("index", 0)
        
        # Create labels list
        page_labels = [info["label"] for page, info in sorted(self.PAGES.items(), key=lambda x: x[1]["index"])]
        
        # Render selector
        selected_label = st.selectbox(
            "ページを選択",
            page_labels,
            index=current_index,
            key="page_selector"
        )
        
        # Map label back to page name
        new_page = None
        for page_name, info in self.PAGES.items():
            if info["label"] == selected_label:
                new_page = page_name
                break
        
        # Handle page change
        if new_page and new_page != current_page:
            self._handle_page_change(current_page, new_page)
    
    def _handle_page_change(self, old_page: str, new_page: str):
        """
        Handle page navigation change.
        
        Args:
            old_page: Previous page name
            new_page: New page name
        """
        # Update session state
        st.session_state["page"] = new_page
        st.session_state["current_page"] = new_page
        
        # Track navigation
        if self.tracking_callback:
            self.tracking_callback("page_navigation", new_page)
            self.tracking_callback("feature_interaction", {
                "feature": "page_navigation",
                "action": "page_change",
                "context": {
                    "from_page": old_page,
                    "to_page": new_page,
                    "navigation_method": "sidebar"
                }
            })
        
        # Google Analytics tracking
        log_to_ga("page_change", self.uid, {
            "previous_page": old_page,
            "new_page": new_page,
            "navigation_method": "sidebar"
        })
        
        # Reload page
        st.rerun()
    
    def _render_ranking_sidebar_content(self):
        """Render ranking-specific sidebar content."""
        st.markdown("**週間ランキング**で他の学習者と競い合いましょう！")
        
        st.divider()
        st.markdown("#### 🎭 ランキング表示設定")
        
        # Get user profile
        user_profile = st.session_state.get("user_profile", {})
        
        if user_profile:
            current_nickname = user_profile.get("nickname", f"ユーザー{user_profile.get('uid', '')[:8]}")
            
            # Nickname input
            new_nickname = st.text_input(
                "ランキング表示名",
                value=current_nickname,
                help="ランキングで表示される名前を変更できます",
                key="ranking_nickname_input"
            )
            
            # Update button
            if st.button("💾 表示名を更新", type="secondary"):
                if new_nickname and new_nickname != current_nickname:
                    try:
                        # Update Firestore
                        from firestore_db import get_firestore_manager
                        db = get_firestore_manager().db
                        db.collection("users").document(user_profile.get("uid")).update({
                            "nickname": new_nickname
                        })
                        
                        # Update session state
                        st.session_state["user_profile"]["nickname"] = new_nickname
                        
                        # Clear ranking cache
                        if hasattr(st.session_state, '_cache'):
                            st.session_state._cache.clear()
                        
                        st.success(f"✅ 表示名を「{new_nickname}」に更新しました！")
                        st.info("📌 全体ランキングへの反映は毎朝3時の定期更新時に行われます")
                        
                        # Track nickname change
                        log_to_ga("profile_update", self.uid, {"field": "nickname"})
                        
                        st.rerun()
                    except Exception as e:
                        st.error(f"エラーが発生しました: {str(e)}")
    
    def render_main_content(self):
        """
        Render the main content area based on selected page.
        
        This method imports and renders the appropriate page module.
        """
        current_page = st.session_state.get("page", "練習")
        
        if current_page == "ランキング":
            from modules.updated_ranking_page import render_updated_ranking_page
            render_updated_ranking_page()
        
        elif current_page == "検索・進捗":
            from modules.search_page import render_search_page
            render_search_page()
        
        elif current_page == "学習メモ":
            from modules.notes_page import render_notes_page
            render_notes_page()
        
        else:  # Default to 練習ページ
            from modules.practice_page import render_practice_page
            from auth import AuthManager
            auth_manager = AuthManager()
            render_practice_page(auth_manager)
    
    @staticmethod
    def get_current_page() -> str:
        """
        Get the currently selected page.
        
        Returns:
            str: Current page name
        """
        return st.session_state.get("page", "練習")
    
    @staticmethod
    def set_page(page_name: str):
        """
        Set the current page programmatically.
        
        Args:
            page_name: Name of the page to navigate to
        """
        if page_name in NavigationManager.PAGES:
            st.session_state["page"] = page_name
            st.session_state["current_page"] = page_name
