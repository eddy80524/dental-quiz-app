"""
Tracking Service Module

Handles all analytics tracking logic extracted from app.py.
This module provides a clean interface for tracking user activities and events.
"""

import streamlit as st
import time
from utils import log_to_ga, AnalyticsUtils, get_japan_now


class TrackingService:
    """
    Service class for handling analytics tracking and user activity monitoring.
    
    This class manages:
    - User session tracking
    - Page navigation tracking
    - Login event tracking
    - Study activity tracking
    - Feature interaction tracking
    """
    
    def __init__(self, uid: str = None, local_debug_mode: bool = False):
        """
        Initialize the tracking service.
        
        Args:
            uid: User ID for tracking
            local_debug_mode: If True, skip all tracking
        """
        self.uid = uid or st.session_state.get("uid")
        self.local_debug_mode = local_debug_mode
    
    def initialize_tracking(self):
        """Initialize tracking session variables."""
        if 'tracking_initialized' not in st.session_state:
            st.session_state['tracking_initialized'] = True
            st.session_state['session_start_time'] = time.time()
            st.session_state['page_interactions'] = 0
    
    def track_page_navigation(self, page_name: str):
        """
        Track page navigation event.
        
        Args:
            page_name: Name of the page being navigated to
        """
        if self.local_debug_mode:
            return
        
        # Google Analytics page view
        AnalyticsUtils.track_page_view(page_name)
        
        # Update session state
        st.session_state['current_page'] = page_name
        st.session_state['page_interactions'] = st.session_state.get('page_interactions', 0) + 1
    
    def track_user_login_success(self, user_info: dict):
        """
        Track successful user login.
        
        Args:
            user_info: Dictionary containing user information
                - uid: User ID
                - email: User email
                -has_gakushi_permission: Permission flag
        """
        if self.local_debug_mode:
            return
        
        user_properties = {
            'user_type': 'registered' if user_info.get('uid') else 'anonymous',
            'login_timestamp': get_japan_now().isoformat(),
            'has_gakushi_permission': user_info.get('has_gakushi_permission', False)
        }
        
        # Google Analytics tracking
        uid = user_info.get('uid')
        if uid:
            AnalyticsUtils.track_user_login(uid, 'manual_login')
            AnalyticsUtils.track_page_view('main_app_manual_login')
    
    def track_user_activity(self):
        """
        Track general user activity.
        
        Tracks session start (once) and periodic activity (every 5 minutes).
        """
        if self.local_debug_mode:
            return
        
        try:
            if not self.uid:
                return
            
            # Track session start (once)
            if not st.session_state.get("session_tracked"):
                log_to_ga("session_start", self.uid, {
                    "session_type": "web_app",
                    "timestamp": get_japan_now().isoformat(),
                    "user_agent": st.context.headers.get("User-Agent", "unknown") if hasattr(st.context, 'headers') else "unknown"
                })
                
                AnalyticsUtils.track_event('session_start', {
                    'session_type': 'web_app',
                    'user_id': self.uid
                })
                st.session_state["session_tracked"] = True
            
            # Track active user (every 5 minutes)
            last_activity = st.session_state.get("last_activity_logged", 0)
            current_time = time.time()
            
            if current_time - last_activity > 300:  # 5 minutes
                log_to_ga("user_active", self.uid, {
                    "active_duration_seconds": current_time - last_activity,
                    "current_page": st.session_state.get("current_page", "unknown")
                })
                
                AnalyticsUtils.track_app_engagement()
                st.session_state["last_activity_logged"] = current_time
                
        except Exception:
            pass
    
    def track_study_activity(self, activity_type: str, details: dict = None):
        """
        Track study-related activities.
        
        Args:
            activity_type: Type of study activity (e.g., 'question_answered', 'session_completed')
            details: Additional details about the activity
        """
        if self.local_debug_mode:
            return
        
        if not self.uid:
            return
        
        event_data = {
            "activity_type": activity_type,
            "timestamp": get_japan_now().isoformat(),
            **(details or {})
        }
        
        log_to_ga("study_activity", self.uid, event_data)
        AnalyticsUtils.track_event(f"study_{activity_type}", event_data)
    
    def track_feature_interaction(self, feature: str, action: str, context: dict = None):
        """
        Track feature interaction events.
        
        Args:
            feature: Feature name (e.g., 'page_navigation', 'filter')
            action: Action performed (e.g., 'click', 'change')
            context: Additional context about the interaction
        """
        if self.local_debug_mode:
            return
        
        if not self.uid:
            return
        
        event_data = {
            "feature": feature,
            "action": action,
            "timestamp": get_japan_now().isoformat(),
            **(context or {})
        }
        
        log_to_ga("feature_interaction", self.uid, event_data)
        AnalyticsUtils.track_event(f"feature_{feature}_{action}", event_data)
    
    @staticmethod
    def track_event(event_name: str, event_data: dict = None):
        """
        Generic event tracking method.
        
        Args:
            event_name: Name of the event
            event_data: Event data dictionary
        """
        uid = st.session_state.get("uid")
        if uid:
            log_to_ga(event_name, uid, event_data or {})
            AnalyticsUtils.track_event(event_name, event_data or {})
