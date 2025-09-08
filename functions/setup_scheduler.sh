#!/bin/bash

# Cloud Scheduler セットアップスクリプト
# 毎日 3:00 AM JST にランキング更新を実行するスケジュールを設定します

set -e

# 設定変数（必要に応じて変更してください）
SCHEDULE="0 3 * * *"  # 毎日3時（cron形式）
TIMEZONE="Asia/Tokyo"
JOB_NAME="dental-ranking-update"
DESCRIPTION="歯科国試アプリ ランキング更新 (毎日3時JST)"

echo "=== Cloud Scheduler セットアップ ==="

# Firebase プロジェクト ID を取得
PROJECT_ID=$(firebase use | grep -o "Now using project.*" | cut -d' ' -f4 || true)

if [ -z "$PROJECT_ID" ]; then
    echo "エラー: Firebase プロジェクト ID を取得できませんでした。"
    echo "以下のコマンドでプロジェクトを設定してください:"
    echo "  firebase use --add"
    echo "  firebase use {PROJECT_ID}"
    exit 1
fi

echo "プロジェクト ID: $PROJECT_ID"

# Function URL を構築
FUNCTION_REGION="asia-northeast1"  # Cloud Functions のデフォルトリージョン
FUNCTION_NAME="updateRankings"
FUNCTION_URL="https://${FUNCTION_REGION}-${PROJECT_ID}.cloudfunctions.net/${FUNCTION_NAME}"

echo "Function URL: $FUNCTION_URL"

# gcloud CLI が利用可能かチェック
if ! command -v gcloud >/dev/null 2>&1; then
    echo "エラー: gcloud CLI が見つかりません。"
    echo "Google Cloud SDK をインストールしてください:"
    echo "https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# プロジェクトを設定
echo "Google Cloud プロジェクトを設定中..."
gcloud config set project "$PROJECT_ID"

# Cloud Scheduler API を有効化
echo "Cloud Scheduler API を有効化中..."
gcloud services enable cloudscheduler.googleapis.com

# 既存のジョブをチェック
echo "既存のスケジュールジョブをチェック中..."
if gcloud scheduler jobs describe "$JOB_NAME" --location="asia-northeast1" >/dev/null 2>&1; then
    echo "既存のジョブが見つかりました。削除しますか? (y/N)"
    read -r response
    if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        echo "既存のジョブを削除中..."
        gcloud scheduler jobs delete "$JOB_NAME" --location="asia-northeast1" --quiet
    else
        echo "既存のジョブをそのまま使用します。"
        exit 0
    fi
fi

# スケジュールジョブを作成
echo "スケジュールジョブを作成中..."
gcloud scheduler jobs create http "$JOB_NAME" \
    --schedule="$SCHEDULE" \
    --uri="$FUNCTION_URL" \
    --http-method=GET \
    --time-zone="$TIMEZONE" \
    --location="asia-northeast1" \
    --description="$DESCRIPTION"

echo ""
echo "=== セットアップ完了 ==="
echo ""
echo "作成されたスケジュール:"
echo "  ジョブ名: $JOB_NAME"
echo "  スケジュール: $SCHEDULE ($TIMEZONE)"
echo "  URL: $FUNCTION_URL"
echo ""
echo "管理コマンド:"
echo ""
echo "1. ジョブの状態確認:"
echo "   gcloud scheduler jobs describe $JOB_NAME --location=asia-northeast1"
echo ""
echo "2. 手動実行（テスト）:"
echo "   gcloud scheduler jobs run $JOB_NAME --location=asia-northeast1"
echo ""
echo "3. ジョブの一時停止:"
echo "   gcloud scheduler jobs pause $JOB_NAME --location=asia-northeast1"
echo ""
echo "4. ジョブの再開:"
echo "   gcloud scheduler jobs resume $JOB_NAME --location=asia-northeast1"
echo ""
echo "5. ジョブの削除:"
echo "   gcloud scheduler jobs delete $JOB_NAME --location=asia-northeast1"
echo ""
echo "6. Cloud Console で確認:"
echo "   https://console.cloud.google.com/cloudscheduler?project=$PROJECT_ID"
echo ""
echo "7. Function の直接テスト:"
echo "   curl '$FUNCTION_URL?dry_run=true'"
echo ""
