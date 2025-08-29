"""
Firebase Analytics統合とデータ収集機能

学習動向の詳細な分析を行うための機能群
"""

from typing import Dict, Any, List, Optional
import datetime
from firestore_db import get_firestore_manager
import streamlit as st


class FirebaseAnalytics:
    """Firebase Analytics統合クラス"""
    
    @staticmethod
    def log_study_session_start(uid: str, session_type: str, metadata: Dict[str, Any] = None):
        """学習セッション開始をログ"""
        if metadata is None:
            metadata = {}
            
        try:
            db_manager = get_firestore_manager()
            analytics_data = {
                "event_type": "study_session_start",
                "uid": uid,
                "session_type": session_type,
                "timestamp": datetime.datetime.now(),
                "metadata": {
                    "target": metadata.get("target", "unknown"),
                    "question_count": metadata.get("question_count", 0),
                    "user_agent": st.context.headers.get("User-Agent", "unknown") if hasattr(st.context, 'headers') else "unknown",
                    **metadata
                }
            }
            
            # analytics_eventsコレクションに保存
            db_manager.db.collection("analytics_events").add(analytics_data)
            
            # daily_analytics_summaryコレクションにも集計データを保存
            today = datetime.date.today().isoformat()
            daily_doc_ref = db_manager.db.collection("daily_analytics_summary").document(f"{uid}_{today}")
            
            daily_doc_ref.set({
                "uid": uid,
                "date": today,
                "session_starts": 1,
                "last_activity": datetime.datetime.now()
            }, merge=True)
            
        except Exception as e:
            print(f"Analytics logging error: {e}")
    
    @staticmethod
    def log_question_answered(uid: str, question_id: str, is_correct: bool, 
                            quality: int, metadata: Dict[str, Any] = None):
        """問題回答をログ"""
        if metadata is None:
            metadata = {}
            
        try:
            db_manager = get_firestore_manager()
            analytics_data = {
                "event_type": "question_answered",
                "uid": uid,
                "question_id": question_id,
                "is_correct": is_correct,
                "quality": quality,
                "timestamp": datetime.datetime.now(),
                "metadata": {
                    "session_type": metadata.get("session_type", "unknown"),
                    "response_time_seconds": metadata.get("response_time", 0),
                    "difficulty_level": metadata.get("difficulty_level", "unknown"),
                    **metadata
                }
            }
            
            # analytics_eventsコレクションに保存
            db_manager.db.collection("analytics_events").add(analytics_data)
            
            # 日次集計の更新
            today = datetime.date.today().isoformat()
            daily_doc_ref = db_manager.db.collection("daily_analytics_summary").document(f"{uid}_{today}")
            
            # 増分データ
            increment_data = {
                "total_questions": 1,
                "correct_answers": 1 if is_correct else 0,
                "last_activity": datetime.datetime.now()
            }
            
            # Firestoreの増分演算を使用
            from google.cloud.firestore import Increment
            for key, value in increment_data.items():
                if key != "last_activity":
                    increment_data[key] = Increment(value)
            
            daily_doc_ref.set(increment_data, merge=True)
            
        except Exception as e:
            print(f"Question analytics logging error: {e}")
    
    @staticmethod
    def log_session_completion(uid: str, session_summary: Dict[str, Any]):
        """学習セッション完了をログ"""
        try:
            db_manager = get_firestore_manager()
            analytics_data = {
                "event_type": "study_session_completion",
                "uid": uid,
                "timestamp": datetime.datetime.now(),
                "session_summary": {
                    "duration_minutes": session_summary.get("duration_minutes", 0),
                    "total_questions": session_summary.get("total_questions", 0),
                    "correct_answers": session_summary.get("correct_answers", 0),
                    "accuracy": session_summary.get("accuracy", 0.0),
                    "session_type": session_summary.get("session_type", "unknown"),
                    **session_summary
                }
            }
            
            # analytics_eventsコレクションに保存
            db_manager.db.collection("analytics_events").add(analytics_data)
            
            # 週次集計の更新
            week_start = datetime.date.today() - datetime.timedelta(days=datetime.date.today().weekday())
            week_doc_ref = db_manager.db.collection("weekly_analytics_summary").document(f"{uid}_{week_start.isoformat()}")
            
            from google.cloud.firestore import Increment
            week_doc_ref.set({
                "uid": uid,
                "week_start": week_start.isoformat(),
                "sessions_completed": Increment(1),
                "total_study_minutes": Increment(session_summary.get("duration_minutes", 0)),
                "last_activity": datetime.datetime.now()
            }, merge=True)
            
        except Exception as e:
            print(f"Session completion analytics logging error: {e}")
    
    @staticmethod
    def log_user_engagement(uid: str, event_type: str, metadata: Dict[str, Any] = None):
        """ユーザーエンゲージメントをログ"""
        if metadata is None:
            metadata = {}
            
        try:
            db_manager = get_firestore_manager()
            analytics_data = {
                "event_type": event_type,
                "uid": uid,
                "timestamp": datetime.datetime.now(datetime.timezone.utc),
                "metadata": {
                    "user_agent": metadata.get("user_agent", "unknown"),
                    "session_id": metadata.get("session_id", "unknown"),
                    "page": metadata.get("page", "unknown"),
                    **metadata
                }
            }
            
            # analytics_eventsコレクションに保存
            db_manager.db.collection("analytics_events").add(analytics_data)
            
            # 日次エンゲージメント集計
            today = datetime.date.today().isoformat()
            daily_doc_ref = db_manager.db.collection("daily_engagement_summary").document(f"{uid}_{today}")
            
            from google.cloud.firestore import Increment
            daily_doc_ref.set({
                "uid": uid,
                "date": today,
                f"{event_type}_count": Increment(1),
                "last_activity": datetime.datetime.now(datetime.timezone.utc)
            }, merge=True)
            
        except Exception as e:
            print(f"User engagement logging error: {e}")
    
    @staticmethod
    def log_page_view(uid: str, page_name: str, metadata: Dict[str, Any] = None):
        """ページビューをログ"""
        if metadata is None:
            metadata = {}
            
        metadata.update({
            "page": page_name,
            "view_type": "page_view"
        })
        
        FirebaseAnalytics.log_user_engagement(uid, "page_view", metadata)
    
    @staticmethod
    def get_user_analytics_summary(uid: str, days: int = 30) -> Dict[str, Any]:
        """ユーザーの分析サマリーを取得"""
        try:
            db_manager = get_firestore_manager()
            
            # 過去N日間のデータを取得
            start_date = datetime.date.today() - datetime.timedelta(days=days)
            
            # 日次サマリーから集計
            daily_docs = db_manager.db.collection("daily_analytics_summary")\
                .where("uid", "==", uid)\
                .where("date", ">=", start_date.isoformat())\
                .get()
            
            total_questions = 0
            total_correct = 0
            session_days = 0
            
            for doc in daily_docs:
                data = doc.to_dict()
                total_questions += data.get("total_questions", 0)
                total_correct += data.get("correct_answers", 0)
                if data.get("total_questions", 0) > 0:
                    session_days += 1
            
            accuracy = (total_correct / total_questions * 100) if total_questions > 0 else 0
            
            return {
                "period_days": days,
                "total_questions": total_questions,
                "total_correct": total_correct,
                "accuracy_percentage": round(accuracy, 1),
                "active_days": session_days,
                "avg_questions_per_day": round(total_questions / max(session_days, 1), 1)
            }
            
        except Exception as e:
            print(f"Analytics summary error: {e}")
            return {}


