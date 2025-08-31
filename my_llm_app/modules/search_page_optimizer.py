"""
検索・進捗ページのパフォーマンス最適化モジュール
練習ページと同じ高速化手法を適用
"""

import streamlit as st
import time
import datetime
from typing import Dict, Any, List, Optional
from functools import lru_cache
import hashlib
import json

class SearchPageOptimizer:
    """検索・進捗ページの最適化クラス"""
    
    @staticmethod
    def should_skip_heavy_computation() -> bool:
        """重い計算処理をスキップするかどうかを判定（練習ページと同じロジック）"""
        # 最近のページ遷移やアクションをチェック
        last_action_time = st.session_state.get("last_search_action_time", 0)
        current_time = time.time()
        action_recently = (current_time - last_action_time) < 2.0  # 2秒以内
        
        # 初回ロード時もスキップ
        is_initial_load = not st.session_state.get("search_stats_calculated", False)
        
        if is_initial_load:
            print(f"[DEBUG] 検索ページ初回ロード - 重い計算をスキップ")
        
        if action_recently:
            print(f"[DEBUG] 最近のアクション後2秒以内 - 重い計算をスキップ")
        
        return action_recently or is_initial_load
    
    @staticmethod
    def mark_action_time():
        """アクション時刻を記録（統計計算スキップのため）"""
        st.session_state["last_search_action_time"] = time.time()
    
    @staticmethod
    def mark_stats_calculated():
        """統計計算完了をマーク"""
        st.session_state["search_stats_calculated"] = True
    
    @staticmethod
    @lru_cache(maxsize=128)
    def get_cached_progress_metrics(uid: str, cards_hash: str, analysis_target: str) -> str:
        """進捗メトリクスをキャッシュ（練習ページ方式）"""
        # ハッシュベースのキャッシュキー
        cache_key = f"progress_metrics_{uid}_{analysis_target}_{cards_hash}"
        return cache_key
    
    @staticmethod
    def create_cards_hash(cards: Dict) -> str:
        """カードデータのハッシュ値生成"""
        if not cards:
            return "empty"
        
        # カードデータの簡易ハッシュ生成
        cards_str = json.dumps(
            {k: len(v.get('history', [])) for k, v in cards.items()},
            sort_keys=True
        )
        return hashlib.md5(cards_str.encode()).hexdigest()[:8]
    
    @staticmethod
    def get_session_cache(key: str, default=None):
        """セッション状態からキャッシュデータを取得"""
        return st.session_state.get(f"search_cache_{key}", default)
    
    @staticmethod
    def set_session_cache(key: str, value):
        """セッション状態にキャッシュデータを保存"""
        st.session_state[f"search_cache_{key}"] = value
    
    @staticmethod
    def clear_session_cache():
        """セッションキャッシュをクリア"""
        keys_to_remove = [k for k in st.session_state.keys() if k.startswith("search_cache_")]
        for key in keys_to_remove:
            del st.session_state[key]


class LazyDataLoader:
    """遅延データロードクラス（練習ページ方式）"""
    
    @staticmethod
    def load_heavy_analytics_data(uid: str, cards: Dict, force_reload: bool = False) -> Dict:
        """重いアナリティクスデータを遅延ロード"""
        if not force_reload and SearchPageOptimizer.should_skip_heavy_computation():
            # 軽量な代替データを返す
            return {
                "status": "skipped",
                "message": "統計計算をスキップしました（パフォーマンス最適化）",
                "basic_stats": {
                    "total_cards": len(cards),
                    "studied_cards": len([c for c in cards.values() if c.get('history', [])]),
                    "timestamp": datetime.datetime.now().isoformat()
                }
            }
        
        # 実際の重い計算を実行
        SearchPageOptimizer.mark_stats_calculated()
        return LazyDataLoader._compute_full_analytics(uid, cards)
    
    @staticmethod
    def _compute_full_analytics(uid: str, cards: Dict) -> Dict:
        """実際の重いアナリティクス計算"""
        try:
            # UserDataExtractorを使用した詳細分析
            from user_data_extractor import UserDataExtractor
            
            extractor = UserDataExtractor(uid)
            detailed_stats = extractor.get_user_comprehensive_stats(uid)
            
            return {
                "status": "computed",
                "detailed_stats": detailed_stats,
                "timestamp": datetime.datetime.now().isoformat()
            }
        except Exception as e:
            print(f"[ERROR] アナリティクス計算エラー: {e}")
            return {
                "status": "error",
                "error": str(e),
                "basic_stats": {
                    "total_cards": len(cards),
                    "studied_cards": len([c for c in cards.values() if c.get('history', [])]),
                    "timestamp": datetime.datetime.now().isoformat()
                }
            }


class ResponsiveUI:
    """レスポンシブUI管理クラス（練習ページ方式）"""
    
    @staticmethod
    def render_loading_placeholder(message: str = "データを読み込み中..."):
        """ローディングプレースホルダー表示"""
        with st.spinner(message):
            st.info("🔄 最適化処理中です。初回表示時は少し時間がかかる場合があります。")
    
    @staticmethod
    def render_lightweight_summary(cards: Dict, analysis_target: str):
        """軽量サマリー表示（重い計算なし）"""
        total_cards = len(cards)
        studied_cards = len([c for c in cards.values() if c.get('history', [])])
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric(
                label="📚 学習状況",
                value=f"{studied_cards}枚",
                help=f"総問題数: {total_cards}枚"
            )
        
        with col2:
            progress_rate = (studied_cards / total_cards * 100) if total_cards > 0 else 0
            st.metric(
                label="📈 進捗率",
                value=f"{progress_rate:.1f}%",
                help="学習済み問題の割合"
            )
        
        with col3:
            st.metric(
                label="🎯 対象",
                value=analysis_target,
                help="現在の分析対象"
            )
    
    @staticmethod
    def render_performance_info():
        """パフォーマンス情報表示"""
        if st.session_state.get("search_stats_calculated"):
            st.success("✅ 詳細統計が利用可能です")
        else:
            st.info("⚡ 高速表示モード（詳細統計は必要時に計算されます）")


class SmartCache:
    """スマートキャッシュ管理（練習ページ方式）"""
    
    @staticmethod
    def get_or_compute(cache_key: str, compute_func, ttl_seconds: int = 3600):
        """キャッシュから取得または計算実行"""
        # キャッシュの存在確認
        cache_data = SearchPageOptimizer.get_session_cache(cache_key)
        
        if cache_data:
            # TTLチェック
            cached_time = cache_data.get("timestamp", 0)
            if time.time() - cached_time < ttl_seconds:
                print(f"[DEBUG] キャッシュヒット: {cache_key}")
                return cache_data.get("data")
        
        # キャッシュミス - 新規計算
        print(f"[DEBUG] キャッシュミス - 新規計算: {cache_key}")
        result = compute_func()
        
        # キャッシュに保存
        SearchPageOptimizer.set_session_cache(cache_key, {
            "data": result,
            "timestamp": time.time()
        })
        
        return result
    
    @staticmethod
    def invalidate_cache(pattern: str = None):
        """キャッシュ無効化"""
        if pattern:
            keys_to_remove = [
                k for k in st.session_state.keys() 
                if k.startswith("search_cache_") and pattern in k
            ]
        else:
            keys_to_remove = [k for k in st.session_state.keys() if k.startswith("search_cache_")]
        
        for key in keys_to_remove:
            del st.session_state[key]
        
        print(f"[DEBUG] キャッシュクリア: {len(keys_to_remove)}件")
