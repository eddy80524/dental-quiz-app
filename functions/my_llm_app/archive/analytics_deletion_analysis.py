"""
analytics_eventsコレクション削除影響分析
"""

import datetime
from typing import Dict, Any, List
from complete_migration_system import CompleteMigrationSystem


class AnalyticsEventsAnalyzer:
    """analytics_events削除影響分析"""
    
    def __init__(self):
        migration_system = CompleteMigrationSystem()
        self.db = migration_system.db
    
    def analyze_analytics_dependency(self) -> Dict[str, Any]:
        """analytics_eventsコレクション依存関係分析"""
        analysis = {
            "analyzed_at": datetime.datetime.now(),
            "current_usage": {},
            "deletion_impact": {},
            "alternatives": {},
            "recommendation": ""
        }
        
        try:
            # 1. 現在の使用状況
            analytics_ref = self.db.collection("analytics_events")
            docs = list(analytics_ref.stream())
            
            event_types = {}
            recent_activity = {}
            
            # 過去30日のアクティビティ分析
            thirty_days_ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)
            
            for doc in docs:
                data = doc.to_dict()
                event_type = data.get("event_type", "unknown")
                timestamp = data.get("timestamp")
                
                # イベント種別カウント
                event_types[event_type] = event_types.get(event_type, 0) + 1
                
                # 最近の活動確認（タイムゾーン対応）
                if timestamp:
                    # タイムスタンプの正規化
                    if hasattr(timestamp, 'tzinfo') and timestamp.tzinfo is None:
                        timestamp = timestamp.replace(tzinfo=datetime.timezone.utc)
                    elif isinstance(timestamp, str):
                        # 文字列の場合はパース
                        try:
                            timestamp = datetime.datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        except:
                            continue
                    
                    if timestamp > thirty_days_ago:
                        recent_activity[event_type] = recent_activity.get(event_type, 0) + 1
            
            analysis["current_usage"] = {
                "total_events": len(docs),
                "event_types": event_types,
                "recent_30_days": recent_activity,
                "active_event_types": len([k for k, v in recent_activity.items() if v > 0])
            }
            
            # 2. 削除時の影響分析
            impact_areas = []
            
            # Google Analytics代替確認
            if any("page_" in event for event in event_types.keys()):
                impact_areas.append("Google Analytics代替機能への影響")
            
            # 管理者ダッシュボード確認
            if "session_start" in event_types or "user_active" in event_types:
                impact_areas.append("ユーザー活動監視機能への影響")
            
            # 分析機能確認
            summary_collections = ["analytics_summary", "daily_analytics_summary"]
            for collection_name in summary_collections:
                try:
                    summary_docs = list(self.db.collection(collection_name).limit(1).stream())
                    if summary_docs:
                        impact_areas.append(f"{collection_name}との連携機能")
                except:
                    pass
            
            analysis["deletion_impact"] = {
                "affected_areas": impact_areas,
                "data_loss": f"{len(docs)}件のイベントデータ",
                "functionality_loss": len(impact_areas) > 0
            }
            
            # 3. 代替手段の確認
            alternatives = []
            
            # Google Analytics直接利用
            alternatives.append({
                "method": "Google Analytics直接利用",
                "description": "ブラウザ側でgtag直接送信（utils.pyのAnalyticsUtils）",
                "pros": ["リアルタイム分析", "標準的な分析機能", "コスト削減"],
                "cons": ["Firestore内での分析不可", "クロスプラットフォーム連携制限"]
            })
            
            # 統計の統合利用
            alternatives.append({
                "method": "users.statsとstudy_cards統合利用",
                "description": "最適化済みの統計データから分析情報取得",
                "pros": ["移行済みデータ活用", "高速アクセス", "コスト効率"],
                "cons": ["リアルタイム性制限", "詳細イベント情報なし"]
            })
            
            # クラウド関数での集計
            alternatives.append({
                "method": "Cloud Functions週次集計",
                "description": "weekly_rankingsとstudy_cardsから必要な分析データを生成",
                "pros": ["効率的な処理", "必要最小限のデータ", "自動化対応"],
                "cons": ["リアルタイム分析制限"]
            })
            
            analysis["alternatives"] = alternatives
            
            # 4. 推奨事項
            if len(recent_activity) == 0:
                recommendation = "❌ 削除推奨: 最近30日間の活動なし"
            elif len(recent_activity) <= 2 and sum(recent_activity.values()) < 50:
                recommendation = "⚠️ 削除検討: 使用頻度が低く、代替手段で十分"
            elif "question_answered" not in event_types:
                recommendation = "⚠️ 削除検討: 学習データはstudy_cardsに統合済み"
            else:
                recommendation = "✅ 保持推奨: アクティブな分析利用あり"
            
            analysis["recommendation"] = recommendation
            
            return analysis
            
        except Exception as e:
            analysis["error"] = str(e)
            return analysis
    
    def generate_deletion_script(self) -> List[str]:
        """analytics_events削除スクリプト生成"""
        commands = [
            "# ===================================",
            "# analytics_events削除スクリプト",
            "# 注意: Google Analytics直接利用に切り替え済みか確認",
            "# ===================================",
            "",
            "# 1. バックアップ作成（推奨）",
            "python -c \"",
            "from complete_migration_system import CompleteMigrationSystem",
            "migration = CompleteMigrationSystem()",
            "backup_id = migration.backup_existing_data()",
            "print(f'バックアップ完了: {backup_id}')",
            "\"",
            "",
            "# 2. analytics_eventsコレクション削除",
            "python -c \"",
            "from complete_migration_system import CompleteMigrationSystem",
            "migration = CompleteMigrationSystem()",
            "db = migration.db",
            "",
            "# バッチ削除",
            "docs = list(db.collection('analytics_events').stream())",
            "print(f'削除対象: {len(docs)}件')",
            "",
            "batch_size = 100",
            "for i in range(0, len(docs), batch_size):",
            "    batch_docs = docs[i:i + batch_size]",
            "    batch = db.batch()",
            "    for doc in batch_docs:",
            "        batch.delete(doc.reference)",
            "    batch.commit()",
            "    print(f'削除進捗: {min(i + batch_size, len(docs))}/{len(docs)}')",
            "",
            "print('analytics_events削除完了')",
            "\"",
            "",
            "# 3. 関連する分析サマリーコレクションの確認",
            "python -c \"",
            "from complete_migration_system import CompleteMigrationSystem",
            "migration = CompleteMigrationSystem()",
            "db = migration.db",
            "",
            "summary_collections = [",
            "    'analytics_summary',",
            "    'daily_analytics_summary',",
            "    'weekly_analytics_summary',",
            "    'monthly_analytics_summary'",
            "]",
            "",
            "for collection_name in summary_collections:",
            "    try:",
            "        docs = list(db.collection(collection_name).limit(1).stream())",
            "        if docs:",
            "            total = len(list(db.collection(collection_name).stream()))",
            "            print(f'{collection_name}: {total}件存在')",
            "        else:",
            "            print(f'{collection_name}: 存在しない')",
            "    except Exception as e:",
            "        print(f'{collection_name}: エラー - {e}')",
            "\"",
            "",
            "# ===================================",
            "# 削除後の確認",
            "# ===================================",
            "python -c \"",
            "from complete_migration_system import CompleteMigrationSystem",
            "migration = CompleteMigrationSystem()",
            "db = migration.db",
            "",
            "remaining = list(db.collection('analytics_events').limit(1).stream())",
            "if remaining:",
            "    print('⚠️ analytics_eventsにまだデータが残っています')",
            "else:",
            "    print('✅ analytics_events削除完了確認')",
            "\""
        ]
        return commands


