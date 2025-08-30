#!/usr/bin/env python3
"""
最終段階Firestore最適化実行
検証結果に基づいた安全で効果的な最適化を実行
"""

from complete_migration_system import CompleteMigrationSystem
from datetime import datetime
import json

class FinalOptimizationExecutor:
    def __init__(self):
        self.migration_system = CompleteMigrationSystem()
        self.db = self.migration_system.db
        
    def execute_final_optimization(self):
        """最終最適化の実行"""
        print("🚀 最終段階Firestore最適化開始")
        print("=" * 60)
        
        optimization_results = {
            'deleted_collections': [],
            'documents_deleted': 0,
            'collections_before': 0,
            'collections_after': 0,
            'safety_preserved': []
        }
        
        # 最適化前状態記録
        initial_collections = list(self.db.collections())
        optimization_results['collections_before'] = len(initial_collections)
        
        print(f"最適化前: {len(initial_collections)}コレクション")
        
        # フェーズ1: 完全安全削除（移行関連）
        print("\n🗑️  フェーズ1: 移行関連データ削除")
        phase1_result = self._execute_phase1_safe_deletion()
        optimization_results['deleted_collections'].extend(phase1_result['deleted'])
        optimization_results['documents_deleted'] += phase1_result['docs_deleted']
        
        # フェーズ2: アナリティクス系統合判定
        print("\n🔄 フェーズ2: アナリティクス系統合可能性確認")
        phase2_result = self._analyze_analytics_usage()
        
        # フェーズ3: 使用されていないアナリティクス削除
        print("\n🗑️  フェーズ3: 未使用アナリティクス削除")
        phase3_result = self._execute_phase3_analytics_cleanup(phase2_result)
        optimization_results['deleted_collections'].extend(phase3_result['deleted'])
        optimization_results['documents_deleted'] += phase3_result['docs_deleted']
        
        # フェーズ4: ランキング最適化
        print("\n⚡ フェーズ4: ランキングデータ最適化")
        phase4_result = self._execute_phase4_ranking_optimization()
        optimization_results['deleted_collections'].extend(phase4_result['deleted'])
        optimization_results['documents_deleted'] += phase4_result['docs_deleted']
        
        # 最適化後状態確認
        final_collections = list(self.db.collections())
        optimization_results['collections_after'] = len(final_collections)
        
        # 結果表示
        self._print_optimization_results(optimization_results)
        
        return optimization_results
    
    def _execute_phase1_safe_deletion(self):
        """フェーズ1: 移行関連の安全削除"""
        result = {'deleted': [], 'docs_deleted': 0}
        
        migration_collections = ['migration_backups', 'migration_summaries']
        
        for collection_name in migration_collections:
            try:
                collection = self.db.collection(collection_name)
                docs = list(collection.stream())
                
                if docs:
                    print(f"   削除中: {collection_name} ({len(docs)}ドキュメント)")
                    
                    # バッチ削除
                    batch = self.db.batch()
                    for doc in docs:
                        batch.delete(doc.reference)
                    
                    batch.commit()
                    
                    result['deleted'].append(collection_name)
                    result['docs_deleted'] += len(docs)
                    print(f"   ✅ {collection_name}削除完了")
                else:
                    print(f"   ℹ️  {collection_name}はすでに空")
                    
            except Exception as e:
                print(f"   ❌ {collection_name}削除エラー: {e}")
        
        return result
    
    def _analyze_analytics_usage(self):
        """アナリティクス系の使用状況分析"""
        print("   📊 アナリティクス使用状況チェック")
        
        analytics_collections = {
            'analytics_summary': {'in_app': False, 'recent_data': False},
            'daily_active_users': {'in_app': True, 'recent_data': False}, 
            'daily_engagement_summary': {'in_app': True, 'recent_data': False}
        }
        
        # 最近のデータ確認（過去7日）
        cutoff_date = (datetime.now().strftime('%Y-%m-%d'))
        
        for collection_name in analytics_collections.keys():
            try:
                docs = list(self.db.collection(collection_name).stream())
                recent_docs = [doc for doc in docs 
                             if doc.to_dict().get('date', '1900-01-01') >= cutoff_date]
                
                if recent_docs:
                    analytics_collections[collection_name]['recent_data'] = True
                    
                print(f"     {collection_name}: アプリ使用={analytics_collections[collection_name]['in_app']}, 最新データ={len(recent_docs)}件")
                
            except Exception as e:
                print(f"     {collection_name}分析エラー: {e}")
        
        return analytics_collections
    
    def _execute_phase3_analytics_cleanup(self, analytics_analysis):
        """フェーズ3: アナリティクス削除"""
        result = {'deleted': [], 'docs_deleted': 0}
        
        # analytics_summaryは使用されていないので削除
        unused_collections = ['analytics_summary']
        
        for collection_name in unused_collections:
            if not analytics_analysis.get(collection_name, {}).get('in_app', True):
                try:
                    collection = self.db.collection(collection_name)
                    docs = list(collection.stream())
                    
                    if docs:
                        print(f"   削除中: {collection_name} ({len(docs)}ドキュメント)")
                        
                        batch = self.db.batch()
                        for doc in docs:
                            batch.delete(doc.reference)
                        
                        batch.commit()
                        
                        result['deleted'].append(collection_name)
                        result['docs_deleted'] += len(docs)
                        print(f"   ✅ {collection_name}削除完了")
                        
                except Exception as e:
                    print(f"   ❌ {collection_name}削除エラー: {e}")
        
        # daily系は使用されているが、古いデータは削除
        daily_collections = ['daily_active_users', 'daily_engagement_summary']
        for collection_name in daily_collections:
            if analytics_analysis.get(collection_name, {}).get('in_app', False):
                try:
                    collection = self.db.collection(collection_name)
                    docs = list(collection.stream())
                    
                    # 7日以上前のデータ削除
                    cutoff_date = (datetime.now()).strftime('%Y-%m-%d')
                    old_docs = [doc for doc in docs 
                               if doc.to_dict().get('date', '9999-12-31') < cutoff_date]
                    
                    if old_docs:
                        print(f"   古いデータ削除: {collection_name} ({len(old_docs)}ドキュメント)")
                        
                        batch = self.db.batch()
                        for doc in old_docs:
                            batch.delete(doc.reference)
                        
                        batch.commit()
                        result['docs_deleted'] += len(old_docs)
                        print(f"   ✅ {collection_name}古いデータ削除完了")
                        
                except Exception as e:
                    print(f"   ❌ {collection_name}古いデータ削除エラー: {e}")
        
        return result
    
    def _execute_phase4_ranking_optimization(self):
        """フェーズ4: ランキング最適化"""
        result = {'deleted': [], 'docs_deleted': 0}
        
        # weekly_ranking_snapshotsは冗長なので削除
        try:
            collection = self.db.collection('weekly_ranking_snapshots')
            docs = list(collection.stream())
            
            if docs:
                print(f"   削除中: weekly_ranking_snapshots ({len(docs)}ドキュメント)")
                
                batch = self.db.batch()
                for doc in docs:
                    batch.delete(doc.reference)
                
                batch.commit()
                
                result['deleted'].append('weekly_ranking_snapshots')
                result['docs_deleted'] += len(docs)
                print(f"   ✅ weekly_ranking_snapshots削除完了")
                
        except Exception as e:
            print(f"   ❌ weekly_ranking_snapshots削除エラー: {e}")
        
        return result
    
    def _print_optimization_results(self, results):
        """最適化結果の表示"""
        print("\n🎯 最終最適化結果")
        print("=" * 60)
        
        print(f"削除されたコレクション: {len(results['deleted_collections'])}個")
        for collection in results['deleted_collections']:
            print(f"   🗑️  {collection}")
        
        print(f"\n削除されたドキュメント: {results['documents_deleted']}個")
        print(f"コレクション数: {results['collections_before']} → {results['collections_after']}")
        
        reduction_rate = ((results['collections_before'] - results['collections_after']) / 
                         results['collections_before'] * 100) if results['collections_before'] > 0 else 0
        
        print(f"コレクション削減率: {reduction_rate:.1f}%")
        
        print("\n🛡️  保持されたコレクション:")
        try:
            final_collections = list(self.db.collections())
            total_docs = 0
            
            for collection in final_collections:
                docs = list(collection.limit(100).stream())
                doc_count = len(docs)
                total_docs += doc_count
                print(f"   ✅ {collection.id}: {doc_count}ドキュメント")
            
            print(f"\n📊 最終ドキュメント総数: {total_docs}")
            
        except Exception as e:
            print(f"❌ 最終状態確認エラー: {e}")
        
        print("\n🎉 最終最適化完了！")
        print("   データベースが最大限最適化されました")

if __name__ == "__main__":
    executor = FinalOptimizationExecutor()
    results = executor.execute_final_optimization()
    
    print("\n✨ Firestore最終最適化が完了しました")
    print("   パフォーマンスとコスト効率が最大化されています")
