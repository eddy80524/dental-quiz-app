"""
Firestore構造分析と最適化設計書

現在の問題点：
1. 複雑すぎる週間ランキング管理
2. 不要な重複データ
3. 高頻度の書き込み処理
4. N+1クエリ問題
5. キャッシュ戦略の不備

最適化後の設計：
1. シンプルなコレクション構造
2. バッチ処理による書き込み削減
3. 効率的なクエリ設計
4. コスト最適化
"""

# 現在のFirestore構造（推定）
CURRENT_STRUCTURE = {
    "users": {
        "user_id": {
            "email": "string",
            "nickname": "string",
            "settings": {},
            "userCards": {  # サブコレクション
                "question_id": {
                    "level": "number",
                    "history": []
                }
            },
            "sessionState": {  # サブコレクション
                "current": {}
            }
        }
    },
    "weekly_rankings": {  # 問題：過度に複雑
        "2025-08-11": {
            "rankings": [],
            "week_start": "timestamp"
        }
    },
    "user_permissions": {  # 問題：別コレクション不要
        "user_id": {
            "can_access_gakushi": "boolean"
        }
    }
}

# 最適化後のFirestore構造
OPTIMIZED_STRUCTURE = {
    "users": {
        "user_id": {
            # 基本情報（書き込み頻度：低）
            "email": "string",
            "nickname": "string", 
            "created_at": "timestamp",
            "last_active": "timestamp",
            
            # 設定（書き込み頻度：低）
            "settings": {
                "new_cards_per_day": "number",
                "can_access_gakushi": "boolean"  # 統合
            },
            
            # 学習統計（書き込み頻度：中）- バッチ更新
            "stats": {
                "total_cards": "number",
                "mastered_cards": "number",  # level >= 4
                "total_points": "number",
                "weekly_points": "number",
                "last_updated": "timestamp"
            }
        }
    },
    
    "user_cards": {  # トップレベルに移動（パフォーマンス向上）
        "user_id_question_id": {  # 複合キー
            "user_id": "string",
            "question_id": "string", 
            "level": "number",
            "last_reviewed": "timestamp",
            "review_count": "number",
            "history": []  # 最小限に
        }
    },
    
    "user_sessions": {  # セッション状態（頻繁更新）
        "user_id": {
            "current_queue": [],
            "review_queue": [],
            "last_updated": "timestamp"
        }
    }
}

print("Firestore構造最適化設計書を作成しました")
