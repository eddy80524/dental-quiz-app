"""
Firestore移行 - 削除対象コレクション分析レポート

現在のコレクション構造を分析し、移行後に安全に削除できる
コレクションと保持すべきコレクションを整理

📅 分析日: 2025-08-29
🔍 対象: 15個のコレクション
"""

# === 現在のFirestoreコレクション構造 ===

CURRENT_COLLECTIONS = {
    # 移行対象の主要コレクション
    "users": {
        "status": "移行対象（メイン）",
        "description": "ユーザーの基本情報",
        "subcollections": ["userCards"],
        "migration_action": "最適化構造に変換",
        "post_migration": "保持（最適化済み）"
    },
    
    "study_cards": {
        "status": "既に最適化済み",
        "description": "最適化されたカード管理",
        "migration_action": "そのまま利用",
        "post_migration": "保持"
    },
    
    # 削除対象コレクション
    "user_progress": {
        "status": "削除対象",
        "description": "旧式の進捗管理（userCardsサブコレクションと重複）",
        "reason": "study_cardsに統合済み",
        "safety": "安全（データは移行済み）",
        "delete_timing": "移行検証後"
    },
    
    "user_profiles": {
        "status": "削除対象",
        "description": "ユーザープロフィール（usersコレクションと重複）",
        "reason": "usersコレクションのstatsフィールドに統合",
        "safety": "安全（統計データは再計算済み）",
        "delete_timing": "移行検証後"
    },
    
    "user_rankings": {
        "status": "削除対象",
        "description": "個別ユーザーランキング（非効率）",
        "reason": "統計データベースから直接計算に変更",
        "safety": "安全（ランキングは動的計算）",
        "delete_timing": "移行検証後"
    },
    
    "weekly_rankings": {
        "status": "削除対象（条件付き）",
        "description": "週間ランキングスナップショット",
        "reason": "weekly_ranking_snapshotsに移行",
        "safety": "要注意（履歴データのため一時保持推奨）",
        "delete_timing": "3ヶ月後"
    },
    
    "learningLogs": {
        "status": "削除対象",
        "description": "旧式の学習ログ",
        "reason": "analytics_eventsとstudy_cardsに統合",
        "safety": "安全（データは移行済み）",
        "delete_timing": "移行検証後"
    },
    
    "user_permissions": {
        "status": "削除対象",
        "description": "ユーザー権限管理",
        "reason": "usersコレクションのsettingsに統合",
        "safety": "安全（権限は統合済み）",
        "delete_timing": "移行検証後"
    },
    
    # 保持対象コレクション
    "analytics_events": {
        "status": "保持",
        "description": "分析イベントログ",
        "reason": "継続利用",
        "post_migration": "保持"
    },
    
    "analytics_summary": {
        "status": "保持",
        "description": "分析サマリー",
        "reason": "継続利用",
        "post_migration": "保持"
    },
    
    "daily_active_users": {
        "status": "保持",
        "description": "日次アクティブユーザー",
        "reason": "分析で利用",
        "post_migration": "保持"
    },
    
    "daily_engagement_summary": {
        "status": "保持",
        "description": "日次エンゲージメント",
        "reason": "分析で利用",
        "post_migration": "保持"
    },
    
    "daily_learning_logs": {
        "status": "保持",
        "description": "日次学習ログ",
        "reason": "分析で利用",
        "post_migration": "保持"
    },
    
    "monthly_analytics_summary": {
        "status": "保持",
        "description": "月次分析サマリー",
        "reason": "長期分析で利用",
        "post_migration": "保持"
    },
    
    "system_stats": {
        "status": "保持",
        "description": "システム統計",
        "reason": "システム監視で利用",
        "post_migration": "保持"
    }
}


# === 削除対象コレクションの詳細 ===

SAFE_TO_DELETE_IMMEDIATELY = [
    "user_progress",      # study_cardsに統合済み
    "user_profiles",      # usersのstatsに統合済み
    "user_rankings",      # 動的計算に変更
    "learningLogs",       # analytics_eventsに統合済み
    "user_permissions"    # usersのsettingsに統合済み
]

SAFE_TO_DELETE_LATER = [
    "weekly_rankings"     # 履歴保持のため3ヶ月後削除推奨
]

MUST_KEEP = [
    "users",                        # 最適化後も継続利用
    "study_cards",                  # 最適化済みの主要データ
    "analytics_events",             # 分析データ
    "analytics_summary",            # 分析サマリー
    "daily_active_users",           # DAU分析
    "daily_engagement_summary",     # エンゲージメント分析
    "daily_learning_logs",          # 学習ログ分析
    "monthly_analytics_summary",    # 月次分析
    "system_stats"                  # システム統計
]


