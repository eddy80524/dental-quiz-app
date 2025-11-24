# 開発ガイド

## 🚀 開発環境のセットアップ

### 必要な環境
- Python 3.11
- Firebase CLI
- テキストエディタ（VS Code推奨）

### 初回セットアップ
詳細は [docs/SETUP.md](docs/SETUP.md) を参照してください。

## 🏃 アプリの起動

### 推奨: スクリプトで起動
```bash
./start_app.sh
```

自動実行される内容:
- 仮想環境のアクティベート
- 依存関係のインストール確認
- キャッシュクリア
- ポート8501の競合チェック
- Streamlitアプリの起動

### 手動起動
```bash
source .venv/bin/activate
streamlit run my_llm_app/app.py
```

## 🛠️ トラブルシューティング

### ポート8501が使用中
```bash
lsof -ti:8501 | xargs kill -9
```

### キャッシュクリア
```bash
find . -type d -name "__pycache__" -exec rm -rf {} +
rm -rf ~/.streamlit
```

### 仮想環境の再作成
```bash
rm -rf .venv
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 📁 プロジェクト構造

```
dental-DX-PoC/
├── my_llm_app/              # メインアプリケーション
│   ├── app.py               # エントリポイント
│   ├── modules/             # 機能モジュール
│   │   ├── practice_page.py
│   │   ├── search_page.py
│   │   └── ranking_page.py
│   ├── utils.py             # SM2アルゴリズム等
│   └── data/                # 問題データ
├── functions/               # Cloud Functions (Python)
│   ├── main.py              # 全関数の実装
│   └── my_llm_app/          # 共有ロジック（自動同期）
├── docs/                    # ドキュメント
├── deploy_functions.sh      # デプロイスクリプト
└── start_app.sh             # 起動スクリプト
```

## 🔧 開発ワークフロー

### 1. 機能開発
`my_llm_app/` 内で実装を行う

### 2. ローカルテスト
```bash
./start_app.sh
```

### 3. Cloud Functions更新（必要時）
`functions/main.py` を編集

### 4. デプロイ
```bash
./deploy_functions.sh
```

## 📊 データと機能

### 問題データ
- 国試問題: 8,576問
- 学士試験問題: 4,941問
- 合計: 13,517問

### 学習レベル（7段階）
- 未学習 → レベル0-5 → 習得済み
- SM2アルゴリズムで自動管理

### 主要機能
1. **練習ページ**: 問題演習とSM2学習
2. **検索ページ**: 問題検索と進捗分析
3. **ランキングページ**: ユーザーランキング

## 🐛 デバッグ

### ログ確認
Streamlitアプリのログはターミナルに表示されます。

### Cloud Functionsログ
```bash
firebase functions:log
```

## 📚 関連ドキュメント
- [セットアップ](docs/SETUP.md)
- [デプロイ](docs/DEPLOYMENT.md)
- [アーキテクチャ](docs/ARCHITECTURE.md)
