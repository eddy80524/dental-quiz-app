#!/usr/bin/env python3
"""
ユーザーの自己評価ログとカードレベルデータの確認スクリプト（Streamlit非依存版）
"""

import sys
import os
import json
from datetime import datetime

# Firebase Admin SDK を直接使用
import firebase_admin
from firebase_admin import credentials, firestore

class DirectFirestoreManager:
    """Streamlitに依存しないFirestoreマネージャー"""
    
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
            
            # 環境変数からサービスアカウントキーを取得
            service_account_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
            
            if service_account_path and os.path.exists(service_account_path):
                # サービスアカウントキーファイルから初期化
                cred = credentials.Certificate(service_account_path)
                firebase_admin.initialize_app(cred)
            else:
                # デフォルトの認証を使用（ADCが設定されている場合）
                cred = credentials.ApplicationDefault()
                firebase_admin.initialize_app(cred, {
                    'projectId': 'dent-ai-4d8d8'  # 正しいプロジェクトIDを設定
                })
            
            self.db = firestore.client()
            print("✅ Firebase Admin SDK 初期化完了")
            
        except Exception as e:
            print(f"❌ Firebase初期化エラー: {e}")
            print("環境変数 GOOGLE_APPLICATION_CREDENTIALS を設定するか、")
            print("Google Cloud ADC を設定してください。")

