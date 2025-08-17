# 🦷 歯科国家試験AI対策アプリ

> **Firebase認証連携・SM-2復習アルゴリズム・PDF生成機能搭載の次世代学習プラットフォーム**

## 📋 目次

- [プロジェクト概要](#-プロジェクト概要)
- [主要機能](#-主要機能)
- [技術スタック](#-技術スタック)
- [セットアップ手順](#-セットアップ手順)
- [環境設定](#-環境設定)
- [デプロイメント](#-デプロイメント)
- [API仕様](#-api仕様)
- [ファイル構成](#-ファイル構成)
- [開発ガイド](#-開発ガイド)

---

## 🎯 プロジェクト概要

歯科医師国家試験の過去問を構造化データとして活用し、個人の学習進捗を追跡・最適化する学習支援アプリケーションです。科学的根拠に基づく間隔反復学習（SM-2アルゴリズム）と現代的なWeb技術を組み合わせることで、効率的な国試対策を実現します。

### 🎪 デモサイト
- **本番環境**: https://dental-quiz-app.streamlit.app
- **開発環境**: http://localhost:8505

### 📊 データ規模
- **総問題数**: 12,527問
- **学士試験データ**: 全年度対応（2022-2025）
- **正答率データ**: リアルタイム集計
- **画像問題**: 高解像度対応

---

## 🚀 主要機能

### � 認証・アカウント管理
- **Firebase Authentication連携**
  - メール・パスワード認証
  - パスワードリセット機能
  - セッション自動維持（50分間）
  - Remember me機能（Cookie連携）

### 📚 学習システム
- **間隔反復学習（SM-2アルゴリズム）**
  - 個人の記憶曲線に合わせた最適復習タイミング
  - 難易度別学習効率の自動調整
  - 長期記憶化を促進する科学的アプローチ

- **アダプティブ学習**
  - おまかせ学習モード（AI推奨）
  - 自由演習モード（分野・回数指定）
  - 短期復習キュー（即時フィードバック）

### 🎨 インタラクティブUI
- **レスポンシブデザイン**
  - ライトモード固定（視認性最適化）
  - サイドバー進捗表示
  - リアルタイム学習統計

- **問題表示機能**
  - 高解像度画像表示
  - LaTeX数式レンダリング
  - 選択肢シャッフル機能
  - 並び替え問題対応

### � レポート・出力機能
- **PDF生成（LaTeX）**
  - 日本語完全対応
  - 問題・解答・解説統合
  - カスタマイズ可能なレイアウト
  - 印刷最適化

- **学習分析**
  - 分野別正答率グラフ
  - 学習進捗トラッキング
  - 弱点分析レポート

### 🔍 検索・フィルター機能
- **高度検索**
  - キーワード検索（本文・選択肢）
  - 分野別フィルター
  - 難易度別分類
  - 学習状況フィルター

---

## 💻 技術スタック

### フロントエンド
- **Streamlit** `1.36+`: Webアプリケーションフレームワーク
- **HTML/CSS**: カスタムスタイリング
- **JavaScript**: インタラクティブ要素

### バックエンド
- **Python** `3.11+`: メインプログラミング言語
- **Firebase Admin SDK**: 認証・データベース連携
- **Requests**: HTTP通信ライブラリ

### データ管理
- **JSON**: 構造化問題データ
- **Pandas**: データ処理・分析
- **NumPy**: 数値計算

### PDF生成
- **LaTeX**: ドキュメント組版システム
- **LuaTeX/XeTeX**: 日本語対応エンジン
- **tcolorbox**: 問題レイアウトパッケージ

### 認証・セッション管理
- **Firebase Authentication**: ユーザー認証
- **streamlit-cookies-manager**: Cookie管理
- **JWT**: トークンベース認証

### デプロイメント
- **Streamlit Community Cloud**: 本番環境
- **GitHub Actions**: CI/CD
- **Docker**: コンテナ化対応

---

## ⚙️ セットアップ手順

### 1. リポジトリクローン
```bash
git clone https://github.com/eddy80524/dental-quiz-app.git
cd dental-quiz-app
```

### 2. Python環境構築
```bash
# Python 3.11+ 推奨
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. LaTeX環境構築（PDF生成用）
```bash
# macOS
brew install --cask mactex

# Ubuntu/Debian
sudo apt-get install texlive-luatex texlive-xetex texlive-lang-japanese

# Windows
# MiKTeX または TeX Live をインストール
```

### 4. アプリケーション起動
```bash
cd my_llm_app
streamlit run app.py --server.port 8505
```

---

## 🔧 環境設定

### Streamlit Secrets設定

`.streamlit/secrets.toml` を作成して以下を設定：

```toml
# Firebase設定
firebase_api_key = "your_firebase_api_key"
firebase_auth_domain = "your_project.firebaseapp.com"
firebase_project_id = "your_project_id"
firebase_storage_bucket = "your_project.appspot.com"
firebase_messaging_sender_id = "123456789012"
firebase_app_id = "1:123456789012:web:abcdef123456"

# Firebase Admin SDK
[firebase_credentials]
type = "service_account"
project_id = "your_project_id"
private_key_id = "key_id"
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "firebase-adminsdk-...@your_project.iam.gserviceaccount.com"
client_id = "123456789012345678901"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/firebase-adminsdk-...%40your_project.iam.gserviceaccount.com"

# Cookie暗号化
cookie_password = "your_secure_cookie_password_32chars+"
```

### 環境変数（任意）
```bash
export STREAMLIT_SERVER_PORT=8505
export STREAMLIT_SERVER_ADDRESS=0.0.0.0
export FIREBASE_PROJECT_ID=your_project_id
```

---

## 🌐 デプロイメント

### Streamlit Community Cloud

1. **GitHubリポジトリ準備**
   - リポジトリをpublic設定
   - secrets設定をStreamlit Cloudに登録

2. **必要ファイル確認**
   ```
   requirements.txt     # Python依存関係
   packages.txt        # システムパッケージ
   .streamlit/config.toml  # Streamlit設定
   ```

3. **デプロイ設定**
   - Main file path: `my_llm_app/app.py`
   - Python version: `3.11`
   - Advanced settings: Secrets設定

### Docker運用
```dockerfile
FROM python:3.11-slim

# LaTeX環境構築
RUN apt-get update && apt-get install -y \
    texlive-luatex \
    texlive-xetex \
    texlive-lang-japanese \
    && rm -rf /var/lib/apt/lists/*

# アプリケーション配置
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 8505

CMD ["streamlit", "run", "my_llm_app/app.py", "--server.port", "8505", "--server.address", "0.0.0.0"]
```

---

## 📡 API仕様

### Firebase Authentication API
```python
# ログイン
firebase_signin(email: str, password: str) -> dict

# パスワードリセット
firebase_reset_password(email: str) -> dict

# トークンリフレッシュ
firebase_refresh_token(refresh_token: str) -> dict
```

### データ管理API
```python
# 問題データ取得
load_master_data() -> dict

# ユーザーデータ取得
load_user_data_minimal(uid: str) -> dict

# 学習記録保存
sm2_update_with_policy(card: dict, quality: int) -> dict
```

### PDF生成API
```python
# LaTeX生成
generate_latex_for_questions(questions: list) -> str

# PDF変換
compile_latex_to_pdf(latex_content: str) -> bytes
```

---

## 📁 ファイル構成

```
dental-DX-PoC/
├── my_llm_app/              # メインアプリケーション
│   ├── app.py               # Streamlitメインファイル
│   ├── data/                # 問題データ
│   │   ├── master_questions_final.json
│   │   └── gakushi-*.json
│   └── __pycache__/
├── scraping/                # データ収集スクリプト
│   ├── scrape_dentalyouth.py
│   └── targets.py
├── notebooks/               # データ分析・実験
│   └── dental_exam_notebook.ipynb
├── requirements.txt         # Python依存関係
├── packages.txt            # システムパッケージ
├── .streamlit/             # Streamlit設定
│   └── config.toml
├── Dockerfile              # Docker設定
├── docker-compose.yml      # Docker Compose
└── README.md               # プロジェクト説明
```

### 主要ファイル詳細

#### `my_llm_app/app.py` (3,746行)
- **Firebase認証システム**: ログイン・認証・セッション管理
- **問題表示エンジン**: 画像・LaTeX・選択肢レンダリング
- **学習アルゴリズム**: SM-2間隔反復・進捗追跡
- **PDF生成機能**: LaTeX変換・コンパイル
- **検索・フィルター**: 高度検索・分野別分析

#### データファイル
- `master_questions_final.json`: 歯科医師国家試験過去問（構造化済み）
- `gakushi-*.json`: 学士試験データ（年度別）

---

## 🛠️ 開発ガイド

### ローカル開発環境
```bash
# 開発モード起動
streamlit run my_llm_app/app.py --logger.level debug

# コード品質チェック
python -c "import ast; ast.parse(open('my_llm_app/app.py').read())"

# 依存関係更新
pip freeze > requirements.txt
```

### デバッグ機能
- **ログレベル**: DEBUG, INFO, WARNING, ERROR
- **セッション状態表示**: サイドバーデバッグ情報
- **パフォーマンス計測**: 処理時間表示

### カスタマイズポイント
1. **問題データ追加**: `data/` ディレクトリにJSONファイル配置
2. **UI調整**: CSS設定をapp.pyの`st.markdown`セクションで修正
3. **学習アルゴリズム**: SM-2パラメータ調整
4. **PDF テンプレート**: LaTeX テンプレート修正

### コントリビューション
1. Forkリポジトリ作成
2. フィーチャーブランチ作成 (`git checkout -b feature/new-feature`)
3. 変更をコミット (`git commit -am 'Add new feature'`)
4. ブランチにプッシュ (`git push origin feature/new-feature`)
5. Pull Request作成

---

## 📄 ライセンス

このプロジェクトはMITライセンスの下で公開されています。

**注意事項**:
- 問題データは厚生労働省公表問題の引用です
- 学習・研究目的でのみ使用してください
- 商業利用には厚生労働省の許可が必要な場合があります

---

## 👨‍💻 作者

**eddy** - 歯科教育DXエンジニア

- 📧 Email: eddy80524@gmail.com
- 🌐 GitHub: [@eddy80524](https://github.com/eddy80524)
- 🎯 Mission: 日本の歯科教育の演習効率を技術で改善する

---

## 🤝 サポート

問題や要望がある場合は、以下の方法でお知らせください：

1. **GitHub Issues**: バグレポート・機能要望
2. **Discussion**: 一般的な質問・議論
3. **Email**: 直接的なサポート要請

---

## 📈 今後の開発予定

- [ ] 多選択肢問題対応拡充
- [ ] スマートフォンアプリ版
- [ ] チーム学習機能
- [ ] AIによる解説生成
- [ ] 音声問題対応
- [ ] オフライン学習モード
