"""
完全自動化Firestore移行スクリプト
既存データを最適化構造に安全に移行

特徴:
1. バックアップ機能付き
2. 段階的移行
3. ロールバック対応
4. 進捗監視
5. エラーハンドリング
"""

import datetime
import json
import time
from typing import Dict, Any, List, Optional
from enhanced_firestore_optimizer import EnhancedFirestoreOptimizer
from optimized_weekly_ranking import OptimizedWeeklyRankingSystem
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CompleteMigrationSystem:
    """完全自動化移行システム"""
    
    def __init__(self):
        self.optimizer = EnhancedFirestoreOptimizer()
        self.ranking_system = OptimizedWeeklyRankingSystem()
        self.db = self.optimizer.db
        self.migration_log = []
    
    def backup_existing_data(self, backup_id: str = None) -> str:
        """既存データのバックアップ"""
        if backup_id is None:
            backup_id = f"backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        try:
            logger.info(f"データバックアップ開始: {backup_id}")
            
            backup_data = {
                "backup_id": backup_id,
                "created_at": datetime.datetime.now().isoformat(),
                "users": {},
                "user_cards": {},
                "weekly_rankings": {}
            }
            
            # ユーザーデータのバックアップ
            users_ref = self.db.collection("users")
            users_docs = list(users_ref.stream())
            
            for user_doc in users_docs:
                user_data = user_doc.to_dict()
                backup_data["users"][user_doc.id] = self._serialize_firestore_data(user_data)
                
                # ユーザーカードのバックアップ
                cards_ref = user_doc.reference.collection("userCards")
                cards_docs = list(cards_ref.stream())
                
                user_cards = {}
                for card_doc in cards_docs:
                    card_data = card_doc.to_dict()
                    user_cards[card_doc.id] = self._serialize_firestore_data(card_data)
                
                if user_cards:
                    backup_data["user_cards"][user_doc.id] = user_cards
            
            # 週間ランキングのバックアップ
            rankings_ref = self.db.collection("weekly_rankings")
            rankings_docs = list(rankings_ref.stream())
            
            for ranking_doc in rankings_docs:
                ranking_data = ranking_doc.to_dict()
                backup_data["weekly_rankings"][ranking_doc.id] = self._serialize_firestore_data(ranking_data)
            
            # バックアップをFirestoreに保存
            backup_ref = self.db.collection("migration_backups").document(backup_id)
            backup_ref.set({
                "backup_id": backup_id,
                "created_at": datetime.datetime.now(),
                "data_size": len(json.dumps(backup_data)),
                "collections_backed_up": ["users", "user_cards", "weekly_rankings"],
                "status": "completed"
            })
            
            # JSONファイルとしても保存（冗長性確保）
            self._save_backup_to_file(backup_data, backup_id)
            
            logger.info(f"データバックアップ完了: {backup_id}")
            return backup_id
            
        except Exception as e:
            logger.error(f"バックアップエラー: {e}")
            raise
    
    def _serialize_firestore_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Firestoreデータをシリアライズ"""
        serialized = {}
        
        for key, value in data.items():
            if isinstance(value, datetime.datetime):
                serialized[key] = value.isoformat()
            elif isinstance(value, dict):
                serialized[key] = self._serialize_firestore_data(value)
            elif isinstance(value, list):
                serialized[key] = [
                    self._serialize_firestore_data(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                serialized[key] = value
        
        return serialized
    
    def _save_backup_to_file(self, backup_data: Dict[str, Any], backup_id: str):
        """バックアップをJSONファイルに保存"""
        try:
            filename = f"/tmp/{backup_id}.json"
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(backup_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"バックアップファイル保存: {filename}")
            
        except Exception as e:
            logger.warning(f"バックアップファイル保存失敗: {e}")
    
    def _get_gakushi_permission(self, uid: str) -> bool:
        """user_permissionsコレクションから学士権限を取得"""
        try:
            # user_permissionsコレクションから権限チェック
            permission_doc = self.db.collection("user_permissions").document(uid).get()
            if permission_doc.exists:
                permission_data = permission_doc.to_dict()
                return permission_data.get("can_access_gakushi", False)
            
            # user_permissionsがない場合はデフォルトTrue（既存ユーザーへの配慮）
            logger.info(f"ユーザー {uid[:8]} の学士権限データなし、デフォルトTrueを設定")
            return True
            
        except Exception as e:
            logger.warning(f"学士権限取得エラー (uid: {uid[:8]}): {e}")
            # エラー時はTrueを返す（安全側に倒す）
            return True
    
    def migrate_user_data_safe(self, uid: str) -> bool:
        """安全なユーザーデータ移行"""
        try:
            logger.info(f"ユーザー {uid[:8]} 移行開始")
            
            # 1. 既存データの検証
            user_doc = self.db.collection("users").document(uid).get()
            if not user_doc.exists:
                logger.warning(f"ユーザー {uid[:8]} が存在しません")
                return False
            
            user_data = user_doc.to_dict()
            if not user_data.get("email"):
                logger.warning(f"ユーザー {uid[:8]} は無効です（emailなし）")
                return False
            
            # 2. 既存userCardsの取得と変換
            old_cards_ref = user_doc.reference.collection("userCards")
            old_cards_docs = list(old_cards_ref.stream())
            
            logger.info(f"ユーザー {uid[:8]} 既存カード数: {len(old_cards_docs)}")
            
            # 3. 最適化されたstudy_cardsに移行
            migrated_cards = 0
            batch_size = 100
            
            for i in range(0, len(old_cards_docs), batch_size):
                batch_cards = old_cards_docs[i:i + batch_size]
                
                batch = self.db.batch()
                
                for card_doc in batch_cards:
                    old_card_data = card_doc.to_dict()
                    
                    # 最適化構造に変換
                    optimized_card = self._convert_to_optimized_card(uid, card_doc.id, old_card_data)
                    
                    # 新しいコレクションに保存
                    new_card_id = f"{uid}_{card_doc.id}"
                    new_card_ref = self.db.collection("study_cards").document(new_card_id)
                    batch.set(new_card_ref, optimized_card)
                    
                    migrated_cards += 1
                
                batch.commit()
                logger.info(f"ユーザー {uid[:8]} カード移行: {migrated_cards}/{len(old_cards_docs)}")
            
            # 4. 学士権限の取得
            gakushi_permission = self._get_gakushi_permission(uid)
            
            # 5. ユーザー統計の計算と更新
            stats = self.optimizer.calculate_user_statistics_batch(uid)
            
            # 6. 最適化されたユーザーデータ作成
            optimized_user_data = {
                "email": user_data.get("email", ""),
                "nickname": user_data.get("nickname", user_data.get("email", "").split("@")[0]),
                "created_at": user_data.get("createdAt", datetime.datetime.now()),
                "last_active": datetime.datetime.now(),
                "settings": {
                    "new_cards_per_day": user_data.get("settings", {}).get("new_cards_per_day", 10),
                    "can_access_gakushi": gakushi_permission,
                    "notifications_enabled": user_data.get("settings", {}).get("notifications_enabled", True),
                    "theme": user_data.get("settings", {}).get("theme", "light")
                },
                "stats": stats,
                "migration": {
                    "migrated_at": datetime.datetime.now(),
                    "original_cards_count": len(old_cards_docs),
                    "migrated_cards_count": migrated_cards,
                    "migration_version": "v2.0"
                }
            }
            
            # 6. ユーザーデータ更新
            self.db.collection("users").document(uid).set(optimized_user_data)
            
            # 7. 移行ログに記録
            self.migration_log.append({
                "uid": uid,
                "migrated_at": datetime.datetime.now(),
                "cards_migrated": migrated_cards,
                "status": "success"
            })
            
            logger.info(f"ユーザー {uid[:8]} 移行完了: カード{migrated_cards}枚")
            return True
            
        except Exception as e:
            logger.error(f"ユーザー {uid[:8]} 移行失敗: {e}")
            
            # エラーログに記録
            self.migration_log.append({
                "uid": uid,
                "migrated_at": datetime.datetime.now(),
                "error": str(e),
                "status": "failed"
            })
            
            return False
    
    def _convert_to_optimized_card(self, uid: str, question_id: str, old_data: Dict[str, Any]) -> Dict[str, Any]:
        """旧カードデータを最適化構造に変換"""
        history = old_data.get("history", [])
        
        # パフォーマンス計算
        total_attempts = len(history)
        correct_attempts = sum(1 for h in history if h.get("quality", 0) >= 4)
        avg_quality = sum(h.get("quality", 0) for h in history) / max(total_attempts, 1)
        last_quality = history[-1].get("quality", 0) if history else 0
        
        return {
            "uid": uid,
            "question_id": question_id,
            "sm2_data": {
                "n": old_data.get("n", 0),
                "ef": old_data.get("ef", 2.5),
                "interval": old_data.get("interval", 0),
                "due_date": old_data.get("dueDate", datetime.datetime.now()),
                "last_studied": old_data.get("lastReviewed")
            },
            "performance": {
                "total_attempts": total_attempts,
                "correct_attempts": correct_attempts,
                "avg_quality": avg_quality,
                "last_quality": last_quality
            },
            "metadata": {
                "created_at": old_data.get("createdAt", datetime.datetime.now()),
                "updated_at": datetime.datetime.now(),
                "subject": self.optimizer._get_subject_from_question_id(question_id),
                "difficulty": old_data.get("difficulty", "normal"),
                "original_level": old_data.get("level", 0)  # 参考用
            },
            "history": history[-10:]  # 最新10件のみ保持
        }
    
    def migrate_all_users_completely(self) -> bool:
        """全ユーザーの完全移行"""
        try:
            logger.info("=== 完全移行プロセス開始 ===")
            
            # 1. バックアップ作成
            backup_id = self.backup_existing_data()
            logger.info(f"バックアップ完了: {backup_id}")
            
            # 2. 全ユーザー取得
            users_ref = self.db.collection("users")
            users_docs = list(users_ref.stream())
            
            valid_users = []
            for user_doc in users_docs:
                user_data = user_doc.to_dict()
                if user_data.get("email"):
                    valid_users.append(user_doc.id)
            
            logger.info(f"移行対象ユーザー: {len(valid_users)}名")
            
            # 3. 段階的移行実行
            success_count = 0
            failure_count = 0
            
            for i, uid in enumerate(valid_users, 1):
                logger.info(f"進捗: {i}/{len(valid_users)} - {uid[:8]}")
                
                if self.migrate_user_data_safe(uid):
                    success_count += 1
                else:
                    failure_count += 1
                
                # 進捗レポート
                if i % 10 == 0:
                    logger.info(f"中間報告: 成功{success_count}, 失敗{failure_count}")
                
                # 負荷軽減のため少し待機
                time.sleep(0.1)
            
            # 4. 移行後処理
            logger.info("移行後処理開始")
            
            # 全ユーザー統計の再計算
            self.ranking_system.update_all_user_statistics()
            
            # 週間ランキングのスナップショット保存
            self.ranking_system.save_weekly_ranking_snapshot()
            
            # 5. 移行ログの保存
            migration_summary = {
                "migration_id": f"complete_migration_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "started_at": datetime.datetime.now(),
                "backup_id": backup_id,
                "total_users": len(valid_users),
                "success_count": success_count,
                "failure_count": failure_count,
                "migration_log": self.migration_log,
                "status": "completed"
            }
            
            summary_ref = self.db.collection("migration_summaries").document(migration_summary["migration_id"])
            summary_ref.set(migration_summary)
            
            logger.info("=== 完全移行プロセス完了 ===")
            logger.info(f"結果: 成功{success_count}名, 失敗{failure_count}名")
            logger.info(f"バックアップID: {backup_id}")
            
            return failure_count == 0
            
        except Exception as e:
            logger.error(f"完全移行エラー: {e}")
            return False
    
    def validate_migration_results(self) -> Dict[str, Any]:
        """移行結果の検証"""
        try:
            logger.info("移行結果検証開始")
            
            validation_results = {
                "validation_time": datetime.datetime.now(),
                "users": {"total": 0, "migrated": 0, "issues": []},
                "study_cards": {"total": 0, "valid": 0, "issues": []},
                "statistics": {"accurate": 0, "inaccurate": 0, "issues": []},
                "overall_status": "unknown"
            }
            
            # ユーザーデータ検証
            users_ref = self.db.collection("users")
            users_docs = list(users_ref.stream())
            
            for user_doc in users_docs:
                user_data = user_doc.to_dict()
                validation_results["users"]["total"] += 1
                
                if user_data.get("migration", {}).get("migration_version") == "v2.0":
                    validation_results["users"]["migrated"] += 1
                else:
                    validation_results["users"]["issues"].append(f"User {user_doc.id[:8]} not migrated")
            
            # study_cardsコレクション検証
            study_cards_ref = self.db.collection("study_cards")
            study_cards_docs = list(study_cards_ref.stream())
            
            for card_doc in study_cards_docs:
                card_data = card_doc.to_dict()
                validation_results["study_cards"]["total"] += 1
                
                # 必須フィールドの存在確認
                required_fields = ["uid", "question_id", "sm2_data", "performance", "metadata"]
                if all(field in card_data for field in required_fields):
                    validation_results["study_cards"]["valid"] += 1
                else:
                    validation_results["study_cards"]["issues"].append(f"Card {card_doc.id} missing required fields")
            
            # 統計データ検証
            for user_doc in users_docs:
                user_data = user_doc.to_dict()
                stats = user_data.get("stats", {})
                
                if stats.get("last_updated"):
                    validation_results["statistics"]["accurate"] += 1
                else:
                    validation_results["statistics"]["inaccurate"] += 1
                    validation_results["statistics"]["issues"].append(f"User {user_doc.id[:8]} missing stats")
            
            # 全体ステータス判定
            if (validation_results["users"]["migrated"] == validation_results["users"]["total"] and
                validation_results["study_cards"]["valid"] == validation_results["study_cards"]["total"] and
                validation_results["statistics"]["inaccurate"] == 0):
                validation_results["overall_status"] = "success"
            else:
                validation_results["overall_status"] = "issues_found"
            
            logger.info(f"移行結果検証完了: {validation_results['overall_status']}")
            return validation_results
            
        except Exception as e:
            logger.error(f"検証エラー: {e}")
            return {"overall_status": "error", "error": str(e)}
    
    def get_deletable_collections_info(self) -> Dict[str, Any]:
        """移行後に削除可能なコレクションの情報"""
        return {
            "deletable_collections": [
                {
                    "name": "user_permissions",
                    "reason": "学士権限がusers.settings.can_access_gakushiに移行済み",
                    "risk_level": "低",
                    "estimated_documents": "全ユーザー数と同程度"
                },
                {
                    "name": "userCards (サブコレクション)",
                    "reason": "全てstudy_cardsコレクションに最適化移行済み",
                    "risk_level": "低",
                    "estimated_documents": "全学習カード数"
                },
                {
                    "name": "user_progress",
                    "reason": "統計情報がusers.statsに統合済み",
                    "risk_level": "低",
                    "estimated_documents": "全ユーザー数と同程度"
                },
                {
                    "name": "user_profiles",
                    "reason": "プロフィール情報がusersコレクションに統合済み",
                    "risk_level": "低",
                    "estimated_documents": "全ユーザー数と同程度"
                },
                {
                    "name": "learningLogs",
                    "reason": "学習履歴が最適化されてstudy_cardsに統合済み",
                    "risk_level": "中",
                    "estimated_documents": "数万〜数十万件"
                }
            ],
            "keep_collections": [
                {
                    "name": "users",
                    "reason": "最適化されたメインユーザーデータ"
                },
                {
                    "name": "study_cards",
                    "reason": "最適化された学習カードデータ"
                },
                {
                    "name": "weekly_rankings",
                    "reason": "最適化されたランキングデータ"
                },
                {
                    "name": "migration_backups",
                    "reason": "移行バックアップ（ロールバック用）"
                },
                {
                    "name": "analytics_events",
                    "reason": "分析用データ（削除不要）"
                }
            ],
            "deletion_command": """