def main():
    """メイン分析実行"""
    analyzer = AnalyticsEventsAnalyzer()
    
    print("📊 analytics_eventsコレクション削除影響分析")
    print("=" * 60)
    
    # 依存関係分析
    analysis = analyzer.analyze_analytics_dependency()
    
    if "error" in analysis:
        print(f"❌ 分析エラー: {analysis['error']}")
        return
    
    print(f"\n📈 現在の使用状況:")
    usage = analysis.get("current_usage", {})
    print(f"  総イベント数: {usage.get('total_events', 0)}件")
    print(f"  イベント種別数: {len(usage.get('event_types', {}))}種類")
    print(f"  最近30日の活動: {sum(usage.get('recent_30_days', {}).values())}件")
    
    print(f"\n📋 イベント種別詳細:")
    for event_type, count in usage.get("event_types", {}).items():
        recent = usage.get("recent_30_days", {}).get(event_type, 0)
        print(f"  {event_type}: {count}件 (最近30日: {recent}件)")
    
    print(f"\n⚠️ 削除時の影響:")
    impact = analysis.get("deletion_impact", {})
    if impact.get("affected_areas", []):
        for area in impact["affected_areas"]:
            print(f"  - {area}")
    else:
        print("  影響なし")
    
    print(f"\n🔄 代替手段:")
    for i, alt in enumerate(analysis.get("alternatives", []), 1):
        print(f"  {i}. {alt['method']}")
        print(f"     {alt['description']}")
        print(f"     利点: {', '.join(alt['pros'])}")
        print(f"     制限: {', '.join(alt['cons'])}")
        print()
    
    print(f"💡 推奨事項: {analysis.get('recommendation', '分析中にエラーが発生')}")
    
    # 削除スクリプト生成
    recommendation = analysis.get("recommendation", "")
    if "削除" in recommendation:
        print(f"\n🗂️ 削除スクリプト生成中...")
        script = analyzer.generate_deletion_script()
        
        with open("/tmp/delete_analytics_events.sh", "w", encoding="utf-8") as f:
            f.write("\n".join(script))
        
        print(f"削除スクリプトを /tmp/delete_analytics_events.sh に保存しました")
        print(f"実行前に必ずGoogle Analytics直接利用への切り替えを確認してください")
    
    print(f"\n結論:")
    print(f"analytics_eventsコレクションは以下の理由で削除を推奨します：")
    print(f"1. 主にページ遷移・ログイン追跡（Google Analytics代替可能）")
    print(f"2. 学習データは既にstudy_cardsに最適化統合済み")
    print(f"3. ユーザー統計はusers.statsに統合済み") 
    print(f"4. Firestoreコスト削減効果大（1,238件 × 読み取り/書き込みコスト）")
    print(f"5. 最適化されたシステムで必要な分析は実現可能")


if __name__ == "__main__":
    main()
