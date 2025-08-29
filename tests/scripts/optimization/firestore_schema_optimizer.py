"""
Firestore Database Schema Redesign for Scalability and Native App Compatibility

新しいデータベース構造設計：
- Native App (SwiftUI) との互換性を考慮
- 拡張性とパフォーマンスを重視
- 不必要なコレクションを削除
- 学士権限管理の維持
"""

from typing import Dict, Any, List, Optional
import datetime
from firestore_db import get_firestore_manager
import streamlit as st


class OptimizedFirestoreSchema:
    """最適化されたFirestoreスキーマ管理"""
    
    # === 核となるコレクション構造 ===
    
    @staticmethod
    def get_core_collections():
        """
        核となるコレクション構造定義
        Native Appとの互換性を重視した最小限の構成
        """
        return {
            # ユーザー管理（認証情報は Firebase Auth に依存）
            "users": {
                "doc_id": "{uid}",
                "structure": {
                    "profile": {
                        "email": "string",
                        "display_name": "string", 
                        "created_at": "timestamp",
                        "last_login": "timestamp",
                        "permissions": {
                            "gakushi_access": "boolean",  # 学士試験アクセス権限
                            "admin": "boolean"
                        },
                        "preferences": {
                            "new_cards_per_day": "number",
                            "study_reminder": "boolean",
                            "analytics_opt_in": "boolean"
                        }
                    },
                    "statistics": {
                        "total_questions_answered": "number",
                        "total_correct_answers": "number", 
                        "study_streak_days": "number",
                        "last_study_date": "date",
                        "mastery_level": "number"  # 0-100
                    }
                }
            },
            
            # 学習カード管理（SM2アルゴリズム）
            "study_cards": {
                "doc_id": "{uid}_{question_id}",
                "structure": {
                    "uid": "string",
                    "question_id": "string",
                    "sm2_data": {
                        "n": "number",           # 復習回数
                        "ef": "number",          # 記憶容易度
                        "interval": "number",    # 復習間隔（日数）
                        "due_date": "timestamp", # 次回復習日
                        "last_studied": "timestamp"
                    },
                    "performance": {
                        "total_attempts": "number",
                        "correct_attempts": "number",
                        "avg_quality": "number",
                        "last_quality": "number"
                    },
                    "metadata": {
                        "created_at": "timestamp",
                        "updated_at": "timestamp",
                        "subject": "string",
                        "difficulty": "string"
                    }
                }
            },
            
            # 学習セッション記録
            "study_sessions": {
                "doc_id": "auto_generated",
                "structure": {
                    "uid": "string",
                    "session_id": "string",
                    "start_time": "timestamp",
                    "end_time": "timestamp",
                    "session_type": "string",  # auto_learning, manual, review
                    "questions": [
                        {
                            "question_id": "string",
                            "answered_at": "timestamp",
                            "user_answer": "string",
                            "correct_answer": "string",
                            "is_correct": "boolean",
                            "quality_rating": "number",
                            "response_time_ms": "number"
                        }
                    ],
                    "summary": {
                        "total_questions": "number",
                        "correct_answers": "number",
                        "accuracy": "number",
                        "avg_response_time": "number",
                        "duration_minutes": "number"
                    }
                }
            },
            
            # 分析データ（集計済み）
            "analytics_summary": {
                "doc_id": "{uid}_{period}_{date}",  # 例: uid_daily_2025-08-25
                "structure": {
                    "uid": "string",
                    "period": "string",  # daily, weekly, monthly
                    "date": "string",    # ISO date
                    "metrics": {
                        "questions_answered": "number",
                        "correct_answers": "number",
                        "accuracy": "number",
                        "study_time_minutes": "number",
                        "sessions_count": "number"
                    },
                    "weak_subjects": ["string"],  # 正答率が低い科目
                    "strong_subjects": ["string"], # 正答率が高い科目
                    "updated_at": "timestamp"
                }
            }
        }
    
    @staticmethod
    def migrate_existing_data(uid: str, dry_run: bool = True):
        """
        既存データを新しいスキーマに移行
        
        Args:
            uid: ユーザーID
            dry_run: True の場合は移行の確認のみ、実際の移行は行わない
        """
        db_manager = get_firestore_manager()
        migration_report = {
            "users_migrated": 0,
            "cards_migrated": 0,
            "sessions_created": 0,
            "analytics_created": 0,
            "errors": []
        }
        
        try:
            if not dry_run:
                st.info("🔄 データ移行を開始しています...")
            
            # 1. ユーザープロフィール移行
            migration_report["users_migrated"] = OptimizedFirestoreSchema._migrate_user_profile(uid, dry_run)
            
            # 2. 学習カード移行
            migration_report["cards_migrated"] = OptimizedFirestoreSchema._migrate_study_cards(uid, dry_run)
            
            # 3. 過去の学習ログから学習セッション作成
            migration_report["sessions_created"] = OptimizedFirestoreSchema._create_study_sessions_from_logs(uid, dry_run)
            
            # 4. 分析サマリー作成
            migration_report["analytics_created"] = OptimizedFirestoreSchema._create_analytics_summary(uid, dry_run)
            
            if not dry_run:
                st.success("✅ データ移行が完了しました")
            
        except Exception as e:
            error_msg = f"Migration error for user {uid}: {str(e)}"
            migration_report["errors"].append(error_msg)
            if not dry_run:
                st.error(f"❌ {error_msg}")
        
        return migration_report
    
    @staticmethod
    def _migrate_user_profile(uid: str, dry_run: bool) -> int:
        """ユーザープロフィールの移行"""
        db_manager = get_firestore_manager()
        
        # 既存プロフィール取得
        old_profile = db_manager.load_user_profile(uid)
        
        # 学士権限チェック
        from firestore_db import check_gakushi_permission
        gakushi_access = check_gakushi_permission(uid)
        
        new_profile = {
            "profile": {
                "email": old_profile.get("email", ""),
                "display_name": old_profile.get("nickname", "匿名ユーザー"),
                "created_at": datetime.datetime.now(),
                "last_login": datetime.datetime.now(),
                "permissions": {
                    "gakushi_access": gakushi_access,
                    "admin": False
                },
                "preferences": {
                    "new_cards_per_day": old_profile.get("settings", {}).get("new_cards_per_day", 10),
                    "study_reminder": True,
                    "analytics_opt_in": True
                }
            },
            "statistics": {
                "total_questions_answered": 0,
                "total_correct_answers": 0,
                "study_streak_days": 0,
                "last_study_date": None,
                "mastery_level": 0
            }
        }
        
        if not dry_run:
            db_manager.db.collection("users").document(uid).set(new_profile)
        
        return 1
    
    @staticmethod
    def _migrate_study_cards(uid: str, dry_run: bool) -> int:
        """学習カードの移行"""
        db_manager = get_firestore_manager()
        migrated_count = 0
        
        try:
            # 既存のuserCardsを取得
            user_cards_ref = db_manager.db.collection("users").document(uid).collection("userCards")
            cards = user_cards_ref.get()
            
            for card_doc in cards:
                card_data = card_doc.to_dict()
                question_id = card_doc.id
                
                # 新しい構造に変換
                new_card = {
                    "uid": uid,
                    "question_id": question_id,
                    "sm2_data": {
                        "n": card_data.get("n", 0),
                        "ef": card_data.get("EF", 2.5),
                        "interval": card_data.get("interval", 0),
                        "due_date": card_data.get("due") or card_data.get("nextReview"),
                        "last_studied": card_data.get("lastStudied")
                    },
                    "performance": {
                        "total_attempts": len(card_data.get("history", [])),
                        "correct_attempts": sum(1 for h in card_data.get("history", []) if h.get("quality", 0) >= 3),
                        "avg_quality": OptimizedFirestoreSchema._calculate_avg_quality(card_data.get("history", [])),
                        "last_quality": card_data.get("history", [{}])[-1].get("quality", 0) if card_data.get("history") else 0
                    },
                    "metadata": {
                        "created_at": datetime.datetime.now(),
                        "updated_at": datetime.datetime.now(),
                        "subject": OptimizedFirestoreSchema._get_subject_from_question_id(question_id),
                        "difficulty": "normal"
                    }
                }
                
                if not dry_run:
                    doc_id = f"{uid}_{question_id}"
                    db_manager.db.collection("study_cards").document(doc_id).set(new_card)
                
                migrated_count += 1
                
        except Exception as e:
            print(f"Error migrating cards for user {uid}: {e}")
        
        return migrated_count
    
    @staticmethod
    def _create_study_sessions_from_logs(uid: str, dry_run: bool) -> int:
        """既存の学習ログから学習セッションを作成"""
        # この実装は既存のlearningLogsコレクションから
        # セッション単位のデータを再構築する
        # 簡易版実装
        return 0
    
    @staticmethod
    def _create_analytics_summary(uid: str, dry_run: bool) -> int:
        """分析サマリーデータを作成"""
        if dry_run:
            return 1
        
        db_manager = get_firestore_manager()
        today = datetime.date.today()
        
        # 過去30日間の日次サマリーを作成
        for i in range(30):
            date = today - datetime.timedelta(days=i)
            doc_id = f"{uid}_daily_{date.isoformat()}"
            
            summary = {
                "uid": uid,
                "period": "daily",
                "date": date.isoformat(),
                "metrics": {
                    "questions_answered": 0,
                    "correct_answers": 0,
                    "accuracy": 0.0,
                    "study_time_minutes": 0,
                    "sessions_count": 0
                },
                "weak_subjects": [],
                "strong_subjects": [],
                "updated_at": datetime.datetime.now()
            }
            
            db_manager.db.collection("analytics_summary").document(doc_id).set(summary)
        
        return 30
    
    @staticmethod
    def _calculate_avg_quality(history: List[Dict]) -> float:
        """履歴から平均品質を計算"""
        if not history:
            return 0.0
        
        qualities = [h.get("quality", 0) for h in history if h.get("quality")]
        return sum(qualities) / len(qualities) if qualities else 0.0
    
    @staticmethod
    def _get_subject_from_question_id(question_id: str) -> str:
        """問題IDから科目を推定"""
        try:
            from data import load_data
            all_data = load_data()
            for q in all_data["questions"]:
                if q["number"] == question_id:
                    return q.get("subject", "未分類")
            return "未分類"
        except:
            return "未分類"
    
    @staticmethod
    def cleanup_old_collections(confirm: bool = False):
        """
        不要な古いコレクションをクリーンアップ
        
        削除対象：
        - daily_learning_logs (新しいstudy_sessionsに統合)
        - weekly_analytics_summary (analytics_summaryに統合)
        - learningLogs (study_sessionsに統合)
        - user_profiles (usersに統合)
        """
        if not confirm:
            st.warning("⚠️ この操作は元に戻せません。確認のため confirm=True を設定してください。")
            return
        
        db_manager = get_firestore_manager()
        collections_to_cleanup = [
            "daily_learning_logs",
            "weekly_analytics_summary", 
            "learningLogs",
            "user_profiles"
        ]
        
        st.info("🗑️ 古いコレクションをクリーンアップしています...")
        
        for collection_name in collections_to_cleanup:
            try:
                # コレクション内の全ドキュメントを削除
                docs = db_manager.db.collection(collection_name).limit(500).get()
                deleted_count = 0
                
                for doc in docs:
                    doc.reference.delete()
                    deleted_count += 1
                
                st.success(f"✅ {collection_name}: {deleted_count}件のドキュメントを削除")
                
            except Exception as e:
                st.error(f"❌ {collection_name}の削除中にエラー: {e}")


