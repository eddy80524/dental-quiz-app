"""
パフォーマンス最適化モジュール
- キャッシュシステム
- デバウンス機能  
- UI最適化
- セッション状態管理
"""

import streamlit as st
import time
import logging
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timedelta
import functools
import gc

# ログレベルを制御するための設定
LOG_LEVEL = logging.WARNING  # DEBUGログを削減

class PerformanceOptimizer:
    """アプリケーション全体のパフォーマンス最適化クラス"""
    
    _last_debounce_time = {}
    
    @staticmethod
    @st.cache_data(ttl=300, show_spinner=False)  # 5分間キャッシュ
    def get_cached_subjects(uid: str, has_gakushi_permission: bool, analysis_target: str) -> List[str]:
        """科目データをキャッシュして取得（実際のJSONデータから）"""
        try:
            from utils import ALL_QUESTIONS
            
            # 実際のJSONデータから科目を抽出
            kokushi_subjects = set()
            gakushi_subjects = set()
            
            for q in ALL_QUESTIONS:
                subject = q.get('subject', '')
                number = q.get('number', '')
                
                if not subject or subject == '（未分類）':
                    continue
                
                # 国試問題か学士試験問題かを判定
                if number.startswith('G'):
                    gakushi_subjects.add(subject)
                else:
                    kokushi_subjects.add(subject)
            
            # 分析対象に応じて科目を返す
            if analysis_target == "学士試験問題":
                if has_gakushi_permission:
                    return sorted(list(gakushi_subjects)) or ["一般"]
                else:
                    # 学士試験権限がない場合は国試科目のみ
                    return sorted(list(kokushi_subjects)) or ["一般"]
            else:
                # 国試問題の場合
                return sorted(list(kokushi_subjects)) or ["一般"]
            
        except Exception as e:
            if LOG_LEVEL <= logging.WARNING:
                st.error(f"科目取得エラー: {e}")
            return ["一般"]
    
    @staticmethod
    def debounce_action(action_key: str, delay: float = 1.0) -> bool:
        """アクションのデバウンス処理"""
        current_time = time.time()
        last_time = PerformanceOptimizer._last_debounce_time.get(action_key, 0)
        
        if current_time - last_time >= delay:
            PerformanceOptimizer._last_debounce_time[action_key] = current_time
            return True
        return False
    
    @staticmethod
    def optimize_session_state():
        """セッション状態の最適化"""
        # 不要なキーを削除してメモリを節約
        unnecessary_keys = [key for key in st.session_state.keys() 
                          if key.startswith('temp_') or key.startswith('cache_expired_')]
        
        for key in unnecessary_keys[:10]:  # 一度に最大10個まで削除
            del st.session_state[key]
        
        # ガベージコレクション
        if len(unnecessary_keys) > 5:
            gc.collect()


class CachedDataManager:
    """データキャッシュ管理クラス"""
    
    @staticmethod
    @st.cache_data(ttl=600, show_spinner=False)  # 10分間キャッシュ
    def get_user_statistics(uid: str) -> Dict[str, Any]:
        """ユーザー統計をキャッシュして取得"""
        if not uid or uid == "guest":
            return {"error": "Invalid UID"}
            
        try:
            # ログ出力を最小限に抑制
            if LOG_LEVEL <= logging.INFO:
                print(f"[INFO] 統計取得: {uid}")
                
            from user_data_extractor import UserDataExtractor
            extractor = UserDataExtractor()
            
            # 重複チェック: 同じリクエストが短時間に来た場合はスキップ
            cache_key = f"stats_{uid}_{int(time.time() // 300)}"  # 5分単位
            if cache_key in st.session_state:
                return st.session_state[cache_key]
            
            # 統計データを取得
            result = extractor.get_comprehensive_statistics(uid)
            
            # 結果をセッションキャッシュに保存
            st.session_state[cache_key] = result
            
            return result
            
        except Exception as e:
            if LOG_LEVEL <= logging.WARNING:
                print(f"[WARNING] 統計取得エラー: {e}")
            return {"error": str(e)}


class UIOptimizer:
    """UI最適化クラス"""
    
    @staticmethod
    def render_optimized_sidebar(sidebar_func: Callable):
        """サイドバーの最適化描画"""
        # デバウンス処理でサイドバーの再描画を制御
        if PerformanceOptimizer.debounce_action("sidebar_render", 0.5):
            with st.sidebar:
                sidebar_func()
    
    @staticmethod
    def optimize_page_transition(target_page: str, current_page: str = None):
        """ページ遷移の最適化"""
        if current_page is None:
            current_page = st.session_state.get("page", "練習")
        
        # 同じページへの遷移は無視
        if current_page == target_page:
            return False
            
        # デバウンス処理
        if PerformanceOptimizer.debounce_action(f"page_transition_{target_page}", 0.3):
            st.session_state["page"] = target_page
            # 不要なページ固有のセッション状態をクリア
            page_specific_keys = [k for k in st.session_state.keys() 
                                if k.startswith(f'{current_page}_')]
            for key in page_specific_keys:
                del st.session_state[key]
            return True
        return False
    
    @staticmethod
    def add_performance_css():
        """パフォーマンス向上のためのCSS"""
        st.markdown("""
        <style>
        /* GPU加速とスムーズなアニメーション */
        .stApp {
            transform: translateZ(0);
            backface-visibility: hidden;
        }
        
        /* ページ遷移の最適化 */
        .main .block-container {
            transition: opacity 0.2s ease-in-out;
        }
        
        /* 重いコンポーネントの最適化 */
        .stDataFrame {
            contain: layout style paint;
        }
        
        /* メモリ使用量の削減 */
        .stPlotlyChart {
            contain: strict;
        }
        </style>
        """, unsafe_allow_html=True)


def apply_performance_optimizations():
    """アプリケーション全体のパフォーマンス最適化を適用"""
    # CSS最適化を適用
    UIOptimizer.add_performance_css()
    
    # セッション状態の最適化
    PerformanceOptimizer.optimize_session_state()
    
    # デバッグログの抑制
    logging.getLogger().setLevel(LOG_LEVEL)
