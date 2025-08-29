#!/bin/bash

echo "🚀 歯科国試アプリ起動スクリプト v2.0"
echo "=================================="

# スクリプトの場所を基準にプロジェクトディレクトリに移動
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "📁 作業ディレクトリ: $(pwd)"

# 仮想環境の確認とアクティベート
if [ ! -d ".venv" ]; then
    echo "❌ 仮想環境が見つかりません。作成中..."
    python3 -m venv .venv
    echo "✅ 仮想環境を作成しました"
fi

echo "🐍 仮想環境をアクティベート中..."
source .venv/bin/activate

# 依存関係のインストール確認
echo "📦 依存関係を確認中..."
pip install -q -r requirements.txt

# キャッシュクリア
echo "🧹 キャッシュクリア中..."

# Pythonキャッシュクリア
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete 2>/dev/null || true

# Streamlitキャッシュクリア
rm -rf ~/.streamlit 2>/dev/null || true
rm -rf .streamlit 2>/dev/null || true

# ポート8501の使用状況確認とプロセス終了
echo "🔍 ポート8501の使用状況を確認中..."
if lsof -ti:8501 >/dev/null 2>&1; then
    echo "⚠️  ポート8501を使用中のプロセスを終了します"
    lsof -ti:8501 | xargs kill -9 2>/dev/null || true
    sleep 2
fi

# Streamlitアプリ起動
echo "🎯 Streamlitアプリを起動中..."
echo "   URL: http://localhost:8501"
echo "   停止: Ctrl+C"
echo ""

python -m streamlit run my_llm_app/app.py --server.port 8501
