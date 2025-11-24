import datetime
import random
import streamlit as st
from typing import List, Dict, Optional, Any
from modules.state.practice_state import PracticeSessionState
from utils import get_japan_now
try:
    from firestore_db import get_firestore_manager
except ImportError:
    def get_firestore_manager():
        return None

class PracticeEngine:
    """練習セッションのロジックを管理するクラス"""
    
    def __init__(self):
        self.firestore_manager = get_firestore_manager()
    
    def get_next_q_group(self) -> List[str]:
        """次の問題グループを取得（日本時間ベース）"""
        now = get_japan_now()
        
        # 利用可能な復習問題を取得
        stq = PracticeSessionState.get_review_queue()
        ready_reviews = []
        for i, item in enumerate(stq):
            ra = item.get("ready_at")
            if isinstance(ra, str):
                try:
                    ra = datetime.datetime.fromisoformat(ra)
                except Exception:
                    ra = now
            if not ra or ra <= now:
                ready_reviews.append((i, item))
        
        # 利用可能な新規問題を取得
        main_queue = PracticeSessionState.get("main_queue", [])
        
        # 復習問題と新規問題のバランス調整
        review_count = len(ready_reviews)
        
        # 復習問題が5個以上溜まっている場合は復習を優先
        if review_count >= 5:
            if ready_reviews:
                i, item = ready_reviews[0]
                stq.pop(i)
                PracticeSessionState.set_review_queue(stq)
                return item.get("group", [])
        
        # 新規問題がある場合は新規問題を優先（復習が溜まっていない場合）
        if main_queue:
            # 3回に1回は復習を混ぜる（復習がある場合）
            if ready_reviews and random.random() < 0.33:
                i, item = ready_reviews[0]
                stq.pop(i)
                PracticeSessionState.set_review_queue(stq)
                return item.get("group", [])
            
            # 新規問題を出題
            next_group = main_queue.pop(0)
            PracticeSessionState.set("main_queue", main_queue)
            return next_group
            
        # 新規問題がない場合は残りの復習問題を出題
        if ready_reviews:
            i, item = ready_reviews[0]
            stq.pop(i)
            PracticeSessionState.set_review_queue(stq)
            return item.get("group", [])
            
        return []
    
    def enqueue_short_review(self, group: List[str], minutes: int):
        """短期復習キューに追加（日本時間ベース）"""
        ready_at = get_japan_now() + datetime.timedelta(minutes=minutes)
        item = {
            "group": group,
            "ready_at": ready_at
        }
        PracticeSessionState.add_to_review_queue(item)
    
    def setup_daily_quiz_from_cloud_function(self) -> bool:
        """Cloud Functionからおまかせクイズをセットアップ"""
        uid = PracticeSessionState.get_uid()
        if not uid:
            st.error("ユーザーIDが見つかりません")
            return False
        
        # getDailyQuiz Cloud Functionを呼び出し
        try:
            from auth import call_cloud_function
            payload = {"uid": uid}
            
            result = call_cloud_function("getDailyQuiz", payload)
            
            if result and result.get("success"):
                # Cloud Functionから返された学習キューをセッションに設定
                cloud_data = result.get("data", {})
                
                PracticeSessionState.set("main_queue", cloud_data.get("main_queue", []))
                PracticeSessionState.set("current_q_group", cloud_data.get("current_q_group", []))
                PracticeSessionState.set("short_term_review_queue", cloud_data.get("short_term_review_queue", []))
                
                queue_info = f"新規: {len(PracticeSessionState.get('main_queue', []))}グループ, " \
                            f"現在: {len(PracticeSessionState.get('current_q_group', []))}問, " \
                            f"復習: {len(PracticeSessionState.get('short_term_review_queue', []))}グループ"
                
                st.success(f"おまかせ学習キューを生成しました\n{queue_info}")
                return True
            else:
                # Cloud Function失敗時はエラーメッセージを表示
                st.error("学習キューの生成に失敗しました。しばらく待ってから再度お試しください。")
                return False
        except ImportError:
            st.error("認証モジュールが見つかりません")
            return False