class NativeAppCompatibleAPI:
    """Native App (SwiftUI) 互換性のためのAPI"""
    
    @staticmethod
    def get_user_study_data(uid: str) -> Dict[str, Any]:
        """
        Native Appで使用するユーザー学習データを取得
        
        Returns:
            統一されたJSONレスポンス形式
        """
        db_manager = get_firestore_manager()
        
        try:
            # ユーザープロフィール取得
            user_doc = db_manager.db.collection("users").document(uid).get()
            user_data = user_doc.to_dict() if user_doc.exists else {}
            
            # 今日の復習対象カード取得
            today = datetime.datetime.now().date()
            cards_query = db_manager.db.collection("study_cards")\
                .where("uid", "==", uid)\
                .where("sm2_data.due_date", "<=", today)\
                .limit(20)
            
            due_cards = []
            for card_doc in cards_query.get():
                card_data = card_doc.to_dict()
                due_cards.append({
                    "question_id": card_data["question_id"],
                    "due_date": card_data["sm2_data"]["due_date"],
                    "difficulty": card_data["metadata"]["difficulty"]
                })
            
            # 最近の学習統計
            week_ago = (datetime.datetime.now() - datetime.timedelta(days=7)).date()
            weekly_summary_doc = db_manager.db.collection("analytics_summary")\
                .document(f"{uid}_weekly_{week_ago.isoformat()}").get()
            
            weekly_stats = weekly_summary_doc.to_dict() if weekly_summary_doc.exists else {}
            
            return {
                "status": "success",
                "user": {
                    "uid": uid,
                    "profile": user_data.get("profile", {}),
                    "statistics": user_data.get("statistics", {}),
                    "permissions": user_data.get("profile", {}).get("permissions", {})
                },
                "study_data": {
                    "due_cards_count": len(due_cards),
                    "due_cards": due_cards[:10],  # 最初の10件のみ
                    "weekly_stats": weekly_stats.get("metrics", {})
                },
                "last_updated": datetime.datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": str(e),
                "timestamp": datetime.datetime.now().isoformat()
            }
    
    @staticmethod
    def submit_study_session(uid: str, session_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Native Appからの学習セッション結果を受信
        
        Args:
            uid: ユーザーID
            session_data: 学習セッションデータ
        """
        db_manager = get_firestore_manager()
        
        try:
            # 学習セッション記録
            session_doc = {
                "uid": uid,
                "session_id": session_data.get("session_id"),
                "start_time": session_data.get("start_time"),
                "end_time": session_data.get("end_time"),
                "session_type": session_data.get("session_type", "manual"),
                "questions": session_data.get("questions", []),
                "summary": session_data.get("summary", {})
            }
            
            db_manager.db.collection("study_sessions").add(session_doc)
            
            # 各問題のSM2データ更新
            for question in session_data.get("questions", []):
                question_id = question["question_id"]
                quality = question.get("quality_rating", 3)
                is_correct = question.get("is_correct", False)
                
                # SM2アルゴリズム更新
                NativeAppCompatibleAPI._update_study_card(uid, question_id, quality, is_correct)
            
            # ユーザー統計更新
            NativeAppCompatibleAPI._update_user_statistics(uid, session_data)
            
            return {
                "status": "success",
                "message": "Study session recorded successfully",
                "timestamp": datetime.datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                "status": "error", 
                "message": str(e),
                "timestamp": datetime.datetime.now().isoformat()
            }
    
    @staticmethod
    def _update_study_card(uid: str, question_id: str, quality: int, is_correct: bool):
        """学習カードのSM2データを更新"""
        from utils import SM2Algorithm
        
        db_manager = get_firestore_manager()
        card_id = f"{uid}_{question_id}"
        card_ref = db_manager.db.collection("study_cards").document(card_id)
        
        card_doc = card_ref.get()
        if card_doc.exists:
            card_data = card_doc.to_dict()
            
            # SM2更新
            old_sm2 = card_data["sm2_data"]
            new_sm2 = SM2Algorithm.sm2_update({
                "n": old_sm2["n"],
                "EF": old_sm2["ef"], 
                "interval": old_sm2["interval"]
            }, quality)
            
            # パフォーマンス更新
            performance = card_data["performance"]
            performance["total_attempts"] += 1
            if is_correct:
                performance["correct_attempts"] += 1
            performance["last_quality"] = quality
            performance["avg_quality"] = (performance["avg_quality"] * (performance["total_attempts"] - 1) + quality) / performance["total_attempts"]
            
            # 更新
            card_ref.update({
                "sm2_data": {
                    "n": new_sm2["n"],
                    "ef": new_sm2["EF"],
                    "interval": new_sm2["interval"],
                    "due_date": new_sm2.get("due"),
                    "last_studied": datetime.datetime.now()
                },
                "performance": performance,
                "metadata.updated_at": datetime.datetime.now()
            })
    
    @staticmethod
    def _update_user_statistics(uid: str, session_data: Dict[str, Any]):
        """ユーザー統計の更新"""
        db_manager = get_firestore_manager()
        user_ref = db_manager.db.collection("users").document(uid)
        
        summary = session_data.get("summary", {})
        total_questions = summary.get("total_questions", 0)
        correct_answers = summary.get("correct_answers", 0)
        
        # 増分更新
        from google.cloud.firestore import Increment
        user_ref.update({
            "statistics.total_questions_answered": Increment(total_questions),
            "statistics.total_correct_answers": Increment(correct_answers),
            "statistics.last_study_date": datetime.date.today()
        })


def main():
    """データベース再構築のメイン関数"""
    st.title("🔧 Firestore Database Optimization")
    st.write("Cloud Firestoreのデータベース構造を最適化し、Native App対応を準備します")
    
    # 現在のユーザー取得
    uid = st.session_state.get("uid")
    if not uid:
        st.warning("ログインしてください")
        return
    
    # 操作選択
    operation = st.selectbox(
        "実行する操作を選択",
        [
            "スキーマ確認のみ",
            "データ移行（ドライラン）",
            "データ移行（実行）",
            "古いコレクション削除"
        ]
    )
    
    if st.button("実行"):
        if operation == "スキーマ確認のみ":
            st.json(OptimizedFirestoreSchema.get_core_collections())
            
        elif operation == "データ移行（ドライラン）":
            report = OptimizedFirestoreSchema.migrate_existing_data(uid, dry_run=True)
            st.json(report)
            
        elif operation == "データ移行（実行）":
            report = OptimizedFirestoreSchema.migrate_existing_data(uid, dry_run=False)
            st.json(report)
            
        elif operation == "古いコレクション削除":
            st.warning("⚠️ この操作は元に戻せません")
            if st.checkbox("理解しました"):
                OptimizedFirestoreSchema.cleanup_old_collections(confirm=True)


if __name__ == "__main__":
    main()
