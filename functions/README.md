# Cloud Functions - 歯科国試アプリ ランキング更新システム

このディレクトリには、歯科国試アプリのランキングを自動更新するCloud Functions実装が含まれています。

## 概要

### 問題
- Streamlitアプリは、ユーザーがアクセスしているときのみ実行される
- ランキングの計算と更新を自動化する必要がある
- 毎日決まった時間（3:00 AM JST）に実行したい

### 解決策
- **Cloud Functions**: サーバーレスでランキング計算を実行
- **Cloud Scheduler**: 毎日3:00 AM JSTに自動実行
- **既存ロジック再利用**: `my_llm_app/modules/ranking_updater.py`を活用

## アーキテクチャ

```
Cloud Scheduler (3:00 AM JST)
    ↓ HTTP GET
Cloud Functions (updateRankings)
    ↓ 計算処理
Firestore Collections:
    ├── study_cards (読み取り)
    ├── users (読み取り)
    ├── weekly_ranking (更新)
    ├── total_ranking (更新)
    ├── mastery_ranking (更新)
    └── ranking_status (更新)
```

## ファイル構成

```
functions/
├── main.py                 # Cloud Functions メイン実装
├── requirements.txt        # Python依存関係
├── setup_functions.sh      # デプロイ用セットアップスクリプト
├── setup_scheduler.sh      # Cloud Scheduler設定スクリプト
├── README.md              # このファイル
├── package.json           # Node.js設定（Firebase CLI用）
├── tsconfig.json          # TypeScript設定（Firebase CLI用）
└── my_llm_app/           # コピーされるアプリモジュール（setup_functions.sh実行後）
    ├── modules/
    │   ├── ranking_updater.py
    │   ├── ranking_calculator.py
    │   └── ...
    ├── firestore_db.py
    └── ...
```

## セットアップ手順

### 1. 前提条件

- Firebase CLI がインストール済み
- Google Cloud SDK (gcloud) がインストール済み
- Firebase プロジェクトが作成済み
- Cloud Functions と Cloud Scheduler API が有効化済み

```bash
# Firebase CLI インストール
npm install -g firebase-tools

# Google Cloud SDK インストール
# https://cloud.google.com/sdk/docs/install

# Firebase ログイン
firebase login

# プロジェクト設定
firebase use --add
```

### 2. Functions セットアップ

```bash
# functions ディレクトリに移動
cd functions

# セットアップスクリプト実行
./setup_functions.sh
```

このスクリプトは以下を実行します：
- `my_llm_app` モジュールを functions ディレクトリにコピー
- 不要なファイル（`__pycache__`, `logs`, `archive`等）を削除
- `npm install` でNode.js依存関係をインストール
- TypeScript プロジェクトの場合は `npm run build` を実行

### 3. Firebase Functions デプロイ

```bash
# Cloud Functions をデプロイ
firebase deploy --only functions

# または特定の関数のみ
firebase deploy --only functions:updateRankings
firebase deploy --only functions:healthCheck
```

### 4. Cloud Scheduler セットアップ

```bash
# スケジューラー設定スクリプト実行
./setup_scheduler.sh
```

このスクリプトは以下を実行します：
- Cloud Scheduler API を有効化
- 毎日 3:00 AM JST に実行されるジョブを作成
- 作成されたジョブの管理コマンドを表示

## 提供される関数

### updateRankings

**URL**: `https://asia-northeast1-{PROJECT_ID}.cloudfunctions.net/updateRankings`

**機能**: ランキングデータの計算・更新

**パラメータ**:
- `force=true`: 通常の3時チェックを無視して強制実行
- `dry_run=true`: ドライラン（実際の更新は行わない）

**例**:
```bash
# 通常実行
curl 'https://asia-northeast1-{PROJECT_ID}.cloudfunctions.net/updateRankings'

# 強制実行
curl 'https://asia-northeast1-{PROJECT_ID}.cloudfunctions.net/updateRankings?force=true'

# ドライラン
curl 'https://asia-northeast1-{PROJECT_ID}.cloudfunctions.net/updateRankings?dry_run=true'
```

### healthCheck

**URL**: `https://asia-northeast1-{PROJECT_ID}.cloudfunctions.net/healthCheck`

**機能**: システムの健康状態チェック

**例**:
```bash
curl 'https://asia-northeast1-{PROJECT_ID}.cloudfunctions.net/healthCheck'
```

