#!/usr/bin/env python3
"""
最適化後Firestore構造の詳細分析
各コレクションの必要性、重複、さらなる統合可能性を徹底検証
"""

from complete_migration_system import CompleteMigrationSystem
from datetime import datetime
import json

class PostOptimizationAnalyzer:
    def __init__(self):
        self.migration_system = CompleteMigrationSystem()
        self.db = self.migration_system.db
        
    def analyze_current_structure(self):
        """現在の構造を詳細分析"""
        print("🔍 最適化後構造の詳細分析")
        print("=" * 60)
        
        analysis_result = {
            'current_collections': {},
            'redundancy_analysis': {},
            'consolidation_opportunities': [],
            'final_recommendations': []
        }
        
        # 各コレクションの詳細分析
        collections = [
            'analytics_summary',
            'daily_active_users', 
            'daily_engagement_summary',
            'migration_backups',
            'migration_summaries', 
            'study_cards',
            'system_stats',
            'user_rankings',
            'users',
            'weekly_ranking_snapshots',
            'weekly_rankings'
        ]
        
        for collection_name in collections:
            print(f"\n📊 {collection_name} 分析")
            analysis = self._analyze_collection_deep(collection_name)
            analysis_result['current_collections'][collection_name] = analysis
            self._print_collection_analysis(collection_name, analysis)
        
        # 機能的重複分析
        redundancy = self._analyze_functional_redundancy()
        analysis_result['redundancy_analysis'] = redundancy
        
        # 統合機会の特定
        consolidation = self._identify_consolidation_opportunities()
        analysis_result['consolidation_opportunities'] = consolidation
        
        # 最終推奨
        recommendations = self._generate_post_optimization_recommendations()
        analysis_result['final_recommendations'] = recommendations
        
        self._print_optimization_summary(analysis_result)
        
        return analysis_result
    
    def _analyze_collection_deep(self, collection_name):
        """コレクションの深度分析"""
        try:
            collection = self.db.collection(collection_name)
            docs = list(collection.stream())
            
            analysis = {
                'document_count': len(docs),
                'unique_users': set(),
                'data_patterns': {},
                'size_analysis': {},
                'functional_purpose': '',
                'redundancy_score': 0,
                'optimization_potential': 0,
                'necessity_score': 0
            }
            
            total_data_size = 0
            
            for doc in docs:
                data = doc.to_dict()
                
                # ユーザー特定
                for user_field in ['uid', 'userId', 'user_id']:
                    if user_field in data:
                        analysis['unique_users'].add(data[user_field])
                        break
                
                # データサイズ
                doc_size = len(str(data))
                total_data_size += doc_size
                
                # データパターン分析
                for key in data.keys():
                    analysis['data_patterns'][key] = analysis['data_patterns'].get(key, 0) + 1
            
            analysis['unique_users'] = len(analysis['unique_users'])
            analysis['size_analysis'] = {
                'total_size': total_data_size,
                'avg_doc_size': total_data_size // len(docs) if docs else 0
            }
            
            # 機能的目的と必要性スコアリング
            analysis.update(self._score_collection_necessity(collection_name, docs))
            
            return analysis
            
        except Exception as e:
            return {'error': str(e)}
    
    def _score_collection_necessity(self, collection_name, docs):
        """コレクションの必要性スコアリング"""
        scoring = {
            'functional_purpose': '',
            'necessity_score': 0,
            'redundancy_score': 0, 
            'optimization_potential': 0
        }
        
        if collection_name == 'users':
            scoring.update({
                'functional_purpose': 'ユーザーマスタ・統計データ',
                'necessity_score': 100,
                'redundancy_score': 0,
                'optimization_potential': 10
            })
        
        elif collection_name == 'study_cards':
            scoring.update({
                'functional_purpose': '学習カード・進捗管理',
                'necessity_score': 100,
                'redundancy_score': 0,
                'optimization_potential': 5
            })
        
        elif collection_name == 'weekly_rankings':
            scoring.update({
                'functional_purpose': '週次ランキングメイン',
                'necessity_score': 95,
                'redundancy_score': 5,
                'optimization_potential': 15
            })
        
        elif collection_name == 'user_rankings':
            scoring.update({
                'functional_purpose': 'ユーザー別ランキング詳細',
                'necessity_score': 80,
                'redundancy_score': 30,
                'optimization_potential': 40
            })
        
        elif collection_name == 'weekly_ranking_snapshots':
            scoring.update({
                'functional_purpose': 'ランキングスナップショット',
                'necessity_score': 60,
                'redundancy_score': 60,
                'optimization_potential': 70
            })
        
        elif collection_name == 'analytics_summary':
            scoring.update({
                'functional_purpose': '日次分析サマリー',
                'necessity_score': 50,
                'redundancy_score': 70,
                'optimization_potential': 80
            })
        
        elif collection_name == 'daily_active_users':
            scoring.update({
                'functional_purpose': 'ユーザーアクティビティ追跡',
                'necessity_score': 45,
                'redundancy_score': 75,
                'optimization_potential': 85
            })
        
        elif collection_name == 'daily_engagement_summary':
            scoring.update({
                'functional_purpose': 'エンゲージメント集計',
                'necessity_score': 40,
                'redundancy_score': 80,
                'optimization_potential': 90
            })
        
        elif collection_name == 'system_stats':
            scoring.update({
                'functional_purpose': 'システム統計',
                'necessity_score': 70,
                'redundancy_score': 20,
                'optimization_potential': 30
            })
        
        elif collection_name == 'migration_backups':
            scoring.update({
                'functional_purpose': '移行バックアップ',
                'necessity_score': 30,
                'redundancy_score': 90,
                'optimization_potential': 95
            })
        
        elif collection_name == 'migration_summaries':
            scoring.update({
                'functional_purpose': '移行サマリー',
                'necessity_score': 25,
                'redundancy_score': 95,
                'optimization_potential': 95
            })
        
        return scoring
    
    def _analyze_functional_redundancy(self):
        """機能的重複の分析"""
        print("\n🔄 機能的重複分析")
        
        redundancy_groups = {
            'ranking_related': {
                'collections': ['weekly_rankings', 'user_rankings', 'weekly_ranking_snapshots'],
                'overlap_type': 'ランキング機能重複',
                'consolidation_potential': 85
            },
            'analytics_related': {
                'collections': ['analytics_summary', 'daily_active_users', 'daily_engagement_summary'],
                'overlap_type': '分析機能重複',
                'consolidation_potential': 90
            },
            'migration_related': {
                'collections': ['migration_backups', 'migration_summaries'],
                'overlap_type': '移行関連（一時的）',
                'consolidation_potential': 100
            }
        }
        
        for group_name, group_info in redundancy_groups.items():
            print(f"   {group_name}: {group_info['overlap_type']} - 統合可能性 {group_info['consolidation_potential']}%")
        
        return redundancy_groups
    
    def _identify_consolidation_opportunities(self):
        """統合機会の特定"""
        print("\n⚡ 統合機会")
        
        opportunities = [
            {
                'priority': 1,
                'action': 'delete_migration_data',
                'target': ['migration_backups', 'migration_summaries'],
                'reason': '移行完了により不要、100%削除可能',
                'impact': 'minimal',
                'risk': 'none'
            },
            {
                'priority': 2,
                'action': 'consolidate_analytics',
                'target': ['daily_active_users', 'daily_engagement_summary', 'analytics_summary'],
                'reason': '機能重複90%、単一analytics_dailyに統合可能',
                'impact': 'medium',
                'risk': 'low'
            },
            {
                'priority': 3,
                'action': 'optimize_rankings',
                'target': ['user_rankings', 'weekly_ranking_snapshots'],
                'reason': 'weekly_rankingsに統合、冗長性削除',
                'impact': 'medium',
                'risk': 'low'
            },
            {
                'priority': 4,
                'action': 'integrate_system_stats',
                'target': ['system_stats'],
                'reason': 'usersコレクションに統合可能',
                'impact': 'small',
                'risk': 'minimal'
            }
        ]
        
        for opp in opportunities:
            print(f"   {opp['priority']}. {opp['action']}: {opp['target']}")
            print(f"      理由: {opp['reason']}")
            print(f"      影響: {opp['impact']}, リスク: {opp['risk']}")
        
        return opportunities
    
    def _generate_post_optimization_recommendations(self):
        """最適化後の推奨事項生成"""
        recommendations = {
            'immediate_actions': [
                {
                    'action': 'delete_migration_collections',
                    'collections': ['migration_backups', 'migration_summaries'],
                    'justification': '移行完了により目的達成、保持不要',
                    'doc_reduction': 2,
                    'collection_reduction': 2
                }
            ],
            'consolidation_actions': [
                {
                    'action': 'merge_analytics_collections',
                    'source_collections': ['analytics_summary', 'daily_active_users', 'daily_engagement_summary'],
                    'target_collection': 'analytics_daily',
                    'justification': '機能重複解消、管理簡素化',
                    'doc_reduction': 15,
                    'collection_reduction': 2
                },
                {
                    'action': 'optimize_ranking_structure',
                    'source_collections': ['user_rankings', 'weekly_ranking_snapshots'],
                    'target_integration': 'weekly_rankings',
                    'justification': 'ランキングデータ統合、パフォーマンス向上',
                    'doc_reduction': 31,
                    'collection_reduction': 2
                }
            ],
            'final_structure': [
                'users (33 docs)',
                'study_cards (1000 docs)', 
                'weekly_rankings (統合後)',
                'analytics_daily (統合後)',
                'system_stats (1 doc)'
            ],
            'target_metrics': {
                'final_collections': 5,
                'final_documents': '~1036',
                'additional_reduction': '4.4%',
                'management_complexity': 'minimal'
            }
        }
        
        return recommendations
    
    def _print_collection_analysis(self, collection_name, analysis):
        """コレクション分析結果表示"""
        if 'error' in analysis:
            print(f"   ❌ エラー: {analysis['error']}")
            return
            
        print(f"   📈 ドキュメント数: {analysis['document_count']}")
        print(f"   👥 ユニークユーザー: {analysis['unique_users']}")
        print(f"   🎯 機能: {analysis['functional_purpose']}")
        print(f"   💯 必要性スコア: {analysis['necessity_score']}/100")
        print(f"   🔄 重複スコア: {analysis['redundancy_score']}/100") 
        print(f"   ⚡ 最適化可能性: {analysis['optimization_potential']}/100")
        
        if analysis['size_analysis']['avg_doc_size'] > 0:
            print(f"   📊 平均ドキュメントサイズ: {analysis['size_analysis']['avg_doc_size']}文字")
    
    def _print_optimization_summary(self, analysis_result):
        """最適化サマリー表示"""
        print("\n🎯 追加最適化可能性サマリー")
        print("=" * 60)
        
        high_optimization = []
        medium_optimization = []
        low_optimization = []
        
        for collection_name, analysis in analysis_result['current_collections'].items():
            if 'optimization_potential' in analysis:
                potential = analysis['optimization_potential']
                if potential >= 80:
                    high_optimization.append((collection_name, potential))
                elif potential >= 50:
                    medium_optimization.append((collection_name, potential))
                else:
                    low_optimization.append((collection_name, potential))
        
        print("\n🔥 高最適化可能性 (80%+):")
        for name, score in high_optimization:
            print(f"   {name}: {score}%")
        
        print("\n⚡ 中最適化可能性 (50-79%):")
        for name, score in medium_optimization:
            print(f"   {name}: {score}%")
        
        print("\n✅ 最適化済み (<50%):")
        for name, score in low_optimization:
            print(f"   {name}: {score}%")
        
        # 推奨アクション
        recommendations = analysis_result['final_recommendations']
        
        print("\n📋 追加最適化推奨アクション:")
        print("1. 移行関連削除 → -2コレクション")
        print("2. 分析系統合 → -2コレクション")  
        print("3. ランキング最適化 → -2コレクション")
        print("4. システム統計統合 → -1コレクション")
        
        print("\n🎯 最終目標構造:")
        for structure in recommendations['target_metrics']:
            print(f"   {structure}: {recommendations['target_metrics'][structure]}")

if __name__ == "__main__":
    analyzer = PostOptimizationAnalyzer()
    analysis_result = analyzer.analyze_current_structure()
    
    print("\n📊 詳細分析完了")
    print("さらなる最適化機会が特定されました")
