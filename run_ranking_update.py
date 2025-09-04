#!/usr/bin/env python3
"""
ランキング更新スクリプト（手動/バッチ実行用）

Streamlitアプリ外でも起動できるようにしていますが、
Firestore 認証はアプリ側の secrets に依存しているため、
ローカル単体実行では認証がない環境だと失敗する点に注意してください。
"""

import sys


def main() -> int:
    try:
        # アプリ内の実装をそのまま呼び出し
        from my_llm_app.modules.ranking_updater import update_all_rankings
        summary = update_all_rankings()
        print(f"Ranking update completed: {summary}")
        return 0
    except Exception as e:
        print(f"Ranking update failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