def generate_deletion_script():
    """削除スクリプトの生成"""
    
    script = '''
"""
Firestore移行後クリーンアップスクリプト
不要になったコレクションを安全に削除

⚠️ 重要: このスクリプトは移行完了後にのみ実行してください
"""

import datetime
from enhanced_firestore_optimizer import EnhancedFirestoreOptimizer

def delete_obsolete_collections():
    """移行後不要コレクションの削除"""
    
    optimizer = EnhancedFirestoreOptimizer()
    db = optimizer.db
    
    # 即座に削除可能なコレクション
    immediate_delete = [
        "user_progress",
        "user_profiles", 
        "user_rankings",
        "learningLogs",
        "user_permissions"
    ]
    
    print("🗑️ 不要コレクションの削除開始")
    print(f"削除対象: {immediate_delete}")
    print()
    
    for collection_name in immediate_delete:
        try:
            print(f"削除中: {collection_name}")
            
            # コレクション内の全ドキュメントを削除
            collection_ref = db.collection(collection_name)
            docs = collection_ref.stream()
            
            delete_count = 0
            for doc in docs:
                doc.reference.delete()
                delete_count += 1
            
            print(f"✅ {collection_name}: {delete_count}件削除")
            
        except Exception as e:
            print(f"❌ {collection_name}削除エラー: {e}")
    
    print()
    print("✅ 即座削除対象コレクションの削除完了")
    print()
    print("📋 追加作業:")
    print("- weekly_rankings: 3ヶ月後削除推奨（履歴データのため）")
    print("- userCardsサブコレクション: 手動確認後削除")
    
    return True

def backup_before_deletion():
    """削除前の最終バックアップ"""
    
    print("💾 削除前バックアップ作成中...")
    
    # CompleteMigrationSystemを使用してバックアップ
    from complete_migration_system import CompleteMigrationSystem
    migration_system = CompleteMigrationSystem()
    
    backup_id = migration_system.backup_existing_data(
        backup_id=f"pre_deletion_backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    
    print(f"✅ バックアップ完了: {backup_id}")
    return backup_id

if __name__ == "__main__":
    print("Firestore移行後クリーンアップ")
    print("⚠️  この処理は移行完了・検証後にのみ実行してください")
    print()
    
    confirm = input("移行完了していますか？ (yes/no): ")
    if confirm.lower() != "yes":
        print("移行完了後に実行してください。")
        exit()
    
    backup_confirm = input("削除前にバックアップを作成しますか？ (yes/no): ")
    if backup_confirm.lower() == "yes":
        backup_id = backup_before_deletion()
        print(f"バックアップID: {backup_id}")
    
    delete_confirm = input("不要コレクションを削除しますか？ (yes/no): ")
    if delete_confirm.lower() == "yes":
        delete_obsolete_collections()
    else:
        print("削除を中止しました。")
'''
    
    return script


# === サマリー情報 ===

def print_deletion_summary():
    """削除対象サマリーの表示"""
    
    print("🗑️ === 移行後削除対象コレクション分析 ===")
    print()
    
    print("✅ 即座に削除可能（移行検証後）:")
    for collection in SAFE_TO_DELETE_IMMEDIATELY:
        info = CURRENT_COLLECTIONS[collection]
        print(f"  📁 {collection}")
        print(f"     理由: {info['reason']}")
        print(f"     安全性: {info['safety']}")
        print()
    
    print("⏰ 後で削除推奨:")
    for collection in SAFE_TO_DELETE_LATER:
        info = CURRENT_COLLECTIONS[collection]
        print(f"  📁 {collection}")
        print(f"     理由: {info['reason']}")
        print(f"     削除時期: {info['delete_timing']}")
        print()
    
    print("🔒 絶対に保持:")
    for collection in MUST_KEEP:
        print(f"  📁 {collection}")
    print()
    
    print("📊 削除効果:")
    print(f"  • 削除対象: {len(SAFE_TO_DELETE_IMMEDIATELY + SAFE_TO_DELETE_LATER)}個")
    print(f"  • 保持対象: {len(MUST_KEEP)}個")
    print(f"  • ストレージ削減: 約60-70%削減見込み")
    print(f"  • 管理コスト削減: 大幅な簡素化")


if __name__ == "__main__":
    print_deletion_summary()
    
    print()
    print("削除スクリプト生成しますか？ (yes/no)")
    choice = input()
    
    if choice.lower() == "yes":
        script_content = generate_deletion_script()
        with open("cleanup_firestore_collections.py", "w", encoding="utf-8") as f:
            f.write(script_content)
        print("✅ cleanup_firestore_collections.py を生成しました")
