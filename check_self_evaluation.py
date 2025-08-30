#!/usr/bin/env python3
"""
自己評価データの確認スクリプト
Firestoreから学習履歴を取得して、自己評価データの有無と統計を確認します。
"""

import sys
import os
import datetime
from collections import Counter

# パスを追加してモジュールをインポート
sys.path.append(os.path.join(os.path.dirname(__file__), 'my_llm_app'))

from firestore_db import get_firestore_manager

def analyze_self_evaluation_data():
    """自己評価データの分析"""
    print("🔍 自己評価データ分析開始...")
    
    try:
        # Firestoreマネージャーを取得
        firestore_manager = get_firestore_manager()
        
        # テストユーザーのUID（既知のユーザー）
        test_uid = "wLAvgm5MPZRnNwTZgFrl9iydUR33"
        
        print(f"📊 ユーザー: {test_uid}")
        
        # カードデータを取得
        cards = firestore_manager.get_cards(test_uid)
        print(f"📚 総カード数: {len(cards)}")
        
        if not cards:
            print("❌ カードデータが見つかりません")
            return
        
        # 自己評価データの統計
        self_evaluation_stats = {
            "× もう一度": 0,    # quality = 1
            "△ 難しい": 0,      # quality = 2
            "○ 普通": 0,        # quality = 3
            "◎ 簡単": 0         # quality = 4
        }
        
        total_evaluations = 0
        cards_with_history = 0
        cards_with_evaluations = 0
        
        quality_ratings = []
        
        print("\n📖 サンプルカードの詳細分析:")
        sample_count = 0
        
        for card_id, card_data in cards.items():
            history = card_data.get("history", [])
            
            if history:
                cards_with_history += 1
                has_evaluation = False
                
                # サンプル表示（最初の5件）
                if sample_count < 5:
                    print(f"\n🔸 カード {card_id}:")
                    print(f"  履歴件数: {len(history)}")
                    for i, h in enumerate(history[:3]):  # 最初の3件を表示
                        print(f"  履歴{i+1}: {h}")
                    sample_count += 1
                
                # 履歴の各エントリーをチェック
                for entry in history:
                    # 自己評価データの確認
                    quality = entry.get("quality")
                    rating = entry.get("rating")
                    
                    if quality is not None:
                        quality_ratings.append(quality)
                        total_evaluations += 1
                        has_evaluation = True
                        
                        # quality値から自己評価カテゴリにマッピング
                        if quality == 1:
                            self_evaluation_stats["× もう一度"] += 1
                        elif quality == 2:
                            self_evaluation_stats["△ 難しい"] += 1
                        elif quality == 3:
                            self_evaluation_stats["○ 普通"] += 1
                        elif quality == 4:
                            self_evaluation_stats["◎ 簡単"] += 1
                    
                    elif rating is not None:
                        # 古い形式のratingデータ
                        quality_ratings.append(rating)
                        total_evaluations += 1
                        has_evaluation = True
                
                if has_evaluation:
                    cards_with_evaluations += 1
        
        # 結果表示
        print(f"\n📊 自己評価データ統計:")
        print(f"  総カード数: {len(cards)}")
        print(f"  履歴があるカード: {cards_with_history}")
        print(f"  自己評価があるカード: {cards_with_evaluations}")
        print(f"  総自己評価回数: {total_evaluations}")
        
        if total_evaluations > 0:
            print(f"\n🎯 自己評価分布:")
            for category, count in self_evaluation_stats.items():
                percentage = (count / total_evaluations) * 100
                print(f"  {category}: {count}回 ({percentage:.1f}%)")
            
            print(f"\n📈 Quality値の分布:")
            quality_counter = Counter(quality_ratings)
            for quality in sorted(quality_counter.keys()):
                count = quality_counter[quality]
                percentage = (count / total_evaluations) * 100
                print(f"  Quality {quality}: {count}回 ({percentage:.1f}%)")
        else:
            print("⚠️ 自己評価データが見つかりませんでした")
        
        # 割合計算
        cards_percentage = (cards_with_evaluations / len(cards)) * 100 if cards else 0
        
        print(f"\n🔢 カバレッジ:")
        print(f"  自己評価済みカード率: {cards_percentage:.1f}% ({cards_with_evaluations}/{len(cards)})")
        
        return {
            "total_cards": len(cards),
            "cards_with_evaluations": cards_with_evaluations,
            "total_evaluations": total_evaluations,
            "evaluation_distribution": self_evaluation_stats,
            "coverage_percentage": cards_percentage
        }
        
    except Exception as e:
        print(f"❌ エラー: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    analyze_self_evaluation_data()