class PerformanceAnalytics:
    """パフォーマンス分析用クラス"""
    
    @staticmethod
    def analyze_weak_areas(uid: str, days: int = 30) -> List[Dict[str, Any]]:
        """弱点分析"""
        try:
            db_manager = get_firestore_manager()
            
            # 期間内の問題回答データを取得
            start_date = datetime.datetime.now() - datetime.timedelta(days=days)
            
            events = db_manager.db.collection("analytics_events")\
                .where("uid", "==", uid)\
                .where("event_type", "==", "question_answered")\
                .where("timestamp", ">=", start_date)\
                .get()
            
            # 科目別の成績を集計
            subject_stats = {}
            
            for event in events:
                data = event.to_dict()
                question_id = data.get("question_id")
                is_correct = data.get("is_correct", False)
                
                # 問題IDから科目を推定（この部分は実装依存）
                subject = PerformanceAnalytics._get_subject_from_question_id(question_id)
                
                if subject not in subject_stats:
                    subject_stats[subject] = {"total": 0, "correct": 0}
                
                subject_stats[subject]["total"] += 1
                if is_correct:
                    subject_stats[subject]["correct"] += 1
            
            # 弱点科目を抽出
            weak_areas = []
            for subject, stats in subject_stats.items():
                if stats["total"] >= 5:  # 最低5問は解いている
                    accuracy = stats["correct"] / stats["total"]
                    if accuracy < 0.6:  # 正答率60%未満
                        weak_areas.append({
                            "subject": subject,
                            "accuracy": round(accuracy * 100, 1),
                            "total_questions": stats["total"],
                            "correct_answers": stats["correct"]
                        })
            
            # 正答率の低い順にソート
            weak_areas.sort(key=lambda x: x["accuracy"])
            
            return weak_areas[:10]  # 上位10個の弱点を返す
            
        except Exception as e:
            print(f"Weak area analysis error: {e}")
            return []
    
    @staticmethod
    def _get_subject_from_question_id(question_id: str) -> str:
        """問題IDから科目を推定（実装は問題データの構造による）"""
        # 実際の実装では、問題データベースから科目情報を取得
        # ここでは簡易的な実装
        try:
            from data import load_data
            all_data = load_data()
            for q in all_data["questions"]:
                if q["number"] == question_id:
                    return q.get("subject", "未分類")
            return "未分類"
        except:
            return "未分類"


class CostOptimization:
    """コスト最適化のための機能"""
    
    @staticmethod
    def batch_analytics_write(analytics_batch: List[Dict[str, Any]]):
        """分析データのバッチ書き込み"""
        try:
            db_manager = get_firestore_manager()
            
            # バッチ処理で効率的に書き込み
            batch = db_manager.db.batch()
            
            for analytics_data in analytics_batch:
                doc_ref = db_manager.db.collection("analytics_events").document()
                batch.set(doc_ref, analytics_data)
            
            batch.commit()
            
        except Exception as e:
            print(f"Batch analytics write error: {e}")
    
    @staticmethod
    def cleanup_old_analytics(days_to_keep: int = 90):
        """古い分析データのクリーンアップ"""
        try:
            db_manager = get_firestore_manager()
            
            cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days_to_keep)
            
            # 古いイベントを削除
            old_events = db_manager.db.collection("analytics_events")\
                .where("timestamp", "<", cutoff_date)\
                .limit(500)  # バッチサイズ制限
            
            deleted_count = 0
            for doc in old_events.stream():
                doc.reference.delete()
                deleted_count += 1
            
            print(f"Cleaned up {deleted_count} old analytics events")
            
        except Exception as e:
            print(f"Analytics cleanup error: {e}")
