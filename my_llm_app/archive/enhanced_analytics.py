#!/usr/bin/env python3
"""
Google Analytics統合強化
包括的なユーザー行動分析システムの実装
"""

import streamlit as st
import streamlit.components.v1 as components
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
import uuid

class EnhancedGoogleAnalytics:
    """強化されたGoogle Analytics統合クラス"""
    
    def __init__(self):
        # Google Analytics設定
        self.ga_measurement_id = self._get_ga_measurement_id()
        self.session_id = self._get_or_create_session_id()
        self.user_id = st.session_state.get('user_id', f'anonymous_{uuid.uuid4().hex[:8]}')
        
    def _get_ga_measurement_id(self) -> str:
        """Google Analytics測定IDを取得"""
        try:
            # Streamlit secretsから取得
            if hasattr(st, 'secrets') and 'google_analytics_id' in st.secrets:
                ga_id = st.secrets.get('google_analytics_id')
                if ga_id and ga_id != 'G-XXXXXXXXXX':
                    return ga_id
            
            # 環境変数から取得
            import os
            ga_id = os.environ.get('GOOGLE_ANALYTICS_ID')
            if ga_id:
                return ga_id
                
            # デフォルト値（実際のIDに置き換える必要がある）
            return 'G-XXXXXXXXXX'
            
        except Exception as e:
            st.warning(f"Google Analytics設定取得エラー: {e}")
            return 'G-XXXXXXXXXX'
    
    def _get_or_create_session_id(self) -> str:
        """セッションIDを取得または作成"""
        if 'ga_session_id' not in st.session_state:
            st.session_state['ga_session_id'] = f'session_{uuid.uuid4().hex[:12]}'
        return st.session_state['ga_session_id']
    
    def initialize_ga(self):
        """Google Analytics初期化"""
        if self.ga_measurement_id == 'G-XXXXXXXXXX':
            st.warning("⚠️ Google Analytics IDが設定されていません。実際の測定IDを設定してください。")
            return False
        
        if not st.session_state.get("enhanced_ga_initialized"):
            self._inject_enhanced_ga_script()
            st.session_state["enhanced_ga_initialized"] = True
            return True
        return False
    
    def _inject_enhanced_ga_script(self):
        """強化されたGoogle Analytics スクリプトを注入"""
        ga_script = f"""
        <!-- Enhanced Google Analytics (gtag.js) -->
        <script async src="https://www.googletagmanager.com/gtag/js?id={self.ga_measurement_id}"></script>
        <script>
          window.dataLayer = window.dataLayer || [];
          function gtag(){{dataLayer.push(arguments);}}
          
          gtag('js', new Date());
          
          // 詳細設定でGoogle Analytics初期化
          gtag('config', '{self.ga_measurement_id}', {{
            cookie_domain: 'auto',
            cookie_flags: 'SameSite=None;Secure',
            send_page_view: false,  // 手動でページビューを制御
            custom_map: {{
              'custom_user_id': 'user_id',
              'custom_session_id': 'session_id'
            }},
            user_id: '{self.user_id}',
            session_id: '{self.session_id}'
          }});
          
          // デバッグ情報
          console.log('Enhanced Google Analytics initialized:', '{self.ga_measurement_id}');
          console.log('User ID:', '{self.user_id}');
          console.log('Session ID:', '{self.session_id}');
          
          // カスタムユーザープロパティ設定
          gtag('set', {{
            'user_id': '{self.user_id}',
            'session_id': '{self.session_id}',
            'app_name': 'dental_exam_app',
            'app_version': '2.0'
          }});
        </script>
        """
        components.html(ga_script, height=0)
    
    def track_page_view(self, page_name: str, page_title: str = None, additional_params: Dict = None):
        """ページビュー追跡"""
        params = {
            'page_title': page_title or page_name,
            'page_location': f'/app/{page_name}',
            'user_id': self.user_id,
            'session_id': self.session_id,
            'send_to': self.ga_measurement_id
        }
        
        if additional_params:
            params.update(additional_params)
        
        self._send_event('page_view', params)
    
    def track_user_login(self, login_method: str = 'firebase', user_properties: Dict = None):
        """ユーザーログイン追跡"""
        params = {
            'method': login_method,
            'user_id': self.user_id,
            'session_id': self.session_id
        }
        
        if user_properties:
            params.update(user_properties)
        
        self._send_event('login', params)
        
        # ユーザープロパティも設定
        if user_properties:
            self._set_user_properties(user_properties)
    
    def track_study_session_start(self, session_type: str, question_count: int = 0, 
                                 difficulty: str = None, subject: str = None):
        """学習セッション開始追跡"""
        params = {
            'session_type': session_type,
            'question_count': question_count,
            'user_id': self.user_id,
            'session_id': self.session_id,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        if difficulty:
            params['difficulty'] = difficulty
        if subject:
            params['subject'] = subject
        
        self._send_event('study_session_start', params)
    
    def track_question_interaction(self, question_id: str, action: str, 
                                  is_correct: Optional[bool] = None, 
                                  response_time: Optional[float] = None,
                                  difficulty: str = None):
        """問題相互作用追跡"""
        params = {
            'question_id': question_id,
            'action': action,  # 'view', 'answer', 'review', 'skip'
            'user_id': self.user_id,
            'session_id': self.session_id,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        if is_correct is not None:
            params['is_correct'] = is_correct
            params['outcome'] = 'correct' if is_correct else 'incorrect'
        
        if response_time is not None:
            params['response_time_seconds'] = round(response_time, 2)
        
        if difficulty:
            params['difficulty'] = difficulty
        
        self._send_event('question_interaction', params)
    
    def track_learning_progress(self, total_questions: int, correct_answers: int,
                               session_duration: float, accuracy: float,
                               improvement_metrics: Dict = None):
        """学習進捗追跡"""
        params = {
            'total_questions': total_questions,
            'correct_answers': correct_answers,
            'session_duration_minutes': round(session_duration / 60, 2),
            'accuracy_percentage': round(accuracy * 100, 1),
            'user_id': self.user_id,
            'session_id': self.session_id,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        if improvement_metrics:
            params.update(improvement_metrics)
        
        self._send_event('learning_progress', params)
    
    def track_feature_usage(self, feature_name: str, action: str, 
                           context: Dict = None):
        """機能使用追跡"""
        params = {
            'feature_name': feature_name,
            'action': action,
            'user_id': self.user_id,
            'session_id': self.session_id,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        if context:
            params.update(context)
        
        self._send_event('feature_usage', params)
    
    def track_user_engagement(self, engagement_type: str, duration: float = None,
                             interaction_count: int = None):
        """ユーザーエンゲージメント追跡"""
        params = {
            'engagement_type': engagement_type,
            'user_id': self.user_id,
            'session_id': self.session_id,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        if duration is not None:
            params['duration_seconds'] = round(duration, 2)
        
        if interaction_count is not None:
            params['interaction_count'] = interaction_count
        
        self._send_event('user_engagement', params)
    
    def track_conversion(self, conversion_type: str, value: float = None,
                        currency: str = 'JPY', items: List[Dict] = None):
        """コンバージョン追跡"""
        params = {
            'conversion_type': conversion_type,
            'user_id': self.user_id,
            'session_id': self.session_id,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        if value is not None:
            params['value'] = value
            params['currency'] = currency
        
        if items:
            params['items'] = items
        
        self._send_event('conversion', params)
    
    def track_error(self, error_type: str, error_message: str, 
                   context: Dict = None):
        """エラー追跡"""
        params = {
            'error_type': error_type,
            'error_message': error_message[:100],  # メッセージを制限
            'user_id': self.user_id,
            'session_id': self.session_id,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        if context:
            params.update(context)
        
        self._send_event('app_error', params)
    
    def _send_event(self, event_name: str, parameters: Dict[str, Any]):
        """Google Analytics イベント送信"""
        if self.ga_measurement_id == 'G-XXXXXXXXXX':
            # デバッグモード（実際のIDが設定されていない場合）
            print(f"[DEBUG GA] Event: {event_name}, Params: {parameters}")
            return
        
        # パラメータをJSONエンコード用に準備
        clean_params = self._clean_parameters(parameters)
        
        ga_js = f"""
        <script>
        if (typeof gtag !== 'undefined') {{
            console.log('Sending GA event:', '{event_name}', {json.dumps(clean_params)});
            gtag('event', '{event_name}', {json.dumps(clean_params)});
        }} else {{
            console.warn('Google Analytics (gtag) not loaded');
        }}
        </script>
        """
        components.html(ga_js, height=0)
    
    def _set_user_properties(self, properties: Dict[str, Any]):
        """ユーザープロパティ設定"""
        if self.ga_measurement_id == 'G-XXXXXXXXXX':
            print(f"[DEBUG GA] User Properties: {properties}")
            return
        
        clean_props = self._clean_parameters(properties)
        
        ga_js = f"""
        <script>
        if (typeof gtag !== 'undefined') {{
            gtag('set', 'user_properties', {json.dumps(clean_props)});
        }}
        </script>
        """
        components.html(ga_js, height=0)
    
    def _clean_parameters(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """パラメータをGoogle Analytics用にクリーン化"""
        clean_params = {}
        
        for key, value in params.items():
            # Google Analytics用にキーを調整
            clean_key = key.replace(' ', '_').lower()
            
            # 値の型を適切に変換
            if isinstance(value, (str, int, float, bool)):
                clean_params[clean_key] = value
            elif value is None:
                clean_params[clean_key] = ''
            else:
                clean_params[clean_key] = str(value)
        
        return clean_params
    
    def get_setup_instructions(self) -> str:
        """セットアップ手順を返す"""
        return """
        🔧 Google Analytics セットアップ手順:
        
        1. Google Analytics 4 プロパティを作成
           https://analytics.google.com/
        
        2. 測定IDを取得 (G-XXXXXXXXXX形式)
        
        3. Streamlit secrets.tomlに設定:
           [secrets]
           google_analytics_id = "G-YOUR-ACTUAL-ID"
        
        4. または環境変数に設定:
           export GOOGLE_ANALYTICS_ID="G-YOUR-ACTUAL-ID"
        
        5. アプリを再起動
        """

# グローバルインスタンス
enhanced_ga = EnhancedGoogleAnalytics()

# 便利関数（後方互換性）
def track_event(event_name: str, parameters: Dict[str, Any] = None):
    """イベント追跡（簡単版）"""
    enhanced_ga._send_event(event_name, parameters or {})

def track_page_view(page_name: str):
    """ページビュー追跡（簡単版）"""
    enhanced_ga.track_page_view(page_name)

if __name__ == "__main__":
    # テスト実行
    print("Enhanced Google Analytics モジュールテスト")
    ga = EnhancedGoogleAnalytics()
    print(f"測定ID: {ga.ga_measurement_id}")
    print(f"ユーザーID: {ga.user_id}")
    print(f"セッションID: {ga.session_id}")
    print("\nセットアップ手順:")
    print(ga.get_setup_instructions())
