import streamlit as st
from typing import Dict, List, Any, Optional
import datetime

class PracticeSessionState:
    """練習セッションの状態管理を行うクラス"""
    
    @staticmethod
    def initialize():
        """セッション状態の初期化"""
        defaults = {
            "current_q_group": [],
            "current_group_id": None,
            "result_log": {},
            "session_history": [],
            "short_term_review_queue": [],
            "daily_stats_cache": {},
        }
        
        for key, value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = value

    @staticmethod
    def get(key: str, default: Any = None) -> Any:
        """状態の取得"""
        return st.session_state.get(key, default)

    @staticmethod
    def set(key: str, value: Any):
        """状態の設定"""
        st.session_state[key] = value

    @staticmethod
    def update_result_log(qid: str, result: Dict):
        """結果ログの更新"""
        if "result_log" not in st.session_state:
            st.session_state["result_log"] = {}
        st.session_state["result_log"][qid] = result

    @staticmethod
    def get_result_log() -> Dict:
        """結果ログの取得"""
        return st.session_state.get("result_log", {})

    @staticmethod
    def clear_current_group():
        """現在の問題グループ情報をクリア"""
        keys_to_clear = [
            "current_q_group", 
            "current_group_id"
        ]
        for key in keys_to_clear:
            if key in st.session_state:
                del st.session_state[key]
                
    @staticmethod
    def add_to_review_queue(item: Dict):
        """短期復習キューに追加"""
        if "short_term_review_queue" not in st.session_state:
            st.session_state["short_term_review_queue"] = []
        st.session_state["short_term_review_queue"].append(item)
        
    @staticmethod
    def get_review_queue() -> List[Dict]:
        """短期復習キューの取得"""
        return st.session_state.get("short_term_review_queue", [])

    @staticmethod
    def set_review_queue(queue: List[Dict]):
        """短期復習キューの設定"""
        st.session_state["short_term_review_queue"] = queue

    @staticmethod
    def get_uid() -> Optional[str]:
        """ユーザーIDの取得"""
        return st.session_state.get("uid")

    @staticmethod
    def get_cards() -> Dict:
        """学習カードデータの取得"""
        return st.session_state.get("cards", {})

    @staticmethod
    def set_cards(cards: Dict):
        """学習カードデータの設定"""
        st.session_state["cards"] = cards

    @staticmethod
    def get_main_queue() -> List[Any]:
        """メインキューの取得"""
        return st.session_state.get("main_queue", [])

    @staticmethod
    def set_main_queue(queue: List[Any]):
        """メインキューの設定"""
        st.session_state["main_queue"] = queue

    @staticmethod
    def get_current_q_group() -> List[str]:
        """現在の問題グループの取得"""
        return st.session_state.get("current_q_group", [])

    @staticmethod
    def set_current_q_group(group: List[str]):
        """現在の問題グループの設定"""
        st.session_state["current_q_group"] = group

    @staticmethod
    def get_session_type() -> str:
        """セッションタイプの取得"""
        return st.session_state.get("session_type", "")

    @staticmethod
    def set_session_type(session_type: str):
        """セッションタイプの設定"""
        st.session_state["session_type"] = session_type

    @staticmethod
    def reset_session():
        """セッションのリセット（主要なキーを削除）"""
        keys_to_reset = [
            "session_choice_made", "session_type", "current_q_group", 
            "main_queue", "short_term_review_queue",
            "session_completed_logged", "session_start_time",
            "is_review_session", "current_question_index",
            "current_group_id"
        ]
        
        for key in keys_to_reset:
            if key in st.session_state:
                del st.session_state[key]
        
        # 問題関連の一時データもクリア
        keys_to_remove = []
        for key in st.session_state.keys():
            if key.startswith(("checked_", "result_", "shuffled_choices_", "user_selection_", "free_input_", "order_input_")):
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            del st.session_state[key]

    @staticmethod
    def get_analysis_target() -> str:
        """分析対象（国試/学士）の取得"""
        return st.session_state.get("analysis_target", "国試")

    @staticmethod
    def get_daily_review_limit() -> int:
        """1日の復習上限の取得"""
        return st.session_state.get("daily_review_limit", 120)

    @staticmethod
    def set_daily_review_limit(limit: int):
        """1日の復習上限の設定"""
        st.session_state["daily_review_limit"] = limit

    @staticmethod
    def get_current_question_index() -> int:
        """現在の問題インデックスの取得"""
        return st.session_state.get("current_question_index", 0)

    @staticmethod
    def set_current_question_index(index: int):
        """現在の問題インデックスの設定"""
        st.session_state["current_question_index"] = index

    @staticmethod
    def get_session_completed_logged() -> bool:
        """セッション完了ログ記録済みフラグの取得"""
        return st.session_state.get("session_completed_logged", False)

    @staticmethod
    def set_session_completed_logged(logged: bool):
        """セッション完了ログ記録済みフラグの設定"""
        st.session_state["session_completed_logged"] = logged

    @staticmethod
    def get_session_start_time() -> float:
        """セッション開始時刻の取得"""
        return st.session_state.get("session_start_time", 0.0)

    @staticmethod
    def set_session_start_time(timestamp: float):
        """セッション開始時刻の設定"""
        st.session_state["session_start_time"] = timestamp

    @staticmethod
    def is_review_session() -> bool:
        """復習セッションかどうかの判定"""
        return st.session_state.get("is_review_session", False)

    @staticmethod
    def set_is_review_session(is_review: bool):
        """復習セッションフラグの設定"""
        st.session_state["is_review_session"] = is_review
