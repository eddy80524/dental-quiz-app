#!/usr/bin/env python3
"""
修正されたFirestoreデータ取得機能のテスト
"""

import sys
import os
sys.path.append(os.path.abspath('.'))

# Firestoreを直接初期化
import firebase_admin
from firebase_admin import credentials, firestore
import json

def test_firestore_data_access():
    """修正されたFirestoreデータアクセスをテスト"""
    
    # Firebase初期化
    try:
        # 既に初期化されている場合はスキップ
        firebase_admin.get_app()
        print("Firebase app already initialized")
    except ValueError:
        # 初期化されていない場合のみ初期化
        cred_path = os.path.join('.streamlit', 'dental-dx-poc-firebase-adminsdk.json')
        if os.path.exists(cred_path):
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
            print("Firebase app initialized with service account")
        else:
            print("Firebase credentials not found")
            return
    
    # Firestoreクライアント取得
    db = firestore.client()
    
    print("=== Firestoreデータアクセステスト ===")
    
    # study_cardsコレクションの確認
    print("\n1. study_cardsコレクションの確認...")
    study_cards_ref = db.collection("study_cards")
    
    # サンプルドキュメントを取得（最初の5件）
    sample_docs = study_cards_ref.limit(5).get()
    
    print(f"study_cardsコレクションの総数: {len(list(db.collection('study_cards').get()))}")
    
    if sample_docs:
        print("\nサンプルドキュメント:")
        for doc in sample_docs:
            doc_data = doc.to_dict()
            print(f"ドキュメントID: {doc.id}")
            print(f"UID: {doc_data.get('uid')}")
            print(f"Question ID: {doc_data.get('question_id')}")
            print(f"Metadata: {doc_data.get('metadata', {}).keys()}")
            print(f"Level: {doc_data.get('metadata', {}).get('original_level')}")
            print(f"SM2 Data: {doc_data.get('sm2_data', {}).keys()}")
            print("---")
            break  # 最初の1件だけ詳細表示
    
    # 特定ユーザーのデータ取得テスト
    print("\n2. 特定ユーザーのデータ取得テスト...")
    
    # 実際に存在するUIDを取得
    all_uids = set()
    for doc in study_cards_ref.limit(10).get():
        uid = doc.to_dict().get('uid')
        if uid:
            all_uids.add(uid)
    
    if all_uids:
        test_uid = list(all_uids)[0]
        print(f"テストユーザー: {test_uid}")
        
        # そのユーザーのカードを取得
        user_cards_query = study_cards_ref.where("uid", "==", test_uid)
        user_cards = user_cards_query.get()
        
        print(f"ユーザー {test_uid} のカード数: {len(user_cards)}")
        
        # データ構造の変換テスト
        converted_cards = {}
        for doc in user_cards:
            card_data = doc.to_dict()
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
        
        # 学習統計の計算
        learned_cards = len([card for card in converted_cards.values() if card.get("level", -1) >= 0])
        mastered_cards = len([card for card in converted_cards.values() if card.get("level", -1) >= 5])
        
        print(f"変換後のカード数: {len(converted_cards)}")
        print(f"学習済みカード: {learned_cards}問")
        print(f"習得済みカード: {mastered_cards}問")
        
        # レベル分布
        levels = [card.get("level", -1) for card in converted_cards.values()]
        from collections import Counter
        level_counts = Counter(levels)
        print(f"レベル分布: {dict(level_counts)}")
        
        return True
    else:
        print("利用可能なユーザーデータが見つかりません")
        return False

if __name__ == "__main__":
    test_firestore_data_access()
