#!/usr/bin/env python3
"""
学習データ取得の詳細デバッグ
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'my_llm_app'))

import datetime
from collections import Counter

def debug_learning_data():
    """学習データの詳細デバッグ"""
    
    # Firebase初期化
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
        
        # 既に初期化されている場合はスキップ
        try:
            firebase_admin.get_app()
            print("✅ Firebase app already initialized")
        except ValueError:
            # 初期化されていない場合のみ初期化
            cred_path = os.path.join('.streamlit', 'dental-dx-poc-firebase-adminsdk.json')
            if os.path.exists(cred_path):
                cred = credentials.Certificate(cred_path)
                firebase_admin.initialize_app(cred)
                print("✅ Firebase app initialized")
            else:
                print("❌ Firebase credentials not found")
                return
        
        # Firestoreクライアント取得
        db = firestore.client()
        
        print("🔍 学習データ詳細デバッグ開始")
        print("=" * 60)
        
        # テストユーザーID（実際に存在するID）
        test_uid = 'wLAvgm5MPZRnNwTZgFrl9iydUR33'
        
        print(f"\n📋 ユーザーID: {test_uid}")
        
        # 1. study_cardsコレクションから直接取得
        print("\n1️⃣ study_cardsコレクションから直接取得")
        study_cards_ref = db.collection("study_cards")
        user_cards_query = study_cards_ref.where("uid", "==", test_uid)
        user_cards_docs = user_cards_query.get()
        
        print(f"取得したドキュメント数: {len(user_cards_docs)}")
        
        # 2. データ構造の確認
        converted_cards = {}
        raw_sample = None
        
        for i, doc in enumerate(user_cards_docs):
            if i >= 3:  # 最初の3件のみ詳細確認
                break
                
            card_data = doc.to_dict()
            if i == 0:
                raw_sample = card_data
                
            question_id = card_data.get("question_id")
            if question_id:
                # 最適化後のデータ構造を旧形式に変換
                metadata = card_data.get("metadata", {})
                sm2_data = card_data.get("sm2_data", {})
                performance = card_data.get("performance", {})
                
                legacy_card = {
                    "question_id": question_id,
                    "level": metadata.get("original_level", -1),
                    "sm2": {
                        "n": sm2_data.get("n", 0),
                        "ef": sm2_data.get("ef", 2.5),
                        "interval": sm2_data.get("interval", 1),
                        "due_date": sm2_data.get("due_date"),
                        "last_studied": sm2_data.get("last_studied")
                    },
                    "performance": {
                        "correct_attempts": performance.get("correct_attempts", 0),
                        "total_attempts": performance.get("total_attempts", 0),
                        "avg_quality": performance.get("avg_quality", 0),
                        "last_quality": performance.get("last_quality", 0)
                    },
                    "history": card_data.get("history", []),
                    "difficulty": metadata.get("difficulty"),
                    "subject": metadata.get("subject"),
                    "updated_at": metadata.get("updated_at"),
                    "created_at": metadata.get("created_at")
                }
                converted_cards[question_id] = legacy_card
        
        # 3. サンプルデータの表示
        if raw_sample:
            print(f"\n2️⃣ サンプルカードの生データ構造:")
            print(f"キー: {list(raw_sample.keys())}")
            print(f"metadata: {raw_sample.get('metadata', {})}")
            print(f"sm2_data: {raw_sample.get('sm2_data', {})}")
            print(f"performance: {raw_sample.get('performance', {})}")
            print(f"history: {len(raw_sample.get('history', []))}件")
            
        # 4. 変換後データの確認
        if converted_cards:
            sample_converted = list(converted_cards.values())[0]
            print(f"\n3️⃣ 変換後のサンプルカード:")
            print(f"question_id: {sample_converted.get('question_id')}")
            print(f"level: {sample_converted.get('level')}")
            print(f"sm2: {sample_converted.get('sm2', {})}")
            print(f"history: {len(sample_converted.get('history', []))}件")
        
        # 5. 学習状況の詳細計算
        print(f"\n4️⃣ 学習状況の詳細計算（全{len(converted_cards)}件）")
        
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        print(f"今日の日付: {today}")
        
        review_count = 0
        new_count = 0
        completed_count = 0
        
        due_dates = []
        levels = []
        histories = []
        
        for q_id, card in converted_cards.items():
            # レベル収集
            level = card.get("level", -1)
            levels.append(level)
            
            # SM2データから復習期限を取得
            sm2_data = card.get("sm2", {})
            due_date = sm2_data.get("due_date", "")
            
            if due_date:
                due_dates.append(due_date)
                if due_date <= today:
                    review_count += 1
            
            # 今日の学習記録チェック
            history = card.get("history", [])
            histories.append(len(history))
            
            today_studied = any(h.get("date", "").startswith(today) for h in history)
            if today_studied:
                completed_count += 1
            elif len(history) == 0:  # 未学習カード
                new_count += 1
        
        # 統計情報の表示
        print(f"\n📊 詳細統計:")
        print(f"復習期限があるカード: {len(due_dates)}件")
        print(f"期限切れカード: {review_count}件")
        print(f"未学習カード: {new_count}件")
        print(f"今日学習済み: {completed_count}件")
        
        # レベル分布
        level_counts = Counter(levels)
        print(f"\nレベル分布: {dict(level_counts)}")
        
        # 履歴分布
        history_counts = Counter(histories)
        print(f"履歴数分布: {dict(sorted(history_counts.items())[:10])}")  # 上位10件
        
        # サンプルdue_date
        if due_dates:
            print(f"\nサンプルdue_date: {due_dates[:5]}")
        
        return True
        
    except Exception as e:
        print(f"❌ デバッグエラー: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    debug_learning_data()
