"""
Firestore安全削除スクリプト
段階的にコレクションを削除し、各段階で確認を行います。
"""

import datetime
import time
from typing import Dict, Any, List
from complete_migration_system import CompleteMigrationSystem
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FirestoreSafeCleanup:
    """Firestore安全削除クラス"""
    
    def __init__(self):
        # 既存の移行システムからFirestore接続を取得
        migration_system = CompleteMigrationSystem()
        self.db = migration_system.db
        self.deletion_log = []
    
    def delete_collection_safe(self, collection_name: str, confirm: bool = False) -> Dict[str, Any]:
        """コレクションの安全削除"""
        result = {
            "collection": collection_name,
            "started_at": datetime.datetime.now(),
            "deleted_count": 0,
            "errors": [],
            "status": "pending"
        }
        
        try:
            # 1. 削除対象の確認
            collection_ref = self.db.collection(collection_name)
            docs = list(collection_ref.stream())
            doc_count = len(docs)
            
            logger.info(f"削除対象: {collection_name} ({doc_count}件)")
            
            if doc_count == 0:
                result["status"] = "already_empty"
                return result
            
            if not confirm:
                result["status"] = "confirmation_required"
                result["document_count"] = doc_count
                return result
            
            # 2. バッチ削除実行
            batch_size = 100
            deleted = 0
            
            for i in range(0, doc_count, batch_size):
                batch_docs = docs[i:i + batch_size]
                batch = self.db.batch()
                
                for doc in batch_docs:
                    batch.delete(doc.reference)
                
                batch.commit()
                deleted += len(batch_docs)
                
                logger.info(f"{collection_name}: {deleted}/{doc_count}件削除完了")
                time.sleep(0.1)  # 負荷軽減
            
            result["deleted_count"] = deleted
            result["status"] = "completed"
            
            # 削除ログに記録
            self.deletion_log.append({
                "collection": collection_name,
                "deleted_at": datetime.datetime.now(),
                "count": deleted
            })
            
            logger.info(f"✅ {collection_name}削除完了: {deleted}件")
            
        except Exception as e:
            logger.error(f"❌ {collection_name}削除エラー: {e}")
            result["errors"].append(str(e))
            result["status"] = "error"
        
        return result
    
    def delete_user_subcollections_safe(self, subcollection_name: str, confirm: bool = False) -> Dict[str, Any]:
        """ユーザーサブコレクションの安全削除"""
        result = {
            "subcollection": subcollection_name,
            "started_at": datetime.datetime.now(),
            "users_processed": 0,
            "total_deleted": 0,
            "errors": [],
            "status": "pending"
        }
        
        try:
            # 1. 全ユーザーの取得
            users_ref = self.db.collection("users")
            users_docs = list(users_ref.stream())
            
            total_subcollection_docs = 0
            
            # サブコレクション数の事前カウント
            for user_doc in users_docs:
                subcol_ref = user_doc.reference.collection(subcollection_name)
                subcol_docs = list(subcol_ref.stream())
                total_subcollection_docs += len(subcol_docs)
            
            logger.info(f"削除対象: {len(users_docs)}ユーザーの{subcollection_name} (合計{total_subcollection_docs}件)")
            
            if total_subcollection_docs == 0:
                result["status"] = "already_empty"
                return result
            
            if not confirm:
                result["status"] = "confirmation_required"
                result["user_count"] = len(users_docs)
                result["total_documents"] = total_subcollection_docs
                return result
            
            # 2. 各ユーザーのサブコレクション削除
            users_processed = 0
            total_deleted = 0
            
            for user_doc in users_docs:
                subcol_ref = user_doc.reference.collection(subcollection_name)
                subcol_docs = list(subcol_ref.stream())
                
                if subcol_docs:
                    # バッチで削除
                    batch = self.db.batch()
                    for doc in subcol_docs:
                        batch.delete(doc.reference)
                    
                    batch.commit()
                    total_deleted += len(subcol_docs)
                    
                    logger.info(f"ユーザー {user_doc.id[:8]}: {len(subcol_docs)}件削除")
                
                users_processed += 1
                
                if users_processed % 10 == 0:
                    logger.info(f"進捗: {users_processed}/{len(users_docs)}ユーザー処理完了")
                
                time.sleep(0.05)  # 負荷軽減
            
            result["users_processed"] = users_processed
            result["total_deleted"] = total_deleted
            result["status"] = "completed"
            
            logger.info(f"✅ {subcollection_name}サブコレクション削除完了: {total_deleted}件")
            
        except Exception as e:
            logger.error(f"❌ {subcollection_name}サブコレクション削除エラー: {e}")
            result["errors"].append(str(e))
            result["status"] = "error"
        
        return result
    
    def get_deletion_plan(self) -> Dict[str, Any]:
        """削除計画の作成"""
        plan = {
            "created_at": datetime.datetime.now(),
            "phase_1": {
                "name": "権限コレクション削除",
                "collections": ["user_permissions"],
                "reason": "学士権限はusers.settings.can_access_gakushiに移行済み",
                "risk": "低"
            },
            "phase_2": {
                "name": "プロファイルコレクション削除", 
                "collections": ["user_profiles"],
                "reason": "プロフィール情報はusersコレクションに統合済み",
                "risk": "低"
            },
            "phase_3": {
                "name": "進捗コレクション削除",
                "collections": ["user_progress"],
                "reason": "統計情報はusers.statsに統合済み",
                "risk": "低"
            },
            "phase_4": {
                "name": "学習ログ削除",
                "collections": ["learningLogs"],
                "reason": "学習履歴はstudy_cardsに最適化統合済み",
                "risk": "中"
            },
            "phase_5": {
                "name": "サブコレクション削除",
                "subcollections": ["userCards"],
                "reason": "学習カードはstudy_cardsに最適化移行済み",
                "risk": "低"
            }
        }
        return plan
    
    def execute_phase(self, phase_number: int, confirm: bool = False) -> Dict[str, Any]:
        """フェーズ実行"""
        plan = self.get_deletion_plan()
        phase_key = f"phase_{phase_number}"
        
        if phase_key not in plan:
            return {"error": f"フェーズ{phase_number}は存在しません"}
        
        phase = plan[phase_key]
        results = {
            "phase": phase_number,
            "name": phase["name"],
            "started_at": datetime.datetime.now(),
            "operations": []
        }
        
        # コレクション削除
        if "collections" in phase:
            for collection in phase["collections"]:
                result = self.delete_collection_safe(collection, confirm=confirm)
                results["operations"].append(result)
        
        # サブコレクション削除
        if "subcollections" in phase:
            for subcollection in phase["subcollections"]:
                result = self.delete_user_subcollections_safe(subcollection, confirm=confirm)
                results["operations"].append(result)
        
        return results


