#!/bin/bash
"""
週間ランキングバッチ処理の自動セットアップスクリプト

このスクリプトは以下を自動で設定します：
- crontabエントリの追加
- ログディレクトリの作成
- Python環境の確認
- 実行権限の設定
"""

# 色付きの出力用
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# スクリプトのディレクトリを取得
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/ranking_scheduler.py"
BATCH_SCRIPT="$SCRIPT_DIR/weekly_ranking_batch.py"

echo -e "${GREEN}🚀 週間ランキングバッチ処理セットアップを開始します${NC}"
echo "================================================"

# 1. Pythonの確認
echo -e "${YELLOW}📍 Python環境を確認中...${NC}"
PYTHON_PATH=$(which python3)
if [ -z "$PYTHON_PATH" ]; then
    echo -e "${RED}❌ python3が見つかりません${NC}"
    exit 1
else
    echo -e "${GREEN}✅ Python3が見つかりました: $PYTHON_PATH${NC}"
fi

# 2. 必要なファイルの確認
echo -e "${YELLOW}📍 必要なファイルを確認中...${NC}"
if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo -e "${RED}❌ ranking_scheduler.pyが見つかりません: $PYTHON_SCRIPT${NC}"
    exit 1
fi

if [ ! -f "$BATCH_SCRIPT" ]; then
    echo -e "${RED}❌ weekly_ranking_batch.pyが見つかりません: $BATCH_SCRIPT${NC}"
    exit 1
fi

echo -e "${GREEN}✅ 必要なファイルが見つかりました${NC}"

# 3. 実行権限の設定
echo -e "${YELLOW}📍 実行権限を設定中...${NC}"
chmod +x "$PYTHON_SCRIPT"
chmod +x "$BATCH_SCRIPT"
echo -e "${GREEN}✅ 実行権限を設定しました${NC}"

# 4. ログディレクトリの作成
echo -e "${YELLOW}📍 ログディレクトリを作成中...${NC}"
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"
echo -e "${GREEN}✅ ログディレクトリを作成しました: $LOG_DIR${NC}"

# 5. 接続テスト
echo -e "${YELLOW}📍 Firebase接続をテスト中...${NC}"
cd "$SCRIPT_DIR"
if $PYTHON_PATH "$PYTHON_SCRIPT" --test > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Firebase接続テスト成功${NC}"
else
    echo -e "${RED}❌ Firebase接続テストに失敗しました${NC}"
    echo "設定を続行しますか？ (y/N): "
    read -r response
    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# 6. crontabエントリの作成
echo -e "${YELLOW}📍 crontabエントリを設定中...${NC}"
CRON_ENTRY="0 3 * * * $PYTHON_PATH $PYTHON_SCRIPT"

# 既存のcrontabを確認
if crontab -l 2>/dev/null | grep -q "$PYTHON_SCRIPT"; then
    echo -e "${YELLOW}⚠️  既存のcrontabエントリが見つかりました${NC}"
    echo "既存のエントリを置き換えますか？ (y/N): "
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        # 既存のエントリを削除してから追加
        (crontab -l 2>/dev/null | grep -v "$PYTHON_SCRIPT"; echo "$CRON_ENTRY") | crontab -
        echo -e "${GREEN}✅ crontabエントリを更新しました${NC}"
    else
        echo -e "${YELLOW}⏭️  crontabエントリの更新をスキップしました${NC}"
    fi
else
    # 新しいエントリを追加
    (crontab -l 2>/dev/null; echo "$CRON_ENTRY") | crontab -
    echo -e "${GREEN}✅ crontabエントリを追加しました${NC}"
fi

# 7. 設定確認
echo ""
echo -e "${GREEN}🎉 セットアップが完了しました！${NC}"
echo "================================================"
echo -e "${YELLOW}📋 設定内容:${NC}"
echo "  • Python: $PYTHON_PATH"
echo "  • スケジューラー: $PYTHON_SCRIPT"
echo "  • バッチ処理: $BATCH_SCRIPT"
echo "  • ログディレクトリ: $LOG_DIR"
echo "  • 実行時刻: 毎日午前3時"
echo ""
echo -e "${YELLOW}📝 現在のcrontab:${NC}"
crontab -l | grep "$PYTHON_SCRIPT" || echo "  (エントリが見つかりません)"
echo ""
echo -e "${YELLOW}🔧 管理コマンド:${NC}"
echo "  • 手動実行: $PYTHON_PATH $PYTHON_SCRIPT"
echo "  • 接続テスト: $PYTHON_PATH $PYTHON_SCRIPT --test"
echo "  • ログ確認: tail -f $LOG_DIR/ranking_batch_$(date +%Y%m).log"
echo "  • crontab確認: crontab -l"
echo "  • crontab編集: crontab -e"
echo ""
echo -e "${GREEN}✨ 次回午前3時に自動実行されます！${NC}"
