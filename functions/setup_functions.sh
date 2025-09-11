#!/bin/bash

# Cloud Functions デプロイメント用セットアップスクリプト
# このスクリプトは、my_llm_app モジュールを functions ディレクトリにコピーして
# Cloud Functions でランキング更新機能を利用可能にします。

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
FUNCTIONS_DIR="$SCRIPT_DIR"
SOURCE_DIR="$PROJECT_ROOT/my_llm_app"

echo "=== Cloud Functions セットアップ開始 ==="
echo "プロジェクトルート: $PROJECT_ROOT"
echo "Functions ディレクトリ: $FUNCTIONS_DIR"
echo "ソースディレクトリ: $SOURCE_DIR"

# functionsディレクトリに移動
cd "$FUNCTIONS_DIR"

# 既存のmy_llm_appフォルダがあれば削除
if [ -d "my_llm_app" ]; then
    echo "既存の my_llm_app を削除中..."
    rm -rf my_llm_app
fi

# my_llm_appフォルダをコピー
echo "my_llm_app モジュールをコピー中..."
cp -r "$SOURCE_DIR" "$FUNCTIONS_DIR/"

# 不要なファイル・フォルダを削除
echo "不要なファイルを削除中..."
cd my_llm_app

# __pycache__ フォルダを削除
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete 2>/dev/null || true

# logsフォルダを削除（Cloud Functionsでは不要）
if [ -d "logs" ]; then
    rm -rf logs
fi

# archiveフォルダを削除（デプロイサイズ削減）
if [ -d "archive" ]; then
    rm -rf archive
fi

# dataフォルダ内の大きなファイルを削除（必要なもの以外）
if [ -d "data" ]; then
    echo "data フォルダ内の大きなファイルをチェック中..."
    find data -type f -size +10M -name "*.json" -exec rm {} + 2>/dev/null || true
    find data -type f -size +10M -name "*.csv" -exec rm {} + 2>/dev/null || true
fi

cd "$FUNCTIONS_DIR"

# package.jsonが存在するかチェック
if [ ! -f "package.json" ]; then
    echo "package.json が見つかりません。Firebase Functions プロジェクトを初期化してください。"
    echo "以下のコマンドを実行してください:"
    echo "  firebase init functions"
    exit 1
fi

# npm dependencies をインストール
echo "npm dependencies をインストール中..."
if command -v npm >/dev/null 2>&1; then
    npm install
else
    echo "警告: npm が見つかりません。手動で 'npm install' を実行してください。"
fi

# TypeScriptプロジェクトの場合はビルド
if [ -f "tsconfig.json" ]; then
    echo "TypeScript プロジェクトを検出しました。ビルド中..."
    if command -v npm >/dev/null 2>&1; then
        npm run build
    else
        echo "警告: npm が見つかりません。手動で 'npm run build' を実行してください。"
    fi
fi

echo ""
echo "=== セットアップ完了 ==="
echo ""
echo "次のステップ:"
echo "1. Firebase プロジェクトの設定を確認:"
echo "   firebase use --add"
echo ""
echo "2. 必要なAPIを有効化:"
echo "   gcloud services enable cloudfunctions.googleapis.com"
echo "   gcloud services enable cloudscheduler.googleapis.com"
echo "   gcloud services enable firestore.googleapis.com"
echo ""
echo "3. Cloud Functions をデプロイ:"
echo "   firebase deploy --only functions"
echo ""
echo "4. Cloud Scheduler を設定:"
echo "   ./setup_scheduler.sh"
echo ""
echo "5. 動作確認:"
echo "   curl 'https://asia-northeast1-{PROJECT_ID}.cloudfunctions.net/healthCheck'"
echo "   curl 'https://asia-northeast1-{PROJECT_ID}.cloudfunctions.net/updateRankings?dry_run=true'"
echo ""
echo "詳細なデプロイガイド: DEPLOYMENT_GUIDE.md を参照してください"
echo ""
