#!/usr/bin/env python3
"""
特定ユーザーの詳細データ確認スクリプト
"""

import sys
import os
from datetime import datetime
import json

# Firebase Admin SDK を直接使用
import firebase_admin
from firebase_admin import credentials, firestore

class SpecificUserChecker:
    """特定ユーザーの詳細チェッカー"""
    
    def __init__(self):
        self.db = None
        self._initialize_firebase()
    
    def _initialize_firebase(self):
        """Firebase Admin SDKを初期化"""
        try:
            # すでに初期化されている場合はスキップ
            if firebase_admin._apps:
                self.db = firestore.client()
                return
            
            # デフォルトの認証を使用（ADCが設定されている場合）
            cred = credentials.ApplicationDefault()
            firebase_admin.initialize_app(cred, {
                'projectId': 'dent-ai-4d8d8'  # 正しいプロジェクトIDを設定
            })
            
            self.db = firestore.client()
            print("✅ Firebase Admin SDK 初期化完了")
            
        except Exception as e:
            print(f"❌ Firebase初期化エラー: {e}")
            raise e
    
    def analyze_user_detailed(self, uid):
        """ユーザーの詳細分析"""
        try:
            print(f"🔍 ユーザー {uid} の詳細分析開始...")
            
            # study_cardsから該当ユーザーのデータを取得
            cards_ref = self.db.collection('study_cards')
            query = cards_ref.where('uid', '==', uid)
            cards_docs = query.get()
            
            cards = {}
            for doc in cards_docs:
                doc_data = doc.to_dict()
                question_id = doc_data.get('question_id')
                if question_id:
                    cards[question_id] = doc_data
            
            print(f"📊 取得したカード数: {len(cards)}")
            
            if not cards:
                print("❌ カードデータが見つかりません")
                return
            
            # 詳細統計
            stats = {
                'total_cards': len(cards),
                'has_history': 0,
                'has_attempts': 0,
                'total_history_entries': 0,
                'cards_with_level': 0,
                'unique_evaluations': set(),
                'learning_progression': []
            }
            
            cards_with_data = []
            
            # 全カードを分析
            for card_id, card_data in cards.items():
                history = card_data.get('history', [])
                performance = card_data.get('performance', {})
                sm2_data = card_data.get('sm2_data', {})
                
                if history:
                    stats['has_history'] += 1
                    stats['total_history_entries'] += len(history)
                    
                    # 履歴の詳細を収集
                    for entry in history:
                        if 'quality' in entry:
                            stats['unique_evaluations'].add(entry['quality'])
                        if 'timestamp' in entry:
                            stats['learning_progression'].append({
                                'card_id': card_id,
                                'timestamp': entry['timestamp'],
                                'quality': entry.get('quality', 0)
                            })
                    
                    cards_with_data.append({
                        'card_id': card_id,
                        'history_count': len(history),
                        'latest_entry': history[-1] if history else None,
                        'sm2_n': sm2_data.get('n', 0),
                        'performance': performance
                    })
                
                if performance.get('total_attempts', 0) > 0:
                    stats['has_attempts'] += 1
                
                if sm2_data.get('n', 0) > 0:
                    stats['cards_with_level'] += 1
            
            # 結果表示
            print(f"\n📈 統計サマリー:")
            print(f"  総カード数: {stats['total_cards']}")
            print(f"  履歴有りカード: {stats['has_history']}")
            print(f"  試行回数有りカード: {stats['has_attempts']}")
            print(f"  総履歴エントリ数: {stats['total_history_entries']}")
            print(f"  レベル有りカード: {stats['cards_with_level']}")
            print(f"  使用された評価値: {sorted(stats['unique_evaluations'])}")
            
            # 履歴があるカードの詳細表示
            if cards_with_data:
                print(f"\n🔍 履歴があるカードの詳細:")
                for i, card in enumerate(cards_with_data[:10]):  # 最初の10件
                    print(f"\n  カード {i+1}: {card['card_id']}")
                    print(f"    履歴エントリ数: {card['history_count']}")
                    print(f"    SM2回数: {card['sm2_n']}")
                    print(f"    パフォーマンス: {card['performance']}")
                    
                    if card['latest_entry']:
                        latest = card['latest_entry']
                        print(f"    最新エントリ:")
                        for key, value in latest.items():
                            if key == 'timestamp' and hasattr(value, 'seconds'):
                                # Firestore Timestampを読みやすい形式に変換
                                readable_time = datetime.fromtimestamp(value.seconds).strftime('%Y-%m-%d %H:%M:%S')
                                print(f"      {key}: {readable_time}")
                            else:
                                print(f"      {key}: {value}")
            
            # 学習進捗の時系列表示
            if stats['learning_progression']:
                print(f"\n⏰ 学習進捗タイムライン:")
                # タイムスタンプでソート
                progression = sorted(stats['learning_progression'], 
                                   key=lambda x: x['timestamp'] if hasattr(x['timestamp'], 'seconds') else x['timestamp'])
                
                for entry in progression[:20]:  # 最初の20件
                    timestamp = entry['timestamp']
                    if hasattr(timestamp, 'seconds'):
                        readable_time = datetime.fromtimestamp(timestamp.seconds).strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        readable_time = str(timestamp)
                    
                    print(f"  {readable_time} - カード:{entry['card_id'][:8]}... 評価:{entry['quality']}")
            
            return stats
            
        except Exception as e:
            print(f"❌ エラー: {e}")
            import traceback
            traceback.print_exc()
            return None

if __name__ == "__main__":
    target_uid = "wLAvgm5MPZRnNwTZgFrl9iydUR33"
    
    if len(sys.argv) > 1:
        target_uid = sys.argv[1]
    
    print(f"🎯 ターゲットユーザー: {target_uid}")
    print("="*70)
    
    checker = SpecificUserChecker()
    checker.analyze_user_detailed(target_uid)