def interactive_cleanup():
    """対話式クリーンアップ"""
    cleanup = FirestoreSafeCleanup()
    
    print("🗂️ Firestore安全クリーンアップ")
    print("=" * 50)
    
    # 削除計画の表示
    plan = cleanup.get_deletion_plan()
    print("\n📋 削除計画:")
    
    for phase_key, phase in plan.items():
        if phase_key.startswith("phase_"):
            phase_num = phase_key.split("_")[1]
            print(f"\nフェーズ{phase_num}: {phase['name']}")
            print(f"  対象: {phase.get('collections', [])} {phase.get('subcollections', [])}")
            print(f"  理由: {phase['reason']}")
            print(f"  リスク: {phase['risk']}")
    
    print("\n⚠️ 重要: 各フェーズは段階的に実行し、動作確認を行ってください")
    
    return cleanup


def run_single_phase(phase_number: int, dry_run: bool = True):
    """単一フェーズの実行"""
    cleanup = FirestoreSafeCleanup()
    
    print(f"🎯 フェーズ{phase_number}実行" + (" (ドライラン)" if dry_run else " (実行)"))
    
    result = cleanup.execute_phase(phase_number, confirm=not dry_run)
    
    print(f"\nフェーズ{phase_number}: {result['name']}")
    
    for operation in result["operations"]:
        if operation["status"] == "confirmation_required":
            count = operation.get("document_count", operation.get("total_documents", 0))
            name = operation.get("collection", operation.get("subcollection"))
            print(f"  {name}: {count}件の削除が必要")
        elif operation["status"] == "completed":
            deleted = operation.get("deleted_count", operation.get("total_deleted", 0))
            name = operation.get("collection", operation.get("subcollection"))
            print(f"  ✅ {name}: {deleted}件削除完了")
        elif operation["status"] == "already_empty":
            name = operation.get("collection", operation.get("subcollection"))
            print(f"  ℹ️  {name}: 既に空です")
        elif operation["status"] == "error":
            name = operation.get("collection", operation.get("subcollection"))
            print(f"  ❌ {name}: エラー - {operation['errors']}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "--interactive":
            cleanup = interactive_cleanup()
        elif sys.argv[1].startswith("--phase="):
            phase_num = int(sys.argv[1].split("=")[1])
            dry_run = "--confirm" not in sys.argv
            run_single_phase(phase_num, dry_run=dry_run)
        else:
            print("使用方法:")
            print("  python firestore_safe_cleanup.py --interactive")
            print("  python firestore_safe_cleanup.py --phase=1 [--confirm]")
    else:
        # デフォルト: 全フェーズのドライラン
        print("🔍 全フェーズドライラン実行")
        for i in range(1, 6):
            run_single_phase(i, dry_run=True)
            print()
