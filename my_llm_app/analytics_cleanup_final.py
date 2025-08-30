#!/usr/bin/env python3
"""
分析コレクション最適化クリーンアップスクリプト
推奨順序に従って安全にコレクションを最適化
"""

from complete_migration_system import CompleteMigrationSystem
from datetime import datetime, timedelta
import time

class AnalyticsCleanup:
    def __init__(self):
        self.migration_system = CompleteMigrationSystem()
        self.db = self.migration_system.db
    
    def execute_priority_1_cleanup(self):
        """優先度1: monthly_analytics_summary削除"""
        print("🗑️  優先度1: monthly_analytics_summaryを削除中...")
        
        collection = self.db.collection('monthly_analytics_summary')
        docs = list(collection.stream())
        
        print(f"   削除対象: {len(docs)}ドキュメント")
        
        batch = self.db.batch()
        for doc in docs:
            batch.delete(doc.reference)
        
        batch.commit()
        print("   ✅ 完了")
    
    def execute_priority_2_cleanup(self):
        """優先度2: daily_learning_logs削除"""
        print("🗑️  優先度2: daily_learning_logsを削除中...")
        
        collection = self.db.collection('daily_learning_logs')
        docs = list(collection.stream())
        
        print(f"   削除対象: {len(docs)}ドキュメント")
        
        batch = self.db.batch()
        for doc in docs:
            batch.delete(doc.reference)
        
        batch.commit()
        print("   ✅ 完了")
    
    def execute_priority_3_cleanup(self):
        """優先度3: analytics_summary選択的削除"""
        print("🗑️  優先度3: analytics_summary古いデータを削除中...")
        
        cutoff_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        collection = self.db.collection('analytics_summary')
        
        docs = [doc for doc in collection.stream() 
                if doc.to_dict().get('date', '9999-12-31') < cutoff_date]
        
        print(f"   削除対象: {len(docs)}ドキュメント (基準日: {cutoff_date})")
        
        if docs:
            batch = self.db.batch()
            for doc in docs:
                batch.delete(doc.reference)
            
            batch.commit()
            print("   ✅ 完了")
        else:
            print("   ℹ️  削除対象なし")
    
    def run_full_cleanup(self):
        """完全クリーンアップの実行"""
        print("🚀 分析コレクション最適化クリーンアップ開始")
        print("=" * 50)
        
        try:
            self.execute_priority_1_cleanup()
            time.sleep(2)
            
            self.execute_priority_2_cleanup()
            time.sleep(2)
            
            self.execute_priority_3_cleanup()
            
            print("\n🎉 クリーンアップ完了！")
            print("✨ Firestore最適化が完了しました")
            
        except Exception as e:
            print(f"❌ エラー: {e}")
            return False
        
        return True

if __name__ == "__main__":
    cleanup = AnalyticsCleanup()
    cleanup.run_full_cleanup()
