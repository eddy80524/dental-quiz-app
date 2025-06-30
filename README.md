# 国試DX-PoC

## 🎯 What is this?

これは歯科医師国家試験（厚生労働省公表問題）の問題データを  
**構造化して個人の弱点解析・最適演習を可能にするPoC（Proof of Concept）** です。

- 公開過去問をスクレイピングしてJSON化
- Gemini CLIなどのLLMで整形・タグ付け
- 個人ごとの回答ログから苦手分野を抽出して学習レポートを生成

---

## 📂 Project Structure
国試DX-PoC/
├── scraping/   # スクレイピングスクリプト (BeautifulSoupなど)
├── data/       # 構造化されたJSON, CSVファイル
├── notebooks/  # Gemini CLIの整形プロンプトや実験ログ
├── README.md   # プロジェクト概要
---

## ✅ Goals

- ✅ 厚労省公表問題を機械可読に構造化する
- ✅ 問題ごとにタグを付与し、分野別分析を可能にする
- ✅ 学習者が自動で弱点を把握できるフィードバックを生成する

---

## ⚙️ Technologies

- Python (requests, BeautifulSoup)
- Gemini CLI or LLM for text parsing
- JSON/CSV構造管理
- GitHubでのバージョン管理

---

## 🗂️ To Do (MVP)

- [ ] DentalYouthブログからのスクレイピング雛形作成
- [ ] Gemini CLIプロンプトでのJSON整形
- [ ] 選択肢の正誤判定を自動抽出
- [ ] 画像URLの保存と整理

---

## 🔖 License & Note

- このリポジトリの問題は厚生労働省公表問題の引用であり、  
  学習・研究目的でのみ使用します。

---

## ✍️ Author

- 🧑‍💻 宇津瑛人
- 📌 目的：日本の歯科教育の演習効率を技術で改善する初手のPoC

---