class DirectFirestoreChecker:
    """Firestore データチェッカー（簡易版）"""
    
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
            
            # 環境変数からサービスアカウントキーを取得
            service_account_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
            
            if service_account_path and os.path.exists(service_account_path):
                # サービスアカウントキーファイルから初期化
                cred = credentials.Certificate(service_account_path)
                firebase_admin.initialize_app(cred)
            else:
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
    
    def get_user_cards_multi_path(self, uid):
        """複数の方法でユーザーのカードデータを取得"""
        try:
            print(f"📊 ユーザー {uid} のカードデータを複数パスで検索...")
            
            # 方法1: study_cardsコレクションから該当ユーザーのデータを取得
            try:
                print("  📊 study_cardsから検索...")
                cards_ref = self.db.collection('study_cards')
                query = cards_ref.where('uid', '==', uid)
                cards_docs = query.get()
                
                cards = {}
                for doc in cards_docs:
                    doc_data = doc.to_dict()
                    question_id = doc_data.get('question_id')
                    if question_id:
                        cards[question_id] = doc_data
                
                if cards:
                    print(f"  ✅ study_cardsから{len(cards)}件取得")
                    return cards
            
            except Exception as e:
                print(f"  ❌ study_cardsでエラー: {e}")
            
            # 方法2: users/{uid}/userCardsサブコレクションから取得
            try:
                print("  📊 users/{uid}/userCardsから検索...")
                cards_ref = self.db.collection('users').document(uid).collection('userCards')
                cards_docs = cards_ref.get()
                
                cards = {}
                for doc in cards_docs:
                    cards[doc.id] = doc.to_dict()
                
                if cards:
                    print(f"  ✅ userCardsから{len(cards)}件取得")
                    return cards
                
            except Exception as e:
                print(f"  ❌ userCardsでエラー: {e}")
            
            # 方法3: users/{uid}/cardsサブコレクションから取得
            try:
                print("  📊 users/{uid}/cardsから検索...")
                cards_ref = self.db.collection('users').document(uid).collection('cards')
                cards_docs = cards_ref.get()
                
                cards = {}
                for doc in cards_docs:
                    cards[doc.id] = doc.to_dict()
                
                if cards:
                    print(f"  ✅ cardsから{len(cards)}件取得")
                    return cards
                
            except Exception as e:
                print(f"  ❌ cardsでエラー: {e}")
            
            print(f"  ⚠️  すべての方法でカードが見つかりませんでした")
            return {}
            
        except Exception as e:
            print(f"❌ カードデータ取得エラー: {e}")
            return {}
            raise
    
    def get_cards(self, uid):
        """ユーザーのカードデータを取得（複数のパスを試行）"""
        try:
            print(f"🔍 UIDでカードデータを検索: {uid}")
            
            # 方法1: study_cardsコレクションから取得
            try:
                print("  📊 study_cardsコレクションから検索...")
                cards_query = self.db.collection('study_cards').where('uid', '==', uid)
                cards_docs = cards_query.get()
                
                if cards_docs:
                    cards = {}
                    for doc in cards_docs:
                        doc_data = doc.to_dict()
                        question_id = doc_data.get('question_id')
                        if question_id:
                            cards[question_id] = doc_data
                    
                    if cards:
                        print(f"  ✅ study_cardsから{len(cards)}件取得")
                        return cards
                
            except Exception as e:
                print(f"  ❌ study_cardsでエラー: {e}")
            
            # 方法2: users/{uid}/userCardsサブコレクションから取得
            try:
                print("  📊 users/{uid}/userCardsから検索...")
                cards_ref = self.db.collection('users').document(uid).collection('userCards')
                cards_docs = cards_ref.get()
                
                cards = {}
                for doc in cards_docs:
                    cards[doc.id] = doc.to_dict()
                
                if cards:
                    print(f"  ✅ userCardsから{len(cards)}件取得")
                    return cards
                
            except Exception as e:
                print(f"  ❌ userCardsでエラー: {e}")
            
            # 方法3: users/{uid}/cardsサブコレクションから取得
            try:
                print("  📊 users/{uid}/cardsから検索...")
                cards_ref = self.db.collection('users').document(uid).collection('cards')
                cards_docs = cards_ref.get()
                
                cards = {}
                for doc in cards_docs:
                    cards[doc.id] = doc.to_dict()
                
                if cards:
                    print(f"  ✅ cardsから{len(cards)}件取得")
                    return cards
                
            except Exception as e:
                print(f"  ❌ cardsでエラー: {e}")
            
            print(f"  ⚠️  すべての方法でカードが見つかりませんでした")
            return {}
            
        except Exception as e:
            print(f"❌ カードデータ取得エラー: {e}")
            return {}
    
    def find_users_with_data(self):
        """データがあるユーザーを検索"""
        try:
            print("🔍 データがあるユーザーを検索中...")
            
            # より広範囲でユーザーを検索
            cards_ref = self.db.collection('study_cards')
            
            # まず全体のドキュメント数を確認
            total_docs = len(cards_ref.get())
            print(f"  📊 study_cardsの総ドキュメント数: {total_docs}")
            
            # ユニークなuidを取得（バッチサイズを大きくして検索）
            uids = set()
            batch_size = 1000
            last_doc = None
            batch_count = 0
            
            while True:
                if last_doc:
                    query = cards_ref.order_by('question_id').start_after(last_doc).limit(batch_size)
                else:
                    query = cards_ref.order_by('question_id').limit(batch_size)
                
                docs = query.get()
                if not docs:
                    break
                
                batch_count += 1
                print(f"  🔄 バッチ {batch_count}: {len(docs)}件処理中...")
                
                for doc in docs:
                    doc_data = doc.to_dict()
                    uid = doc_data.get('uid')
                    if uid:
                        uids.add(uid)
                
                last_doc = docs[-1]
                
                # 安全のため、10バッチで一旦停止
                if batch_count >= 10:
                    print(f"  ⚠️  安全のため10バッチで停止（{batch_count * batch_size}件確認済み）")
                    break
            
            print(f"  📊 見つかったユニークユーザー: {len(uids)}人")
            uids_list = list(uids)
            
            # 全ユーザーを表示
            for i, uid in enumerate(uids_list):
                print(f"    {i+1}. {uid}")
            
            return uids_list
            
        except Exception as e:
            print(f"❌ ユーザー検索エラー: {e}")
            return []
    
    def find_users_in_users_collection(self):
        """usersコレクションからユーザーを検索"""
        try:
            print("🔍 usersコレクションからユーザーを検索中...")
            
            users_ref = self.db.collection('users')
            users_docs = users_ref.get()
            
            users = []
            for doc in users_docs:
                user_id = doc.id
                user_data = doc.to_dict()
                users.append({
                    'uid': user_id,
                    'data': user_data
                })
            
            print(f"  📊 usersコレクションで見つかったユーザー: {len(users)}人")
            for i, user in enumerate(users):
                print(f"    {i+1}. {user['uid']}")
                # ユーザーデータの主要フィールドを表示
                if user['data']:
                    key_fields = ['email', 'displayName', 'createdAt', 'lastLoginAt']
                    for field in key_fields:
                        if field in user['data']:
                            print(f"        {field}: {user['data'][field]}")
            
            return users
            
        except Exception as e:
            print(f"❌ usersコレクション検索エラー: {e}")
            return []

def check_user_data(uid=None):
    """指定されたユーザー（またはテストユーザー）のデータを確認"""
    
    # Firestoreマネージャーを取得
    try:
        firestore_manager = DirectFirestoreManager()
    except Exception as e:
        print(f"❌ Firestore接続に失敗しました: {e}")
        return None
    
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
                # 日付を読みやすい形式で表示
                last_entry = card['last_entry'].copy()
                if 'timestamp' in last_entry:
                    timestamp = last_entry['timestamp']
                    if hasattr(timestamp, 'seconds'):  # Firestore Timestamp
                        last_entry['timestamp'] = datetime.fromtimestamp(timestamp.seconds).strftime('%Y-%m-%d %H:%M:%S')
                print(f"  最新エントリ: {json.dumps(last_entry, ensure_ascii=False, indent=4)}")
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
        
        # 7. SM2アルゴリズム関連データの確認
        print(f"\n🧠 SM2アルゴリズム関連データ:")
        ease_factors = []
        intervals = []
        
        for card_data in cards.values():
            if 'easiness_factor' in card_data:
                ease_factors.append(card_data['easiness_factor'])
            if 'interval' in card_data:
                intervals.append(card_data['interval'])
        
        if ease_factors:
            avg_ease = sum(ease_factors) / len(ease_factors)
            print(f"  平均難易度係数: {avg_ease:.2f} ({len(ease_factors)}枚)")
        
        if intervals:
            avg_interval = sum(intervals) / len(intervals)
            print(f"  平均復習間隔: {avg_interval:.1f}日 ({len(intervals)}枚)")
        
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

