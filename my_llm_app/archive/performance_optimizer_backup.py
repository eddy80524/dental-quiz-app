"""
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
        """科目データをキャッシュして取得（パフォーマンス最適化版）"""
        from subject_mapping import get_all_standardized_subjects
        try:
            # 基本科目を取得
            all_subjects = get_all_standardized_subjects()
            
            # 権限に基づくフィルタリング
            if analysis_target == "学士試験問題" and not has_gakushi_permission:
                # 学士試験権限がない場合は国試科目のみ
                return ["一般", "必修"]
            
            return all_subjects or ["一般"]
            
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
        """ユーザー統計をキャッシュして取得（重複処理削減版）"""
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
    def optimize_page_transition(target_page: str):
        """ページ遷移の最適化"""
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
"""

import streamlit as st
import time
from functools import wraps
from typing import Any, Callable, Dict, List, Optional


class PerformanceOptimizer:
    """アプリケーションのパフォーマンス最適化クラス"""
    
    @staticmethod
    @st.cache_data(ttl=300, show_spinner=False)  # 5分間キャッシュ
    def get_cached_subjects(uid: str, has_gakushi_permission: bool, analysis_target: str) -> List[str]:
        """科目リストをキャッシュ化して取得"""
        from utils import ALL_QUESTIONS
        
        subjects_set = set()
        for q in ALL_QUESTIONS:
            q_num = q.get("number", "")
            
            # 権限チェック
            if q_num.startswith("G") and not has_gakushi_permission:
                continue
            
            # 分析対象フィルタ
            if analysis_target == "学士試験問題":
                if not q_num.startswith("G"):
                    continue
            elif analysis_target == "国試問題":
                if q_num.startswith("G"):
                    continue
            
            # 元の科目名をそのまま使用
            original_subject = q.get("subject", "未分類")
            if original_subject:
                subjects_set.add(original_subject)
        
        return sorted(list(subjects_set))
    
    @staticmethod
    def debounce_page_change(delay: float = 0.1):
        """ページ変更のデバウンス処理"""
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                # 前回の実行時間をチェック
                last_execution_key = f"{func.__name__}_last_execution"
                current_time = time.time()
                last_time = st.session_state.get(last_execution_key, 0)
                
                if current_time - last_time < delay:
                    return  # デバウンス期間中は実行しない
                
                st.session_state[last_execution_key] = current_time
                return func(*args, **kwargs)
            return wrapper
        return decorator
    
    @staticmethod
    def lazy_load_component(component_key: str, loader_func: Callable) -> Any:
        """コンポーネントの遅延読み込み"""
        cache_key = f"lazy_loaded_{component_key}"
        
        if cache_key not in st.session_state:
            with st.spinner(f"{component_key}を読み込み中..."):
                st.session_state[cache_key] = loader_func()
        
        return st.session_state[cache_key]
    
    @staticmethod
    def optimize_session_state():
        """セッション状態の最適化"""
        # 不要なキーを削除（5分以上アクセスされていないキー）
        current_time = time.time()
        keys_to_remove = []
        
        for key in st.session_state.keys():
            if key.endswith("_timestamp"):
                timestamp = st.session_state.get(key, 0)
                if current_time - timestamp > 300:  # 5分
                    base_key = key.replace("_timestamp", "")
                    keys_to_remove.extend([key, base_key])
        
        for key in keys_to_remove:
            if key in st.session_state:
                del st.session_state[key]
    
    @staticmethod
    def track_component_load_time(component_name: str):
        """コンポーネントの読み込み時間を追跡"""
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                start_time = time.time()
                result = func(*args, **kwargs)
                load_time = time.time() - start_time
                
                # デバッグ用の読み込み時間表示
                if load_time > 1.0:  # 1秒以上かかった場合
                    print(f"[PERFORMANCE] {component_name} 読み込み時間: {load_time:.2f}秒")
                
                return result
            return wrapper
        return decorator


