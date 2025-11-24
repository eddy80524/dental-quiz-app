# デプロイ手順

## Cloud Functions デプロイ

### 準備
```bash
# リポジトリのルートディレクトリで実行
cd /path/to/dental-DX-PoC
```

### デプロイ実行
```bash
./deploy_functions.sh
```

このスクリプトは自動的に以下を実行します:
1. `my_llm_app` を `functions/my_llm_app` に同期
2. Python仮想環境 (`venv`) が存在しない場合は作成
3. Firebase Cloud Functions をデプロイ

### 手動デプロイ（オプション）
スクリプトを使わずに手動でデプロイする場合:

```bash
# 1. コード同期
rm -rf functions/my_llm_app
cp -R my_llm_app functions/my_llm_app

# 2. 仮想環境作成（初回のみ）
cd functions
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
deactivate

# 3. デプロイ
cd ..
firebase deploy --only functions
```

## Streamlit アプリ デプロイ

### ローカル起動
```bash
./start_app.sh
```

### Streamlit Cloud
1. Streamlit Cloud にログイン
2. リポジトリを接続
3. メインファイル: `my_llm_app/app.py`
4. Python バージョン: 3.11

## 環境変数
以下の環境変数が必要です:
- Firebaseの認証情報（自動取得）
- `.env` ファイル（ローカル開発時）

## デプロイ後の確認
```bash
# ヘルスチェック
curl https://YOUR_REGION-YOUR_PROJECT.cloudfunctions.net/healthCheck
```