if __name__ == "__main__":
    print("� Firestore直接接続によるユーザーデータ検証を開始します...")
    
    checker = DirectFirestoreChecker()
    
    # 1. データがあるユーザーを検索
    users_with_data = checker.find_users_with_data()
    
    if not users_with_data:
        print("❌ データがあるユーザーが見つかりませんでした")
    else:
        print(f"\n✅ {len(users_with_data)}人のユーザーデータが見つかりました")
        
        # 2. 最初の数人についてデータを確認
        print(f"\n🔍 最初の3人のユーザーデータを詳細確認中...")
        for i, uid in enumerate(users_with_data[:3]):
            print(f"\n--- ユーザー {i+1}: {uid} ---")
            
            # カードデータ取得
            cards_data = checker.get_user_cards_multi_path(uid)
            print(f"カードデータ数: {len(cards_data)}")
            
            # 自己評価データのサンプル表示
            if cards_data:
                # 最初のカードの全フィールドを表示
                sample_card = list(cards_data.values())[0]
                print(f"サンプルカード（ID: {list(cards_data.keys())[0]}）の全フィールド:")
                for key, value in sample_card.items():
                    if isinstance(value, list):
                        print(f"  - {key}: リスト({len(value)}件)")
                        if value:  # リストが空でない場合は最初の要素も表示
                            print(f"    例: {value[0]}")
                    elif isinstance(value, dict):
                        print(f"  - {key}: 辞書({len(value)}キー)")
                        # 辞書の中身も表示
                        for sub_key, sub_value in value.items():
                            print(f"    {sub_key}: {sub_value}")
                    else:
                        print(f"  - {key}: {value}")
                
                # より詳細な統計
                has_history = 0
                has_level = 0
                has_evaluation = 0
                has_sm2_data = 0
                has_performance = 0
                total_evaluations = 0
                
                for card_id, card_data in list(cards_data.items())[:50]:  # 最初の50件を確認
                    if 'history' in card_data and card_data['history']:
                        has_history += 1
                        total_evaluations += len(card_data['history'])
                    if 'level' in card_data and card_data['level'] > 0:
                        has_level += 1
                    if 'self_evaluation' in card_data:
                        has_evaluation += 1
                    if 'sm2_data' in card_data:
                        has_sm2_data += 1
                    if 'performance' in card_data:
                        has_performance += 1
                
                print(f"\n統計情報（最初の50件）:")
                print(f"  📊 履歴有りカード: {has_history}/50件")
                print(f"  📊 レベル設定カード: {has_level}/50件")
                print(f"  📊 自己評価設定カード: {has_evaluation}/50件")
                print(f"  📊 SM2データ有りカード: {has_sm2_data}/50件")
                print(f"  📊 パフォーマンスデータ有りカード: {has_performance}/50件")
                print(f"  📊 総評価回数: {total_evaluations}回")
            
    print("\n✅ 全データ検証完了")


if __name__ == "__main__":
    print("🔧 Firestore直接接続によるユーザーデータ検証を開始します...")
    
    checker = DirectFirestoreChecker()
    
    # 1. study_cardsからユーザーを検索
    print("\n" + "="*60)
    print("📊 STUDY_CARDSコレクションからユーザー検索")
    print("="*60)
    users_with_cards = checker.find_users_with_data()
    
    # 2. usersコレクションからユーザーを検索
    print("\n" + "="*60)
    print("👥 USERSコレクションからユーザー検索")
    print("="*60)
    users_in_users_collection = checker.find_users_in_users_collection()
    
    # 3. 結果の比較
    print("\n" + "="*60)
    print("🔍 検索結果の比較")
    print("="*60)
    
    cards_uids = set(users_with_cards)
    users_uids = set(user['uid'] for user in users_in_users_collection)
    
    print(f"study_cardsにデータがあるユーザー: {len(cards_uids)}人")
    print(f"usersコレクションに登録済みユーザー: {len(users_uids)}人")
    
    # 共通ユーザー
    common_users = cards_uids & users_uids
    print(f"両方に存在するユーザー: {len(common_users)}人")
    
    # study_cardsのみにいるユーザー
    cards_only = cards_uids - users_uids
    if cards_only:
        print(f"study_cardsのみにいるユーザー: {len(cards_only)}人")
        for uid in cards_only:
            print(f"  - {uid}")
    
    # usersのみにいるユーザー
    users_only = users_uids - cards_uids
    if users_only:
        print(f"usersのみにいるユーザー: {len(users_only)}人")
        for uid in users_only:
            print(f"  - {uid}")
    
    print("\n✅ ユーザー検索完了")
