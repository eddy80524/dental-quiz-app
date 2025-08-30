#!/usr/bin/env python3
"""
ユーザーの自己評価ログとカードレベルデータの確認スクリプト
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'my_llm_app'))

from my_llm_app.firestore_db import get_firestore_manager
import json
from datetime import datetime

def check_user_data(uid=None):
    """指定されたユーザー（またはテストユーザー）のデータを確認"""
    
    # Firestoreマネージャーを取得
    firestore_manager = get_firestore_manager()
    
    # UIDが指定されていない場合は、既知のテストユーザーを使用
    if not uid:
        uid = "wLAvgm5MPZRnNwTZgFrl9iydUR33"  # ログで見たUID
        print(f"デフォルトテストユーザーを使用: {uid}")
    
    print(f"=" * 60)
    print(f"ユーザーデータ確認: {uid}")
    print(f"=" * 60)
    
    try:
        # 1. ユーザーの全カードデータを取得
        print("📊 Firestoreからカードデータを取得中...")
        cards = firestore_manager.get_cards(uid)
        
        if not cards:
            print("❌ カードデータが見つかりません")
            return
        
        print(f"✅ 取得したカード数: {len(cards)}")
        
        # 2. 自己評価データの分析
        print("\n" + "=" * 40)
        print("🔍 自己評価データ分析")
        print("=" * 40)
        
        evaluation_stats = {
            "× もう一度": 0,    # quality = 1
            "△ 難しい": 0,      # quality = 2  
            "○ 普通": 0,        # quality = 3
            "◎ 簡単": 0         # quality = 4
        }
        
        total_evaluations = 0
        cards_with_evaluations = 0
        cards_with_history = 0
        level_distribution = {}
        
        # 詳細分析用
        sample_cards = []
        
        for card_id, card_data in cards.items():
            history = card_data.get("history", [])
            level = card_data.get("level", 0)
            
            # レベル分布
            if level not in level_distribution:
                level_distribution[level] = 0
            level_distribution[level] += 1
            
            if history:
                cards_with_history += 1
                has_evaluation = False
                
                # 履歴をチェック
                for entry in history:
                    quality = entry.get("quality")
                    
                    if quality is not None and 1 <= quality <= 4:
                        total_evaluations += 1
                        has_evaluation = True
                        
                        if quality == 1:
                            evaluation_stats["× もう一度"] += 1
                        elif quality == 2:
                            evaluation_stats["△ 難しい"] += 1
                        elif quality == 3:
                            evaluation_stats["○ 普通"] += 1
                        elif quality == 4:
                            evaluation_stats["◎ 簡単"] += 1
                
                if has_evaluation:
                    cards_with_evaluations += 1
                
                # サンプルカード収集（最初の5件）
                if len(sample_cards) < 5:
                    sample_cards.append({
                        'card_id': card_id,
                        'level': level,
                        'history_count': len(history),
                        'last_entry': history[-1] if history else None,
                        'evaluations': [entry.get('quality') for entry in history if entry.get('quality') is not None]
                    })
        
        # 3. 結果表示
        print(f"📈 総カード数: {len(cards)}")
        print(f"📝 履歴があるカード: {cards_with_history}")
        print(f"⭐ 自己評価があるカード: {cards_with_evaluations}")
        print(f"🔢 総自己評価回数: {total_evaluations}")
        
        print(f"\n📊 自己評価分布:")
        for category, count in evaluation_stats.items():
            if total_evaluations > 0:
                percentage = (count / total_evaluations) * 100
                print(f"  {category}: {count}回 ({percentage:.1f}%)")
            else:
                print(f"  {category}: {count}回")
        
        print(f"\n🎯 カードレベル分布:")
        for level in sorted(level_distribution.keys()):
            count = level_distribution[level]
            percentage = (count / len(cards)) * 100
            print(f"  レベル{level}: {count}枚 ({percentage:.1f}%)")
        
        # 4. サンプルカード詳細表示
        print(f"\n🔍 サンプルカード詳細 (最初の5件):")
        print("-" * 50)
        for i, card in enumerate(sample_cards, 1):
            print(f"カード{i}: {card['card_id'][:12]}...")
            print(f"  レベル: {card['level']}")
            print(f"  履歴件数: {card['history_count']}")
            print(f"  自己評価: {card['evaluations']}")
            if card['last_entry']:
                print(f"  最新エントリ: {json.dumps(card['last_entry'], ensure_ascii=False, indent=4)}")
            print()
        
        # 5. データの整合性チェック
        print("🔧 データ整合性チェック:")
        
        # レベルと評価の関係をチェック
        high_level_low_eval = 0
        low_level_high_eval = 0
        
        for card_id, card_data in cards.items():
            level = card_data.get("level", 0)
            history = card_data.get("history", [])
            
            if history:
                # 最新の評価を取得
                latest_quality = None
                for entry in reversed(history):
                    if entry.get("quality") is not None:
                        latest_quality = entry.get("quality")
                        break
                
                if latest_quality:
                    # レベルが高いのに最新評価が低い
                    if level >= 3 and latest_quality <= 2:
                        high_level_low_eval += 1
                    # レベルが低いのに最新評価が高い
                    elif level <= 1 and latest_quality >= 3:
                        low_level_high_eval += 1
        
        print(f"  ⚠️  高レベル低評価カード: {high_level_low_eval}")
        print(f"  ⚠️  低レベル高評価カード: {low_level_high_eval}")
        
        # 6. 学習進捗の確認
        mastered_cards = sum(1 for card_data in cards.values() if card_data.get("level", 0) >= 4)
        learning_cards = sum(1 for card_data in cards.values() if 0 < card_data.get("level", 0) < 4)
        new_cards = sum(1 for card_data in cards.values() if card_data.get("level", 0) == 0)
        
        print(f"\n📚 学習進捗:")
        print(f"  新規カード: {new_cards}")
        print(f"  学習中カード: {learning_cards}")
        print(f"  習得済みカード: {mastered_cards}")
        
        return {
            'total_cards': len(cards),
            'cards_with_history': cards_with_history,
            'cards_with_evaluations': cards_with_evaluations,
            'total_evaluations': total_evaluations,
            'evaluation_stats': evaluation_stats,
            'level_distribution': level_distribution,
            'sample_cards': sample_cards
        }
        
    except Exception as e:
        print(f"❌ エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        return None

def check_multiple_users():
    """複数のユーザーのデータを確認"""
    
    firestore_manager = get_firestore_manager()
    
    # すべてのユーザーのリストを取得（可能であれば）
    try:
        # Firestoreから全ユーザーを取得する方法を試す
        print("🔍 利用可能なユーザーを検索中...")
        
        # 既知のテストユーザー
        test_uids = [
            "wLAvgm5MPZRnNwTZgFrl9iydUR33"
        ]
        
        for uid in test_uids:
            print(f"\n{'='*20} ユーザー: {uid} {'='*20}")
            result = check_user_data(uid)
            if result:
                print("✅ データ確認完了")
            else:
                print("❌ データ確認失敗")
                
    except Exception as e:
        print(f"❌ 複数ユーザー確認でエラー: {e}")

if __name__ == "__main__":
    print("🔍 ユーザーデータ確認スクリプト")
    print("=" * 60)
    
    if len(sys.argv) > 1:
        # コマンドライン引数でUIDが指定された場合
        uid = sys.argv[1]
        check_user_data(uid)
    else:
        # デフォルトユーザーをチェック
        check_user_data()
