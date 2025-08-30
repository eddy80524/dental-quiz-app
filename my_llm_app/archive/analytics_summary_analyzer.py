"""
分析関連コレクション詳細分析と最適化提案
"""

import datetime
from typing import Dict, Any, List
from complete_migration_system import CompleteMigrationSystem


class AnalyticsSummaryAnalyzer:
    """分析関連コレクション最適化分析"""
    
    def __init__(self):
        migration_system = CompleteMigrationSystem()
        self.db = migration_system.db
    
    def analyze_analytics_collections(self) -> Dict[str, Any]:
        """分析関連コレクション詳細分析"""
        analysis = {
            "analyzed_at": datetime.datetime.now(),
            "collections": {},
            "redundancy_analysis": {},
            "optimization_recommendations": {}
        }
        
        # 分析対象コレクション
        collections_to_analyze = [
            'analytics_summary',
            'daily_analytics_summary', 
            'weekly_analytics_summary',
            'monthly_analytics_summary',
            'daily_active_users',
            'daily_learning_logs',
            'daily_engagement_summary'
        ]
        
        for collection_name in collections_to_analyze:
            collection_analysis = self._analyze_single_collection(collection_name)
            analysis["collections"][collection_name] = collection_analysis
        
        # 冗長性分析
        analysis["redundancy_analysis"] = self._analyze_redundancy(analysis["collections"])
        
        # 最適化提案
        analysis["optimization_recommendations"] = self._generate_optimization_recommendations(analysis)
        
        return analysis
    
    def _analyze_single_collection(self, collection_name: str) -> Dict[str, Any]:
        """単一コレクションの詳細分析"""
        result = {
            "name": collection_name,
            "exists": False,
            "document_count": 0,
            "sample_data": None,
            "data_structure": [],
            "date_range": {},
            "user_coverage": 0,
            "storage_estimate": 0,
            "necessity_score": 0
        }
        
        try:
            collection_ref = self.db.collection(collection_name)
            docs = list(collection_ref.stream())
            
            if not docs:
                return result
                
            result["exists"] = True
            result["document_count"] = len(docs)
            
            # サンプルデータ分析
            sample_doc = docs[0].to_dict()
            result["sample_data"] = sample_doc
            result["data_structure"] = list(sample_doc.keys())
            
            # 日付範囲分析
            dates = []
            users = set()
            
            for doc in docs:
                data = doc.to_dict()
                
                # 日付情報取得
                if 'date' in data:
                    dates.append(data['date'])
                elif 'timestamp' in data:
                    dates.append(str(data['timestamp'])[:10])
                
                # ユーザー情報取得
                if 'uid' in data:
                    users.add(data['uid'])
                elif 'userId' in data:
                    users.add(data['userId'])
            
            if dates:
                result["date_range"] = {
                    "earliest": min(dates),
                    "latest": max(dates),
                    "span_days": len(set(dates))
                }
            
            result["user_coverage"] = len(users)
            
            # ストレージ見積もり（おおよそ）
            avg_doc_size = len(str(sample_doc)) * 1.5  # JSON + メタデータの見積もり
            result["storage_estimate"] = int(avg_doc_size * len(docs))
            
            # 必要性スコア計算
            result["necessity_score"] = self._calculate_necessity_score(collection_name, result)
            
        except Exception as e:
            result["error"] = str(e)
        
        return result
    
    def _calculate_necessity_score(self, collection_name: str, analysis: Dict[str, Any]) -> int:
        """必要性スコア計算（0-100）"""
        score = 0
        
        # 基本存在スコア
        if analysis["exists"]:
            score += 20
        
        # データ量スコア
        doc_count = analysis["document_count"]
        if doc_count > 100:
            score += 30
        elif doc_count > 10:
            score += 20
        elif doc_count > 0:
            score += 10
        
        # 最新性スコア
        if analysis["date_range"]:
            latest_date = analysis["date_range"].get("latest", "")
            if latest_date >= "2025-08-25":  # 最近4日以内
                score += 25
            elif latest_date >= "2025-08-20":  # 最近9日以内
                score += 15
            elif latest_date >= "2025-08-01":  # 今月
                score += 5
        
        # ユーザーカバレッジスコア
        user_count = analysis["user_coverage"]
        if user_count > 10:
            score += 15
        elif user_count > 5:
            score += 10
        elif user_count > 0:
            score += 5
        
        # コレクション固有の重要度
        if collection_name in ['analytics_summary']:
            score += 10  # 主要な分析データ
        elif collection_name in ['daily_active_users', 'daily_learning_logs']:
            score += 5   # 有用だが代替可能
        
        return min(score, 100)
    
    def _analyze_redundancy(self, collections: Dict[str, Any]) -> Dict[str, Any]:
        """冗長性分析"""
        redundancy = {
            "duplicate_data": [],
            "overlapping_metrics": [],
            "consolidation_opportunities": []
        }
        
        # 存在するコレクション
        existing_collections = {name: data for name, data in collections.items() 
                              if data.get("exists", False)}
        
        # 重複データ検出
        for name1, data1 in existing_collections.items():
            for name2, data2 in existing_collections.items():
                if name1 < name2:  # 重複チェック回避
                    fields1 = set(data1.get("data_structure", []))
                    fields2 = set(data2.get("data_structure", []))
                    
                    overlap = fields1.intersection(fields2)
                    if len(overlap) > 2:  # 2つ以上の共通フィールド
                        redundancy["overlapping_metrics"].append({
                            "collections": [name1, name2],
                            "overlapping_fields": list(overlap),
                            "overlap_percentage": len(overlap) / max(len(fields1), len(fields2)) * 100
                        })
        
        # 統合機会の特定
        daily_collections = [name for name in existing_collections.keys() if 'daily' in name]
        if len(daily_collections) > 1:
            redundancy["consolidation_opportunities"].append({
                "type": "daily_collections_merge",
                "collections": daily_collections,
                "benefit": "統一された日次分析データ構造"
            })
        
        return redundancy
    
    def _generate_optimization_recommendations(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """最適化推奨事項生成"""
        recommendations = {
            "immediate_actions": [],
            "consolidation_plan": [],
            "cost_savings": {},
            "migration_to_optimized": []
        }
        
        collections = analysis["collections"]
        
        # 即座削除推奨
        for name, data in collections.items():
            if data.get("exists", False):
                necessity_score = data.get("necessity_score", 0)
                doc_count = data.get("document_count", 0)
                
                if necessity_score < 30:
                    recommendations["immediate_actions"].append({
                        "action": "delete",
                        "collection": name,
                        "reason": f"必要性スコア低い({necessity_score}/100)",
                        "savings": f"{doc_count}ドキュメント削除"
                    })
                elif necessity_score < 60:
                    recommendations["immediate_actions"].append({
                        "action": "review",
                        "collection": name,
                        "reason": f"必要性要検討({necessity_score}/100)",
                        "suggestion": "代替手段との比較検討"
                    })
        
        # 最適化システムへの移行推奨
        existing_collections = [name for name, data in collections.items() if data.get("exists")]
        if existing_collections:
            recommendations["migration_to_optimized"] = [
                {
                    "target": "users.stats統合",
                    "source_collections": existing_collections,
                    "benefit": "単一の最適化統計データ構造",
                    "implementation": "enhanced_firestore_optimizerのstats機能活用"
                },
                {
                    "target": "weekly_rankings活用",
                    "source_collections": [c for c in existing_collections if 'daily' in c or 'weekly' in c],
                    "benefit": "事前計算済みランキングデータ",
                    "implementation": "OptimizedWeeklyRankingSystemの機能拡張"
                }
            ]
        
        # コスト削減見積もり
        total_docs = sum(data.get("document_count", 0) for data in collections.values() if data.get("exists"))
        total_storage = sum(data.get("storage_estimate", 0) for data in collections.values() if data.get("exists"))
        
        recommendations["cost_savings"] = {
            "documents_removable": total_docs,
            "storage_savings_bytes": total_storage,
            "monthly_read_cost_reduction": f"${total_docs * 0.0000006:.4f}",  # Firestore読み取りコスト概算
            "monthly_write_cost_reduction": f"${total_docs * 0.0000018:.4f}"   # Firestore書き込みコスト概算
        }
        
        return recommendations
    
    def generate_cleanup_script(self, analysis: Dict[str, Any]) -> List[str]:
        """クリーンアップスクリプト生成"""
        recommendations = analysis["optimization_recommendations"]
        
        commands = [
            "#!/bin/bash",
            "# =====================================",
            "# 分析関連コレクション最適化スクリプト",
            "# =====================================",
            "",
            "echo '🔍 分析関連コレクション最適化開始'",
            "",
            "# 1. バックアップ作成",
            "python -c \"",
            "from complete_migration_system import CompleteMigrationSystem",
            "migration = CompleteMigrationSystem()",
            "backup_id = migration.backup_existing_data()",
            "print(f'📦 バックアップ完了: {backup_id}')",
            "\"",
            ""
        ]
        
        # 削除対象コレクション処理
        delete_actions = [action for action in recommendations["immediate_actions"] 
                         if action["action"] == "delete"]
        
        if delete_actions:
            commands.extend([
                "# 2. 低必要性コレクション削除",
                "python -c \"",
                "from complete_migration_system import CompleteMigrationSystem",
                "migration = CompleteMigrationSystem()",
                "db = migration.db",
                ""
            ])
            
            for action in delete_actions:
                collection = action["collection"]
                commands.extend([
                    f"# {collection}削除",
                    f"docs = list(db.collection('{collection}').stream())",
                    f"print(f'🗑️ 削除対象: {collection} {{len(docs)}}件')",
                    "for doc in docs:",
                    "    doc.reference.delete()",
                    f"print(f'✅ {collection}削除完了')",
                    ""
                ])
            
            commands.extend(["\"\n"])
        
        # 検証スクリプト
        commands.extend([
            "# 3. 削除後確認",
            "python -c \"",
            "from complete_migration_system import CompleteMigrationSystem",
            "migration = CompleteMigrationSystem()",
            "db = migration.db",
            "",
            "collections_to_check = [" + 
            ", ".join([f"'{action['collection']}'" for action in delete_actions]) + "]",
            "",
            "for collection_name in collections_to_check:",
            "    remaining = list(db.collection(collection_name).limit(1).stream())",
            "    if remaining:",
            "        print(f'⚠️ {collection_name}: まだデータが残っています')",
            "    else:",
            "        print(f'✅ {collection_name}: 削除完了確認')",
            "\"",
            "",
            "echo '🎉 分析関連コレクション最適化完了'"
        ])
        
        return commands


def main():
    """メイン分析実行"""
    analyzer = AnalyticsSummaryAnalyzer()
    
    print("📊 分析関連コレクション詳細分析")
    print("=" * 60)
    
    # 詳細分析実行
    analysis = analyzer.analyze_analytics_collections()
    
    print(f"\n📋 コレクション別詳細分析:")
    for name, data in analysis["collections"].items():
        if data.get("exists", False):
            print(f"\n✅ {name}:")
            print(f"   ドキュメント数: {data['document_count']}件")
            print(f"   ユーザーカバレッジ: {data['user_coverage']}名")
            print(f"   必要性スコア: {data['necessity_score']}/100")
            if data.get("date_range"):
                date_range = data["date_range"]
                print(f"   データ期間: {date_range['earliest']} ～ {date_range['latest']} ({date_range['span_days']}日間)")
            print(f"   データ構造: {data['data_structure'][:3]}..." if len(data['data_structure']) > 3 else f"   データ構造: {data['data_structure']}")
        else:
            print(f"\n❌ {name}: 存在しない")
    
    print(f"\n🔄 冗長性分析:")
    redundancy = analysis["redundancy_analysis"]
    
    if redundancy["overlapping_metrics"]:
        print("重複メトリクス:")
        for overlap in redundancy["overlapping_metrics"]:
            collections = " & ".join(overlap["collections"])
            print(f"   {collections}: {overlap['overlap_percentage']:.1f}%重複")
            print(f"   共通フィールド: {overlap['overlapping_fields']}")
    else:
        print("重複メトリクス: なし")
    
    if redundancy["consolidation_opportunities"]:
        print("統合機会:")
        for opportunity in redundancy["consolidation_opportunities"]:
            print(f"   {opportunity['type']}: {opportunity['collections']}")
            print(f"   効果: {opportunity['benefit']}")
    
    print(f"\n💡 最適化推奨事項:")
    recommendations = analysis["optimization_recommendations"]
    
    print("即座対応:")
    for action in recommendations["immediate_actions"]:
        action_icon = "🗑️" if action["action"] == "delete" else "🔍"
        print(f"   {action_icon} {action['collection']}: {action['reason']}")
    
    print(f"\n💰 コスト削減効果:")
    savings = recommendations["cost_savings"]
    print(f"   削除可能ドキュメント: {savings['documents_removable']}件")
    print(f"   ストレージ削減: {savings['storage_savings_bytes']:,}バイト")
    print(f"   月次読み取りコスト削減: {savings['monthly_read_cost_reduction']}")
    print(f"   月次書き込みコスト削減: {savings['monthly_write_cost_reduction']}")
    
    print(f"\n🚀 最適化システム移行推奨:")
    for migration in recommendations["migration_to_optimized"]:
        print(f"   {migration['target']}: {migration['benefit']}")
        print(f"   対象: {migration['source_collections']}")
        print(f"   実装: {migration['implementation']}")
        print()
    
    # クリーンアップスクリプト生成
    script = analyzer.generate_cleanup_script(analysis)
    
    with open("/tmp/cleanup_analytics_collections.sh", "w", encoding="utf-8") as f:
        f.write("\n".join(script))
    
    print(f"🗂️ クリーンアップスクリプトを /tmp/cleanup_analytics_collections.sh に保存しました")
    
    # 総合推奨事項
    delete_count = len([a for a in recommendations["immediate_actions"] if a["action"] == "delete"])
    review_count = len([a for a in recommendations["immediate_actions"] if a["action"] == "review"])
    
    print(f"\n🎯 総合推奨:")
    print(f"   即座削除推奨: {delete_count}コレクション")
    print(f"   要検討: {review_count}コレクション") 
    print(f"   最適化システム統合により、分析機能を効率化")


if __name__ == "__main__":
    main()
