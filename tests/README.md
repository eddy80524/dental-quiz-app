# 📁 テストファイル

このディレクトリには、開発・テスト用のファイルが整理されています。

## 📂 構成

```
tests/
├── latex/          # LaTeX PDF生成のテストファイル
│   ├── ideal_latex_test.py
│   ├── improved_framed_test.py
│   ├── improved_latex_test.py
│   ├── jsarticle_test.py
│   ├── simple_latex_template.py
│   ├── simple_latex_test.py
│   └── step_ideal_test.py
└── scripts/        # 開発用スクリプト
    ├── run_scraper.py
    └── start_streamlit_ngrok.py
```

## 🔧 LaTeXテストファイル

PDF生成機能の開発・テスト用ファイルです：

- **ideal_latex_test.py**: 理想的なLaTeXテンプレートのテスト
- **improved_framed_test.py**: フレーム機能改善版のテスト
- **simple_latex_test.py**: シンプルなLaTeX生成のテスト
- **step_ideal_test.py**: ステップバイステップ理想版のテスト

## 🛠️ 開発用スクリプト

- **run_scraper.py**: 問題データスクレイピング用スクリプト
- **start_streamlit_ngrok.py**: ngrokを使った開発サーバー起動スクリプト

## ⚠️ 注意

これらのファイルは本番環境では使用されません。開発・テスト目的でのみ使用してください。
