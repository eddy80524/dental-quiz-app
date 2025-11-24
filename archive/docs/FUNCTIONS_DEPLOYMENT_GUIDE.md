# 高性能ランキング更新システム - デプロイガイド

このガイドでは、Cloud Functionsによる高性能ランキング更新システムのデプロイとスケジューリング設定手順を説明します。

## 🎯 システム概要

- **目的**: 毎朝3時に全ユーザーのランキングを自動更新
- **アーキテクチャ**: Cloud Functions + Cloud Scheduler + Firestore
- **特徴**: 高性能・堅牢・タイムアウト対策済み

## 📋 前提条件

1. Google Cloud Platform プロジェクトの設定完了
2. Firebase プロジェクトの設定完了
3. gcloud CLI のインストールと認証完了
4. Node.js (18以上) のインストール完了

## 🚀 1. Cloud Functions デプロイ

### ステップ 1-1: プロジェクト設定

```bash
# Firebase プロジェクトの設定
firebase use --add
firebase use [YOUR_PROJECT_ID]

# gcloud プロジェクトの設定
gcloud config set project [YOUR_PROJECT_ID]
```

### ステップ 1-2: 必要なAPIの有効化

```bash
# 必要なGoogle Cloud APIを有効化
gcloud services enable cloudfunctions.googleapis.com
gcloud services enable cloudscheduler.googleapis.com
gcloud services enable firebase.googleapis.com
gcloud services enable firestore.googleapis.com
```

### ステップ 1-3: functions ディレクトリへ移動

```bash
cd functions
```

### ステップ 1-4: 依存関係のインストール

```bash
# Node.js 依存関係のインストール
npm install

# TypeScript プロジェクトの場合はビルド
npm run build
```

### ステップ 1-5: Cloud Functions デプロイ

```bash
# ランキング更新システムをデプロイ
firebase deploy --only functions

# 特定の関数のみデプロイする場合
firebase deploy --only functions:updateRankings
firebase deploy --only functions:healthCheck
```

### ステップ 1-6: デプロイ確認

```bash
# ヘルスチェック
curl "https://asia-northeast1-[YOUR_PROJECT_ID].cloudfunctions.net/healthCheck"

# ドライランテスト
curl "https://asia-northeast1-[YOUR_PROJECT_ID].cloudfunctions.net/updateRankings?dry_run=true"
```

## ⏰ 2. Cloud Scheduler 設定

### ステップ 2-1: Cloud Scheduler API の有効化

```bash
gcloud services enable cloudscheduler.googleapis.com
```

### ステップ 2-2: スケジュールジョブの作成

```bash
# 毎朝3時（JST）に実行するジョブを作成
gcloud scheduler jobs create http dental-ranking-update \
    --schedule="0 3 * * *" \
    --uri="https://asia-northeast1-[YOUR_PROJECT_ID].cloudfunctions.net/updateRankings" \
    --http-method=GET \
    --time-zone="Asia/Tokyo" \
    --location="asia-northeast1" \
    --description="歯科国試アプリ ランキング更新 (毎日3時JST)" \
    --max-retry-attempts=3 \
    --min-backoff-duration=60s \
    --max-backoff-duration=300s
```

### ステップ 2-3: スケジュール確認

```bash
# ジョブの状態確認
gcloud scheduler jobs describe dental-ranking-update --location=asia-northeast1

# 手動実行テスト
gcloud scheduler jobs run dental-ranking-update --location=asia-northeast1
```

## 🔧 3. 設定管理

### ステップ 3-1: セットアップスクリプトの実行

```bash
# セットアップスクリプトを実行（自動化）
chmod +x setup_functions.sh
./setup_functions.sh

# スケジューラーセットアップ
chmod +x setup_scheduler.sh
./setup_scheduler.sh
```

### ステップ 3-2: 環境変数の設定（必要に応じて）

```bash
# Firebase プロジェクト設定
firebase functions:config:set ranking.batch_size=400
firebase functions:config:set ranking.timeout=540

# 設定をデプロイ
firebase deploy --only functions
```

## 📊 4. 動作確認・モニタリング

### ステップ 4-1: Cloud Console でのモニタリング

1. [Cloud Functions Console](https://console.cloud.google.com/functions)
2. [Cloud Scheduler Console](https://console.cloud.google.com/cloudscheduler)
3. [Cloud Logging Console](https://console.cloud.google.com/logs)

### ステップ 4-2: ログの確認

```bash
# Cloud Functions のログを確認
gcloud functions logs read updateRankings --limit=50

# Cloud Scheduler のログを確認
gcloud logging read "resource.type=cloud_scheduler_job" --limit=10
```

### ステップ 4-3: パフォーマンステスト

```bash
# ドライランでパフォーマンス測定
curl -w "@curl-format.txt" -s -o /dev/null \
  "https://asia-northeast1-[YOUR_PROJECT_ID].cloudfunctions.net/updateRankings?dry_run=true"

# curl-format.txt の内容:
# time_total: %{time_total}s\n
```

## 🛠️ 5. トラブルシューティング

### 一般的な問題と解決方法

#### 問題 1: デプロイエラー

```bash
# エラーログを確認
firebase debug

# 権限確認
gcloud projects get-iam-policy [YOUR_PROJECT_ID]
```

#### 問題 2: タイムアウトエラー

```bash
# 関数のタイムアウト設定を確認・変更
gcloud functions describe updateRankings --region=asia-northeast1

# タイムアウトを10分に設定
gcloud functions deploy updateRankings \
  --timeout=600s \
  --memory=1GB \
  --region=asia-northeast1
```

#### 問題 3: メモリ不足

```bash
# メモリ割り当てを増加
gcloud functions deploy updateRankings \
  --memory=2GB \
  --region=asia-northeast1
```

### ログレベルの調整

```bash
# デバッグレベルでのデプロイ
firebase deploy --only functions --debug

# Cloud Logging でのフィルタリング
resource.type="cloud_function"
resource.labels.function_name="updateRankings"
severity>=WARNING
```

## 📈 6. 運用・保守

### 定期的なメンテナンス

1. **月次**: パフォーマンス指標の確認
2. **週次**: ログエラーの確認
3. **日次**: ランキング更新状況の確認

### アラート設定

```bash
# Cloud Monitoring でアラートポリシーを作成
gcloud alpha monitoring policies create --policy-from-file=alert-policy.yaml
```

### バックアップ・復旧

```bash
# Firestore のバックアップ
gcloud firestore export gs://[BACKUP_BUCKET]/[DATE]

# 復旧
gcloud firestore import gs://[BACKUP_BUCKET]/[DATE]
```

## 🎯 7. 最適化

### パフォーマンス最適化

1. **バッチサイズの調整**: Firestore書き込みの最適化
2. **メモリ配分**: Cloud Functions のメモリ設定
3. **タイムアウト設定**: 処理時間に応じた調整

### コスト最適化

1. **実行頻度の見直し**: 必要に応じたスケジュール調整
2. **リソース配分**: メモリ・CPUの最適化
3. **ログ保持期間**: 不要なログの削除

## 📞 サポート

### エラー報告

問題が発生した場合は、以下の情報を含めて報告してください：

1. エラーメッセージ
2. 実行時間
3. Cloud Functions のログ
4. Cloud Scheduler の実行履歴

### パフォーマンス報告

```bash
# 実行時間・成功率の確認
gcloud logging read "resource.type=cloud_function AND resource.labels.function_name=updateRankings" \
  --format="table(timestamp,severity,textPayload)" \
  --limit=100
```

---

**重要**: このシステムは本番環境での利用を想定しています。テスト環境での十分な検証を行ってからデプロイしてください。