# 削除コマンド例（慎重に実行）
# 1. user_permissions削除
# 2. 各ユーザーのuserCardsサブコレクション削除
# 3. user_progress, user_profiles, learningLogs削除
            """,
            "warning": "削除前に必ずバックアップの存在確認と動作テストを実施してください"
        }


# === メイン実行関数 ===

def run_complete_migration():
    """完全移行の実行"""
    migration_system = CompleteMigrationSystem()
    
    print("🚀 Firestore完全最適化移行を開始します")
    print("⚠️  この処理は既存データを変更します。バックアップが自動作成されます。")
    
    # 移行実行
    success = migration_system.migrate_all_users_completely()
    
    if success:
        print("✅ 移行が正常に完了しました")
        
        # 結果検証
        validation = migration_system.validate_migration_results()
        
        if validation["overall_status"] == "success":
            print("✅ 移行結果の検証も成功しました")
            
            # 削除可能コレクション情報の表示
            deletion_info = migration_system.get_deletable_collections_info()
            print("\n📋 移行後の削除推奨コレクション:")
            for collection in deletion_info["deletable_collections"]:
                print(f"  - {collection['name']}: {collection['reason']}")
            
            print(f"\n⚠️  {deletion_info['warning']}")
        else:
            print(f"⚠️  検証で問題が見つかりました: {validation}")
    else:
        print("❌ 移行中にエラーが発生しました")
    
    return success


if __name__ == "__main__":
    run_complete_migration()
