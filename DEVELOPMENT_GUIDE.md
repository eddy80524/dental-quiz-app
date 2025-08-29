# 歯科国試アプリ 開発環境セットアップガイド

## 🚀 簡単起動方法

### 方法1: スクリプトで起動（推奨）

```bash
./start_app.sh
```

このスクリプトは以下を自動実行します：
- 仮想環境のアクティベート
- 依存関係のインストール確認
- キャッシュクリア（Python + Streamlit）
- ポート8501の競合チェック
- Streamlitアプリの起動

### 方法2: VS Code タスクで起動

1. `Cmd+Shift+P` でコマンドパレットを開く
2. "Tasks: Run Task" を選択
3. "歯科国試アプリ起動" を選択

### 方法3: 手動起動

```bash
# 1. 仮想環境アクティベート
source .venv/bin/activate

# 2. キャッシュクリア
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
rm -rf ~/.streamlit 2>/dev/null || true

# 3. アプリ起動
streamlit run my_llm_app/app.py
```

## 🛠️ トラブルシューティング

### よくある問題と解決法

#### 1. ポート8501が使用中エラー
```bash
# 使用中のプロセスを確認
lsof -i:8501

# プロセスを終了
lsof -ti:8501 | xargs kill -9
```

#### 2. キャッシュ関連の問題
VS Codeタスク "キャッシュクリア" を実行するか：
```bash
# 手動でキャッシュクリア
find . -type d -name "__pycache__" -exec rm -rf {} +
find . -name "*.pyc" -delete
rm -rf ~/.streamlit
rm -rf .streamlit
```

#### 3. 仮想環境の問題
```bash
# 仮想環境を再作成
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

#### 4. Firebase Functions のコンパイルエラー
VS Codeタスク "Firebase Functions ビルド" を実行するか：
```bash
cd functions
npm run build
```

## 📊 アプリ機能

### 学習レベルシステム（7段階）
- **未学習**: まだ学習していない問題
- **レベル0**: 初回学習（赤色）
- **レベル1**: 2回目学習（オレンジ色）
- **レベル2**: 3回目学習（黄色）
- **レベル3**: 4回目学習（薄緑色）
- **レベル4**: 5回目学習（緑色）
- **レベル5**: 6回目学習（青色）
- **習得済み**: 完全に習得した問題（紫色）

### 問題データ
- **国試問題**: 8,576問
- **学士試験問題**: 4,941問
- **合計**: 13,517問

### 主要ページ
1. **ホーム**: 学習状況ダッシュボード
2. **問題練習**: ランダム出題と学習記録
3. **検索・進捗**: 問題検索と詳細な進捗分析
4. **ランキング**: ユーザーランキングとプロフィール

## 🔧 開発者向け情報

### プロジェクト構造
```
dental-DX-PoC/
├── my_llm_app/           # Streamlitアプリ
│   ├── app.py           # メインアプリ
│   ├── modules/         # ページモジュール
│   └── data/           # 問題データ
├── functions/           # Firebase Functions
├── .venv/              # Python仮想環境
└── start_app.sh        # 起動スクリプト
```

### 環境変数
Firebase設定は `firebase.json` と環境変数で管理

### バックアップ
重要なファイルは定期的にバックアップを推奨

---

**問題が解決しない場合は、start_app.sh を実行してください。**
