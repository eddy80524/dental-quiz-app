import firebase_admin
from firebase_admin import credentials, firestore

# --- 初期化処理 ---
# あなたのサービスアカウントキーのファイル名を指定
CRED_PATH = 'firebase-credentials.json' 

try:
    cred = credentials.Certificate(CRED_PATH)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("✅ Firebaseへの接続に成功しました。")
except Exception as e:
    print(f"❌ Firebaseへの接続に失敗しました: {e}")
    exit()

# --- データ移行メイン処理 ---
def migrate_data():
    print("\n--- データ移行を開始します ---")
    
    # 1. 古いコレクションへの参照を取得
    old_collection_ref = db.collection('user_progress')
    
    # 2. 古いコレクションの全ドキュメントをストリームで読み込む
    docs = old_collection_ref.stream()
    
    total_users_migrated = 0
    total_cards_migrated = 0
    total_logs_created = 0

    for doc in docs:
        old_data = doc.to_dict()
        user_id = doc.id # 古いドキュメントID（UIDのはず）
        
        print(f"\n🔄 ユーザーID: {user_id} の移行処理を開始...")

        # --- 新しい `users` コレクションへの書き込み ---
        user_profile_data = {
            'email': old_data.get('email'),
            'schoolYear': old_data.get('schoolYear'), # 既存のデータにあれば
            'learningStatus': old_data.get('learningStatus'), # 既存のデータにあれば
            'settings': {
                'new_cards_per_day': old_data.get('new_cards_per_day', 10)
            },
            'createdAt': old_data.get('created_at') # 既存の作成日時を引き継ぐ
        }
        db.collection('users').document(user_id).set(user_profile_data)
        print(f"  - `users`コレクションにプロフィールを作成しました。")
        
        # --- `userCards` サブコレクションと `learningLogs` への書き込み ---
        cards_data = old_data.get('cards', {})
        if not isinstance(cards_data, dict):
            print(f"  - 警告: `cards` データが不正な形式です。スキップします。")
            continue

        for question_id, card_info in cards_data.items():
            if not isinstance(card_info, dict):
                continue

            # `userCards` にSM-2の進捗データを保存
            user_card_data = {
                'EF': card_info.get('EF', 2.5),
                'I': card_info.get('I', 0),
                'n': card_info.get('n', 0),
                'next_review': card_info.get('next_review'),
                'quality': card_info.get('quality'),
                'level': card_info.get('level')
            }
            db.collection('users').document(user_id).collection('userCards').document(question_id).set(user_card_data)
            total_cards_migrated += 1

            # `learningLogs` に過去の学習履歴を1件ずつログとして保存
            history = card_info.get('history', [])
            if isinstance(history, list):
                for log in history:
                    if isinstance(log, dict):
                        log_data = {
                            'userId': user_id,
                            'questionId': question_id,
                            'timestamp': log.get('timestamp'),
                            'quality': log.get('quality'),
                            'interval': log.get('interval'),
                            'EF': log.get('EF')
                        }
                        # 新しいlearningLogsコレクションにドキュメントを追加
                        db.collection('learningLogs').add(log_data)
                        total_logs_created += 1
        
        print(f"  - {len(cards_data)} 件のカードデータと、{total_logs_created - (total_users_migrated * len(cards_data))} 件の学習ログを移行しました。")
        total_users_migrated += 1

    print("\n--- データ移行が完了しました ---")
    print(f"👤 合計ユーザー数: {total_users_migrated}")
    print(f"🃏 合計カード数: {total_cards_migrated}")
    print(f"✍️ 合計ログ数: {total_logs_created}")

# --- スクリプトの実行 ---
if __name__ == '__main__':
    migrate_data()