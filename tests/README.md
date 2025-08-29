# 📁 テストファイル

このディレクトリには、開発・テスト用のファイルが整理されています。

## 📂 構成

```
tests/
├── latex/              # LaTeX PDF生成のテストファイル
│   ├── ideal_latex_test.py
│   ├── improved_framed_test.py
│   ├── improved_latex_test.py
│   ├── jsarticle_test.py
│   ├── simple_latex_template.py
│   ├── simple_latex_test.py
│   └── step_ideal_test.py
├── demos/              # デモ・プロトタイプファイル
│   └── pdf_demo.py
└── scripts/            # 開発・管理用スクリプト
    ├── run_scraper.py
    ├── start_streamlit_ngrok.py
    ├── migration/      # データ移行スクリプト
    │   ├── migrate.py
    │   └── migrate_data.py
    ├── debug/          # デバッグ・検証スクリプト
    │   ├── check_recent_activity.py
    │   ├── check_saved_rankings.py
    │   └── run_august_16_week_ranking.py
    └── optimization/   # 最適化・分析スクリプト
        ├── firestore_schema_optimizer.py
        └── optimized_firestore_db.py
```

## 🔧 LaTeXテストファイル

PDF生成機能の開発・テスト用ファイルです：

- **ideal_latex_test.py**: 理想的なLaTeXテンプレートのテスト
- **improved_framed_test.py**: フレーム機能改善版のテスト
- **simple_latex_test.py**: シンプルなLaTeX生成のテスト
- **step_ideal_test.py**: ステップバイステップ理想版のテスト

## 🎭 デモファイル

- **pdf_demo.py**: PDF生成機能のスタンドアロンデモ

## 🛠️ 開発用スクリプト

- **run_scraper.py**: 問題データスクレイピング用スクリプト
- **start_streamlit_ngrok.py**: ngrokを使った開発サーバー起動スクリプト

## 🔄 データ移行スクリプト

- **migrate.py**: ユーザーデータ移行スクリプト
- **migrate_data.py**: データ統合・移行処理

## 🐛 デバッグ・検証スクリプト

- **check_recent_activity.py**: 学習アクティビティ確認
- **check_saved_rankings.py**: 保存されたランキングデータ確認
- **run_august_16_week_ranking.py**: 特定週のランキング計算

## ⚡ 最適化・分析スクリプト

- **firestore_schema_optimizer.py**: Firestoreスキーマ最適化
- **optimized_firestore_db.py**: 最適化されたDB接続クラス

## ⚠️ 注意

これらのファイルは本番環境では使用されません。開発・テスト目的でのみ使用してください。
