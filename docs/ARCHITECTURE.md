# アーキテクチャ概要

## システム構成

```
┌─────────────────────┐
│  Streamlit Web App  │ (Python)
│  (my_llm_app/)      │
└──────────┬──────────┘
           │
           ├─────────────────────────────┐
           │                             │
           ▼                             ▼
┌──────────────────┐         ┌────────────────────┐
│ Firebase Auth    │         │ Cloud Functions    │ (Python)
└──────────────────┘         │ (functions/)       │
           │                 │ - getDailyQuiz     │
           │                 │ - logStudyActivity │
           │                 │ - updateRankings   │
           │                 └─────────┬──────────┘
           │                           │
           └───────────┬───────────────┘
                       ▼
            ┌────────────────────┐
            │ Firestore Database │
            │ - users            │
            │ - study_cards      │
            │ - rankings         │
            └────────────────────┘
```

## 主要コンポーネント

### 1. Streamlit Web App (`my_llm_app/`)
- **app.py**: メインエントリポイント
- **auth.py**: Firebase認証
- **firestore_db.py**: Firestore操作
- **utils.py**: SM2アルゴリズム、ユーティリティ関数
- **modules/**: 機能別モジュール
  - `practice_page.py`: 練習画面
  - `search_page.py`: 検索画面
  - `ranking_page.py`: ランキング画面

### 2. Cloud Functions (`functions/`)
- **main.py**: 全関数の実装
- **my_llm_app/**: Webアプリと共有するロジック（自動同期）

#### 実装済み関数
- `getDailyQuiz`: 復習対象カード取得
- `logStudyActivity`: 学習ログ記録・SM2更新
- `submitStudySession`: セッション記録
- `updateRankings`: ランキング更新（定期実行）
- `healthCheck`: ヘルスチェック

### 3. データベース (Firestore)

#### コレクション構造
- `users`: ユーザープロフィール
- `study_cards`: 学習カード（SM2データ含む）
- `study_sessions`: 学習セッション
- `rankings`: ランキングデータ
- `analytics_summary`: 分析サマリー

## アルゴリズム

### SM2（間隔反復学習）
ユーザーの復習スケジュールを最適化:
- Ease Factor (EF): 問題の難易度
- Interval: 次回復習までの間隔
- Quality: ユーザー自己評価 (1-4)

詳細: `my_llm_app/utils.py` の `SM2Algorithm` クラス参照

## デプロイ構成
- **Frontend**: Streamlit Cloud または ローカル実行
- **Backend**: Firebase Cloud Functions (Python 3.11)
- **Database**: Cloud Firestore
- **Auth**: Firebase Authentication

## 技術スタック
- Python 3.11
- Streamlit
- Firebase Admin SDK
- Cloud Functions for Firebase
