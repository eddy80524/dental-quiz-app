# 🦷 歯科国家試験対策アプリ

AI-powered dental examination preparation app with spaced repetition learning system.

## 🚀 Streamlit Cloud デプロイメント手順

### 1. Firebase設定

1. Firebase Consoleで新しいプロジェクトを作成またはexisting project を使用
2. Firebase Authentication、Firestore、Cloud Functions を有効化
3. Service Account JSON をダウンロード

### 2. Streamlit Cloud Secrets設定

Streamlit Cloud App Dashboard の **Secrets** セクションで以下を設定:

```toml
[firebase]
type = "service_account"
project_id = "your-project-id"
private_key_id = "your-private-key-id"
private_key = "-----BEGIN PRIVATE KEY-----\nYOUR_PRIVATE_KEY\n-----END PRIVATE KEY-----\n"
client_email = "your-service-account-email"
client_id = "your-client-id"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/your-service-account-email"

[auth]
cookie_name = "dental_app_auth"
cookie_key = "your_random_secret_key"
cookie_expiry_days = 30
```

### 3. デプロイ設定

- **Main file path**: `my_llm_app/app.py`
- **Python version**: 3.11
- **Requirements**: `requirements.txt`

### 4. 機能

- 🎯 AI-powered問題生成
- 📊 スペース反復学習システム
- 🏆 ランキングシステム
- 📈 学習進捗分析
- 🔐 Firebase Authentication

## 🛠️ ローカル開発

```bash
# 依存関係インストール
pip install -r requirements.txt

# Streamlit アプリ起動
streamlit run my_llm_app/app.py
```

## 📋 環境要件

- Python 3.11+
- Firebase プロジェクト
- Streamlit Cloud アカウント

## 🔧 Cloud Functions (Optional)

自動ランキング更新用のCloud Functionsも利用可能:
- 毎日 3:00 AM JST に自動ランキング更新
- 手動トリガー対応
