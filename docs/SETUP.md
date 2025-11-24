# セットアップガイド

## 必要な環境
- Python 3.11
- Firebase CLI
- Git

## 初期セットアップ

### 1. リポジトリのクローン
```bash
git clone <repository-url>
cd dental-DX-PoC
```

### 2. Python環境の準備
```bash
# 仮想環境作成
python3.11 -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate  # Windows

# 依存関係インストール
pip install -r requirements.txt
```

### 3. Firebase設定
```bash
# Firebase CLIインストール（未インストールの場合）
npm install -g firebase-tools

# Firebaseログイン
firebase login

# プロジェクト確認
firebase projects:list
```

### 4. 環境変数設定
ルートに `.env` ファイルを作成:
```
# 必要に応じて追加
```

### 5. Streamlit Secrets設定（ローカル開発時）
`my_llm_app/.streamlit/secrets.toml` を作成:
```toml
# Firebase認証情報は自動取得されるため不要
```

## ローカル実行

### Webアプリ起動
```bash
./start_app.sh
```
または
```bash
cd my_llm_app
streamlit run app.py
```

### Cloud Functions ローカルテスト
```bash
cd functions
python main.py
# → http://localhost:8080 で起動
```

## 開発ワークフロー

1. **機能開発**: `my_llm_app/` で実装
2. **ローカルテスト**: `./start_app.sh` で動作確認
3. **Cloud Functions更新**: 必要に応じて `functions/main.py` を更新
4. **デプロイ**: `./deploy_functions.sh`

## トラブルシューティング

### Firebaseエラー
```bash
# プロジェクト再設定
firebase use --add
```

### 依存関係エラー
```bash
# 再インストール
pip install --upgrade -r requirements.txt
```

詳細は `DEVELOPMENT_GUIDE.md` を参照してください。
