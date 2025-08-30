"""
学士権限移行のテスト用スクリプト

移行前後で学士権限が正しく保持されているかを確認します。
"""

import datetime
from typing import Dict, Any, List
from complete_migration_system import CompleteMigrationSystem
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GakushiMigrationTest:
    """学士権限移行テスト"""
    
    def __init__(self):
        self.migration_system = CompleteMigrationSystem()
        self.db = self.migration_system.db
    
    def test_gakushi_permission_preservation(self, test_uid: str = None) -> Dict[str, Any]:
        """学士権限の保持テスト"""
        results = {
            "test_started_at": datetime.datetime.now(),
            "users_tested": [],
            "permission_changes": [],
            "errors": []
        }
        
        try:
            # テスト対象ユーザーの取得
            if test_uid:
                test_users = [test_uid]
            else:
                # ランダムに数名をテスト
                users_ref = self.db.collection("users").limit(5)
                users_docs = list(users_ref.stream())
                test_users = [doc.id for doc in users_docs]
            
            logger.info(f"学士権限テスト開始: {len(test_users)}名のユーザー")
            
            for uid in test_users:
                user_result = self._test_single_user_permission(uid)
                results["users_tested"].append(user_result)
                
                if user_result["permission_changed"]:
                    results["permission_changes"].append(user_result)
            
            # サマリー作成
            total_users = len(results["users_tested"])
            users_with_changes = len(results["permission_changes"])
            
            results["summary"] = {
                "total_users_tested": total_users,
                "users_with_permission_changes": users_with_changes,
                "success_rate": (total_users - users_with_changes) / total_users if total_users > 0 else 0
            }
            
            logger.info(f"学士権限テスト完了: 成功率 {results['summary']['success_rate']:.1%}")
            return results
            
        except Exception as e:
            logger.error(f"テストエラー: {e}")
            results["errors"].append(str(e))
            return results
    
    def _test_single_user_permission(self, uid: str) -> Dict[str, Any]:
        """単一ユーザーの権限テスト"""
        result = {
            "uid": uid[:8],  # セキュリティのため短縮
            "permission_before": None,
            "permission_after": None,
            "permission_changed": False,
            "error": None
        }
        
        try:
            # 移行前の権限取得（user_permissionsから）
            permission_doc = self.db.collection("user_permissions").document(uid).get()
            if permission_doc.exists:
                permission_data = permission_doc.to_dict()
                result["permission_before"] = permission_data.get("can_access_gakushi", False)
            else:
                result["permission_before"] = None  # 権限設定なし
            
            # 移行後の権限取得（usersから）
            user_doc = self.db.collection("users").document(uid).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                result["permission_after"] = user_data.get("settings", {}).get("can_access_gakushi", False)
            else:
                result["permission_after"] = None
            
            # 権限変更の確認
            if result["permission_before"] is not None and result["permission_after"] is not None:
                result["permission_changed"] = result["permission_before"] != result["permission_after"]
            
            return result
            
        except Exception as e:
            logger.error(f"ユーザー権限テストエラー (uid: {uid[:8]}): {e}")
            result["error"] = str(e)
            return result
    
    def check_current_gakushi_permissions(self) -> Dict[str, Any]:
        """現在の学士権限状況確認"""
        results = {
            "checked_at": datetime.datetime.now(),
            "user_permissions_count": 0,
            "users_with_gakushi": 0,
            "users_in_main_collection": 0,
            "sample_permissions": []
        }
        
        try:
            # user_permissionsコレクションの確認
            permissions_ref = self.db.collection("user_permissions")
            permissions_docs = list(permissions_ref.stream())
            
            results["user_permissions_count"] = len(permissions_docs)
            
            for doc in permissions_docs[:5]:  # サンプル5件
                permission_data = doc.to_dict()
                can_access = permission_data.get("can_access_gakushi", False)
                
                if can_access:
                    results["users_with_gakushi"] += 1
                
                results["sample_permissions"].append({
                    "uid": doc.id[:8],
                    "can_access_gakushi": can_access
                })
            
            # usersコレクション内の権限確認
            users_ref = self.db.collection("users")
            users_docs = list(users_ref.stream())
            
            results["users_in_main_collection"] = len(users_docs)
            
            logger.info(f"権限確認完了: user_permissions {results['user_permissions_count']}件, users {results['users_in_main_collection']}件")
            return results
            
        except Exception as e:
            logger.error(f"権限確認エラー: {e}")
            results["error"] = str(e)
            return results
    
    def demo_permission_migration(self, demo_uid: str = "demo_user_123") -> bool:
        """権限移行のデモ"""
        try:
            logger.info(f"権限移行デモ開始: {demo_uid}")
            
            # 1. デモ用の権限データ作成
            demo_permission = {
                "can_access_gakushi": True,
                "created_at": datetime.datetime.now(),
                "test_data": True
            }
            
            self.db.collection("user_permissions").document(demo_uid).set(demo_permission)
            logger.info("デモ用権限データ作成完了")
            
            # 2. 権限移行のテスト
            migrated_permission = self.migration_system._get_gakushi_permission(demo_uid)
            logger.info(f"移行された権限: {migrated_permission}")
            
            # 3. クリーンアップ
            self.db.collection("user_permissions").document(demo_uid).delete()
            logger.info("デモデータクリーンアップ完了")
            
            return migrated_permission == True
            
        except Exception as e:
            logger.error(f"デモエラー: {e}")
            return False


def run_gakushi_permission_test():
    """学士権限テストの実行"""
    tester = GakushiMigrationTest()
    
    print("🧪 学士権限移行テストを開始します")
    
    # 1. 現在の権限状況確認
    print("\n📊 現在の権限状況確認中...")
    current_status = tester.check_current_gakushi_permissions()
    print(f"user_permissions: {current_status['user_permissions_count']}件")
    print(f"users: {current_status['users_in_main_collection']}件")
    print(f"学士権限ありのユーザー: {current_status['users_with_gakushi']}名")
    
    # 2. デモ移行テスト
    print("\n🔄 権限移行デモテスト...")
    demo_success = tester.demo_permission_migration()
    print(f"デモテスト結果: {'✅ 成功' if demo_success else '❌ 失敗'}")
    
    # 3. 実際のユーザーでのテスト（少数）
    print("\n🔍 実ユーザーでの権限保持テスト...")
    test_results = tester.test_gakushi_permission_preservation()
    print(f"テスト対象: {test_results['summary']['total_users_tested']}名")
    print(f"権限変更検出: {test_results['summary']['users_with_permission_changes']}名")
    print(f"成功率: {test_results['summary']['success_rate']:.1%}")
    
    return demo_success and test_results['summary']['success_rate'] > 0.8


if __name__ == "__main__":
    run_gakushi_permission_test()