class CachedDataManager:
    """データのキャッシュ管理クラス"""
    
    @staticmethod
    @st.cache_data(ttl=600, show_spinner=False)  # 10分間キャッシュ
    def get_user_statistics(uid: str) -> Dict[str, Any]:
        """ユーザー統計情報をキャッシュ化して取得"""
        try:
            # UserDataExtractorが利用可能な場合のみ実行
            from user_data_extractor import UserDataExtractor
            
            extractor = UserDataExtractor(uid)
            stats = extractor.get_comprehensive_statistics()
            
            return {
                "success": True,
                "data": stats,
                "timestamp": time.time()
            }
        except Exception as e:
            print(f"[DEBUG] ユーザー統計取得エラー: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": time.time()
            }
    
    @staticmethod
    @st.cache_data(ttl=300, show_spinner=False)  # 5分間キャッシュ
    def get_filtered_questions(subject_filter: List[str], show_hisshu_only: bool, 
                             level_filter: List[str], analysis_target: str,
                             has_gakushi_permission: bool) -> List[Dict[str, Any]]:
        """フィルタリングされた問題リストをキャッシュ化して取得"""
        from utils import ALL_QUESTIONS, HISSHU_Q_NUMBERS_SET, GAKUSHI_HISSHU_Q_NUMBERS_SET
        
        filtered_questions = []
        
        for q in ALL_QUESTIONS:
            q_num = q.get("number", "")
            
            # 権限チェック
            if q_num.startswith("G") and not has_gakushi_permission:
                continue
            
            # 分析対象フィルタ
            if analysis_target == "学士試験問題":
                if not q_num.startswith("G"):
                    continue
            elif analysis_target == "国試問題":
                if q_num.startswith("G"):
                    continue
            
            # 科目フィルタ
            if subject_filter:
                if q.get("subject", "未分類") not in subject_filter:
                    continue
            
            # 必修フィルタ
            if show_hisshu_only:
                if analysis_target == "学士試験問題":
                    if q_num not in GAKUSHI_HISSHU_Q_NUMBERS_SET:
                        continue
                else:
                    if q_num not in HISSHU_Q_NUMBERS_SET:
                        continue
            
            filtered_questions.append(q)
        
        return filtered_questions


class UIOptimizer:
    """UI描画の最適化クラス"""
    
    @staticmethod
    def render_optimized_sidebar(render_func: Callable) -> None:
        """最適化されたサイドバー描画"""
        # サイドバーの内容をキャッシュ
        sidebar_key = "optimized_sidebar_content"
        
        if sidebar_key not in st.session_state or st.session_state.get("force_sidebar_refresh", False):
            st.session_state[sidebar_key] = True
            st.session_state["force_sidebar_refresh"] = False
            render_func()
        else:
            render_func()
    
    @staticmethod
    def prevent_unnecessary_reruns():
        """不要な再実行を防ぐ"""
        # ページの状態が変更されていない場合は早期リターン
        current_state_hash = hash(str(sorted(st.session_state.items())))
        last_state_hash = st.session_state.get("last_state_hash", None)
        
        if current_state_hash == last_state_hash:
            return True  # 状態に変更なし
        
        st.session_state["last_state_hash"] = current_state_hash
        return False  # 状態に変更あり
    
    @staticmethod
    def optimize_page_transition(new_page: str, old_page: str) -> bool:
        """ページ遷移の最適化"""
        # 同じページへの遷移は無視
        if new_page == old_page:
            return False
        
        # ページ変更のクールダウン（0.5秒）
        last_page_change = st.session_state.get("last_page_change_time", 0)
        current_time = time.time()
        
        if current_time - last_page_change < 0.5:
            return False  # クールダウン中
        
        st.session_state["last_page_change_time"] = current_time
        return True  # ページ変更を許可


def apply_performance_optimizations():
    """パフォーマンス最適化を適用"""
    # セッション状態の最適化
    PerformanceOptimizer.optimize_session_state()
    
    # プリロード用のCSS最適化
    st.markdown("""
    <style>
    /* ページ遷移の高速化 */
    .stApp {
        transition: none !important;
    }
    
    /* スピナーの最適化 */
    .stSpinner {
        transition: opacity 0.1s ease-in-out !important;
    }
    
    /* 不要なアニメーションを無効化 */
    * {
        transition-duration: 0.1s !important;
        animation-duration: 0.1s !important;
    }
    
    /* ボタンクリックの応答性向上 */
    .stButton > button {
        transition: background-color 0.1s ease !important;
    }
    
    /* ラジオボタンの応答性向上 */
    .stRadio > div {
        transition: none !important;
    }
    </style>
    """, unsafe_allow_html=True)
