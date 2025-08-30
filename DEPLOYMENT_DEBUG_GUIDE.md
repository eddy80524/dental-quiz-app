# デプロイ環境での学習データ取得問題の診断・修正ガイド

## 🚨 問題: ローカルでは動作するが、デプロイ環境でユーザー学習データが0になる

### 📋 考えられる原因と解決策

#### 1. **Streamlit Secrets設定不備**
```bash
# 問題: Firebase認証情報がデプロイ環境で設定されていない
# 解決: デプロイ先で .streamlit/secrets.toml を正しく設定

# Streamlit Cloud の場合:
# - アプリ設定 > Secrets で secrets.toml の内容を設定

# Heroku の場合:
# - 環境変数として設定
heroku config:set FIREBASE_API_KEY=your-api-key
heroku config:set FIREBASE_CREDENTIALS='{"type": "service_account", ...}'

# その他のクラウドプロバイダー:
# - 環境変数またはシークレット管理機能を使用
```

#### 2. **Firebase プロジェクト設定の違い**
```python
# 問題: デプロイ環境で異なるFirebaseプロジェクトに接続している可能性
# 解決: プロジェクトIDを確認

# my_llm_app/firestore_db.py で以下をデバッグ出力に追加
def _initialize_firebase(self):
    firebase_creds = self._to_dict(st.secrets["firebase_credentials"])
    print(f"[DEBUG] 接続先Firebase Project: {firebase_creds.get('project_id')}")
    # ... 既存のコード
```

#### 3. **認証トークンの有効性**
```python
# 問題: デプロイ環境でトークンの更新が正しく行われていない
# 解決: auth.py にデバッグ情報を追加

def ensure_valid_session(self) -> bool:
    uid = st.session_state.get("uid")
    print(f"[DEBUG] Session UID: {uid}")
    
    # Firebase接続テスト
    try:
        from firestore_db import get_firestore_manager
        manager = get_firestore_manager()
        test_doc = manager.db.collection("users").document(uid).get()
        print(f"[DEBUG] Firebase接続テスト: {test_doc.exists}")
    except Exception as e:
        print(f"[DEBUG] Firebase接続エラー: {e}")
    
    return True  # 既存のロジック
```

#### 4. **セッション状態の保持問題**
```python
# 問題: デプロイ環境でセッション状態が正しく保持されていない
# 解決: より堅牢なセッション管理

# my_llm_app/app.py に追加
def debug_session_state():
    print(f"[DEBUG] Session State Keys: {list(st.session_state.keys())}")
    print(f"[DEBUG] User Logged In: {st.session_state.get('user_logged_in')}")
    print(f"[DEBUG] UID: {st.session_state.get('uid')}")
    print(f"[DEBUG] Cards Count: {len(st.session_state.get('cards', {}))}")

# メイン処理の最初で呼び出し
if __name__ == "__main__":
    debug_session_state()
```

#### 5. **Firestore セキュリティルール**
```javascript
// 問題:本番環境でセキュリティルールが厳しすぎる
// 解決: firestore.rules を確認

rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    // ユーザーデータアクセス許可
    match /users/{userId} {
      allow read, write: if request.auth != null && request.auth.uid == userId;
    }
    
    // study_cards コレクションアクセス許可
    match /study_cards/{cardId} {
      allow read, write: if request.auth != null;
    }
  }
}
```

### 🔧 即座に試すべき修正

#### 1. **デバッグモードを有効化**
```python
# my_llm_app/modules/practice_page.py の最上部に追加
import os
DEBUG_MODE = os.environ.get('DEBUG_MODE', 'false').lower() == 'true'

if DEBUG_MODE:
    print("[DEBUG] Practice Page - Debug Mode Enabled")
```

#### 2. **Firebase接続テスト関数を追加**
```python
# my_llm_app/app.py に追加
def test_firebase_connection():
    try:
        from firestore_db import get_firestore_manager
        manager = get_firestore_manager()
        
        # 現在のユーザーで接続テスト
        uid = st.session_state.get("uid")
        if uid:
            user_doc = manager.db.collection("users").document(uid).get()
            st.write(f"Firebase接続テスト: {user_doc.exists}")
            
            # study_cards テスト
            cards_query = manager.db.collection("study_cards").where("uid", "==", uid).limit(5)
            cards_docs = list(cards_query.stream())
            st.write(f"学習カード数（サンプル）: {len(cards_docs)}")
        else:
            st.write("UID not found in session")
            
    except Exception as e:
        st.error(f"Firebase接続エラー: {e}")

# サイドバーにテストボタンを追加
if st.sidebar.button("Firebase接続テスト"):
    test_firebase_connection()
```

### 📊 次のステップ

1. **デプロイ先の確認**: どこにデプロイしているか教えてください
2. **Secrets設定**: `.streamlit/secrets.toml` の内容確認
3. **ログ確認**: デプロイ環境のログでエラーメッセージを確認
4. **Firebase Console確認**: 実際のデータが存在するか確認

どのデプロイ方法を使用していますか？
- Streamlit Cloud
- Heroku  
- Google Cloud Run
- その他

この情報があれば、より具体的な解決策を提供できます。
