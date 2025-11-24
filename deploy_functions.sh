#!/bin/bash
set -e

# カラー出力設定
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}=== Cloud Functions Deployment Script ===${NC}"

# プロジェクトルートディレクトリ（このスクリプトがある場所）
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$SCRIPT_DIR"

# 1. コード同期 (my_llm_app -> functions/my_llm_app)
echo -e "${GREEN}Step 1: Syncing shared code (my_llm_app)...${NC}"
rm -rf "$PROJECT_ROOT/functions/my_llm_app"
cp -R "$PROJECT_ROOT/my_llm_app" "$PROJECT_ROOT/functions/my_llm_app"

# 不要なファイルの削除
rm -rf "$PROJECT_ROOT/functions/my_llm_app/__pycache__"
rm -rf "$PROJECT_ROOT/functions/my_llm_app/.streamlit"
rm -rf "$PROJECT_ROOT/functions/my_llm_app/.DS_Store"
rm -rf "$PROJECT_ROOT/functions/my_llm_app/logs"
rm -rf "$PROJECT_ROOT/functions/my_llm_app/data"

echo "Sync complete."

# 1.5 Python仮想環境の準備 (Firebaseデプロイに必須)
if [ ! -d "$PROJECT_ROOT/functions/venv" ]; then
    echo -e "${GREEN}Step 1.5: Creating virtual environment...${NC}"
    python3.11 -m venv "$PROJECT_ROOT/functions/venv"
    source "$PROJECT_ROOT/functions/venv/bin/activate"
    pip install -r "$PROJECT_ROOT/functions/requirements.txt"
    deactivate
fi

# 2. デプロイ実行
echo -e "${GREEN}Step 2: Deploying functions...${NC}"
echo "Running: firebase deploy --only functions"

# ユーザー確認
read -p "Do you want to proceed with deployment? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]
then
    firebase deploy --only functions
else
    echo "Deployment cancelled."
fi