## 動作確認

### 1. デプロイ確認

```bash
# デプロイされた関数一覧
firebase functions:list

# ログ確認
firebase functions:log --only updateRankings
```

### 2. 手動テスト

```bash
# ヘルスチェック
curl 'https://asia-northeast1-{PROJECT_ID}.cloudfunctions.net/healthCheck'

# ドライラン実行
curl 'https://asia-northeast1-{PROJECT_ID}.cloudfunctions.net/updateRankings?dry_run=true&force=true'

# 実際の更新実行（テスト）
curl 'https://asia-northeast1-{PROJECT_ID}.cloudfunctions.net/updateRankings?force=true'
```

### 3. スケジューラー確認

```bash
# ジョブ状態確認
gcloud scheduler jobs describe dental-ranking-update --location=asia-northeast1

# 手動実行（テスト）
gcloud scheduler jobs run dental-ranking-update --location=asia-northeast1

# 実行履歴確認
gcloud scheduler jobs describe dental-ranking-update --location=asia-northeast1
```

## 更新ロジック

### データフロー

1. **ユーザープロファイル取得**: `users` と `study_cards` コレクションから
2. **学習データ読み込み**: 各ユーザーの `study_cards` を取得
3. **メトリクス計算**:
   - **週間ポイント**: 過去7日間の学習活動
   - **総合ポイント**: 累積学習ポイント
   - **習熟度スコア**: SM-2アルゴリズムによる習熟度評価
4. **ランキング保存**: 各ランキングコレクションに保存
5. **順位付与**: ポイント/スコア順にランクを設定
6. **重複クリーンアップ**: 古い/重複データを削除
7. **ステータス更新**: `ranking_status/daily` に更新情報を記録

### 更新条件

- **時間基準**: 3:00 AM JST を境とした日次更新
- **重複防止**: 同日内の重複実行を防止
- **強制実行**: `force=true` パラメータで重複防止を無視

## トラブルシューティング

### よくあるエラー

#### 1. モジュールインポートエラー

```
インポート "modules.ranking_updater" を解決できませんでした
```

**解決策**: `setup_functions.sh` を実行して `my_llm_app` をコピー

#### 2. Firebase権限エラー

```
Permission denied
```

**解決策**: 
- Cloud Functions サービスアカウントに適切な権限を付与
- Firestore Rules を確認

#### 3. Cloud Scheduler実行失敗

```
Function execution failed
```

**解決策**:
- Cloud Functions のログを確認: `firebase functions:log`
- ヘルスチェックでシステム状態を確認

### デバッグ

#### ローカル実行

```bash
cd functions
python main.py

# ブラウザで確認
# http://localhost:8080/health
# http://localhost:8080/update-rankings?dry_run=true
```

#### ログ確認

```bash
# Cloud Functions ログ
firebase functions:log --only updateRankings

# Cloud Scheduler ログ
gcloud logging read "resource.type=cloud_scheduler_job" --limit=50
```

## メンテナンス

### 定期的なタスク

1. **ログ確認**: 毎週実行ログをチェック
2. **エラー監視**: 失敗時のアラート設定
3. **パフォーマンス監視**: 実行時間の監視
4. **データ整合性**: ランキングデータの検証

### 設定変更

#### スケジュール変更

```bash
# 実行時間を変更（例：2:30 AM）
gcloud scheduler jobs update http dental-ranking-update \
    --schedule="30 2 * * *" \
    --location=asia-northeast1
```

#### タイムアウト設定

```bash
# Cloud Functions のタイムアウト延長
firebase functions:config:set runtime.timeout=540
firebase deploy --only functions
```

## セキュリティ

### アクセス制御

- Cloud Functions は認証不要のHTTPトリガー
- 必要に応じてIAMやAPI Keyによる制限を実装
- Firestore Rules でデータアクセスを制御

### 機密情報

- Firebase Admin SDK は自動的にサービスアカウント認証を使用
- 環境変数は Firebase Functions Config で管理

## 参考リンク

- [Firebase Cloud Functions ドキュメント](https://firebase.google.com/docs/functions)
- [Google Cloud Scheduler ドキュメント](https://cloud.google.com/scheduler/docs)
- [Firebase CLI リファレンス](https://firebase.google.com/docs/cli)
- [Cloud Functions Python ランタイム](https://cloud.google.com/functions/docs/concepts/python-runtime)
