"""
App Initializer Service Module

Handles all application initialization logic extracted from app.py.
This module provides a clean interface for bootstrapping the application state.
"""

import streamlit as st
import time
from typing import Dict, List
from firestore_db import get_firestore_manager, get_user_profile_for_ranking, save_user_profile
from auth import get_user_permission


class AppInitializer:
    """
    Service class for handling application initialization.
    
    This class manages:
    - Session state initialization
    - User data loading from Firestore
    - User profile setup
    - Subject list initialization
    """
    
    # Default level filter
    DEFAULT_LEVEL_FILTER = [
        "未学習", "レベル0", "レベル1", "レベル2", 
        "レベル3", "レベル4", "レベル5", "習得済み"
    ]
    
    def __init__(self, uid: str = None):
        """
        Initialize the app initializer.
        
        Args:
            uid: Optional user ID. If not provided, will use session state
        """
        self.uid = uid or st.session_state.get("uid")
        self.firestore_manager = get_firestore_manager() if self.uid else None
    
    def initialize_session_state(self):
        """Initialize all session state variables with default values."""
        default_values = {
            "user_logged_in": None,
            "uid": None,
            "email": None,
            "name": None,
            "page": "練習",  # Default to practice page
            "cards": {},
            "analysis_target": "国試",
            "level_filter": self.DEFAULT_LEVEL_FILTER,
            "new_cards_per_day": 10,
            "result_log": {},
            "auto_login_attempted": False,
            "session_start_time": time.time(),
            "page_interactions": 0,
            "study_sessions": []
        }
        
        for key, value in default_values.items():
            if key not in st.session_state:
                st.session_state[key] = value
    
    def initialize_user_profile(self):
        """Initialize user profile from Firestore or create default."""
        try:
            if not self.uid:
                st.session_state["user_profile"] = {}
                return
            
            # Get profile from database
            profile = get_user_profile_for_ranking(self.uid)
            
            if profile:
                st.session_state["user_profile"] = {
                    "uid": self.uid,
                    "nickname": profile.get("nickname", f"ユーザー{self.uid[:8]}"),
                    "show_on_leaderboard": profile.get("show_on_leaderboard", True),
                    "email": st.session_state.get("email", "")
                }
            else:
                # Create default profile
                default_nickname = f"ユーザー{self.uid[:8]}"
                st.session_state["user_profile"] = {
                    "uid": self.uid,
                    "nickname": default_nickname,
                    "show_on_leaderboard": True,
                    "email": st.session_state.get("email", "")
                }
                # Save to database
                save_user_profile(self.uid, default_nickname, True)
                
        except Exception as e:
            print(f"ユーザープロフィール初期化エラー: {e}")
            st.session_state["user_profile"] = {}
    
    def load_user_data(self):
        """Load user's study data (cards) from Firestore."""
        if not self.uid:
            return
        
        # Skip if already loaded
        if st.session_state.get("cards") and len(st.session_state.get("cards", {})) > 0:
            return
        
        try:
            if not self.firestore_manager:
                st.session_state["cards"] = {}
                return
            
            # Get cached data from Firestore
            cards = self.firestore_manager.get_user_cards(self.uid)
            st.session_state["cards"] = cards
            
        except Exception as e:
            print(f"[ERROR] load_user_data: {e}")
            st.session_state["cards"] = {}
    
    def initialize_available_subjects(self, analysis_target: str = None):
        """
        Initialize available subjects list based on analysis target.
        
        Args:
            analysis_target: "国試" or "学士試験". If None, uses session state.
        """
        if analysis_target is None:
            analysis_target = st.session_state.get("analysis_target", "国試")
        
        has_gakushi_permission = get_user_permission() if self.uid else False
        
        # Check if already initialized for this configuration
        cache_key = f"{self.uid}_{has_gakushi_permission}_{analysis_target}"
        if (st.session_state.get('available_subjects') and 
            st.session_state.get('subjects_cache_key') == cache_key):
            return
        
        try:
            # Get subjects for target
            available_subjects = self._get_subjects_for_target(analysis_target)
            st.session_state.available_subjects = available_subjects
            st.session_state.subjects_cache_key = cache_key
            
            # Set default subject filter
            if 'subject_filter' not in st.session_state:
                st.session_state.subject_filter = available_subjects
                
        except Exception:
            # Fallback
            st.session_state.available_subjects = ["一般"]
            st.session_state.subject_filter = ["一般"]
            st.session_state.subjects_cache_key = cache_key
    
    def _get_subjects_for_target(self, analysis_target: str) -> List[str]:
        """
        Get list of subjects for a specific analysis target.
        
        Args:
            analysis_target: "国試" or "学士試験"
            
        Returns:
            List of subject names
        """
        from utils import ALL_QUESTIONS
        
        # Filter questions by target
        target_questions = []
        for q in ALL_QUESTIONS:
            q_number = q.get("question_number", "")
            
            if analysis_target == "学士試験":
                # 学士試験: 問題番号が数字4桁で始まる
                if q_number and len(q_number) >= 4 and q_number[:4].isdigit():
                    target_questions.append(q)
            else:  # 国試
                # 国試: それ以外
                if not (q_number and len(q_number) >= 4 and q_number[:4].isdigit()):
                    target_questions.append(q)
        
        # Extract unique subjects
        subjects = set()
        for q in target_questions:
            subject = q.get("subject")
            if subject:
                subjects.add(subject)
        
        # Sort and return
        return sorted(list(subjects))
    
    def initialize_all(self):
        """
        Initialize all components in the correct order.
        
        This is a convenience method for complete initialization.
        """
        self.initialize_session_state()
        
        if self.uid:
            self.initialize_user_profile()
            # Note: load_user_data is heavy and should be called lazily
            # self.load_user_data()  # Commented out for lazy loading
            self.initialize_available_subjects()
    
    @staticmethod
    def ensure_user_data_loaded():
        """
        Ensure user data is loaded (lazy loading helper).
        
        This should be called on-demand when cards data is actually needed.
        """
        if not st.session_state.get("cards"):
            uid = st.session_state.get("uid")
            if uid:
                initializer = AppInitializer(uid)
                with st.spinner("学習データを読み込んでいます..."):
                    initializer.load_user_data()
    
    @staticmethod
    def ensure_subjects_initialized():
        """
        Ensure subjects are initialized (lazy loading helper).
        
        This should be called on-demand when subject list is needed.
        """
        if not st.session_state.get('available_subjects'):
            uid = st.session_state.get("uid")
            if uid:
                initializer = AppInitializer(uid)
                initializer.initialize_available_subjects()
