#!/usr/bin/env python3
"""
UserDataExtractorの問題をデバッグ
"""

import sys
import os
from datetime import datetime, timedelta

# Firebase Admin SDK を直接使用
import firebase_admin
from firebase_admin import credentials, firestore

# Firebase初期化
if not firebase_admin._apps:
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred, {
        'projectId': 'dent-ai-4d8d8'
    })

db = firestore.client()

def debug_data_structure(uid):
    """データ構造をデバッグ"""
    try:
        print(f"🔍 {uid} のデータ構造をデバッグ中...")
        
        # カードデータをサンプリング
        cards_ref = db.collection('study_cards')
        query = cards_ref.where('uid', '==', uid).limit(5)
        cards_docs = query.get()
        
        print(f"\n📋 カードデータサンプル (最大5件):")
        for i, doc in enumerate(cards_docs):
            card_data = doc.to_dict()
            print(f"\n--- カード {i+1} ---")
            print(f"question_id: {card_data.get('question_id')}")
            
            # SM2データ
            sm2_data = card_data.get('sm2_data', {})
            print(f"sm2_data.n (level): {sm2_data.get('n')} (type: {type(sm2_data.get('n'))})")
            
            # 履歴データの最初の1件
            history = card_data.get('history', [])
            if history:
                first_entry = history[0]
                timestamp = first_entry.get('timestamp')
                print(f"timestamp: {timestamp} (type: {type(timestamp)})")
                print(f"quality: {first_entry.get('quality')} (type: {type(first_entry.get('quality'))})")
                
                # DatetimeWithNanosecondsオブジェクトの詳細
                if hasattr(timestamp, '__dict__'):
                    print(f"timestamp attributes: {dir(timestamp)}")
                if hasattr(timestamp, 'timestamp'):
                    print(f"timestamp.timestamp(): {timestamp.timestamp()}")
                if hasattr(timestamp, 'seconds'):
                    print(f"timestamp.seconds: {timestamp.seconds}")
            else:
                print("履歴データなし")
                
            break
        
    except Exception as e:
        print(f"❌ デバッグエラー: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    uid = "wLAvgm5MPZRnNwTZgFrl9iydUR33"
    debug_data_structure(uid)
