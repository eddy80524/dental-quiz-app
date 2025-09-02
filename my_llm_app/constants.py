"""
歯科国試アプリ 共通定数定義

学習レベル・習熟度レベルの統一分類システム
"""

# 統一レベル分類（学習レベル = 習熟度レベル）
UNIFIED_LEVEL_ORDER = [
    "未学習",    # 学習履歴なし
    "レベル0",   # 初回学習済み
    "レベル1",   # 基礎学習段階
    "レベル2",   # 理解段階
    "レベル3",   # 定着段階
    "レベル4",   # 習熟段階
    "レベル5",   # 高度習熟段階
    "習得済み"   # 完全習得
]

# レベル色分けマップ
LEVEL_COLORS = {
    "未学習": "#BDBDBD",      # グレー
    "レベル0": "#E3F2FD",     # 薄い青
    "レベル1": "#BBDEFB",     # 青1
    "レベル2": "#90CAF9",     # 青2
    "レベル3": "#64B5F6",     # 青3
    "レベル4": "#42A5F5",     # 青4
    "レベル5": "#2196F3",     # 青5
    "習得済み": "#4CAF50"     # 緑
}

# 習熟度表記の統一変換マップ
MASTERY_STATUS_MAPPING = {
    "マスター": "習得済み",
    "初級": "レベル1",
    "中級": "レベル3",
    "上級": "レベル5",
    "expert": "習得済み",
    "advanced": "レベル5",
    "intermediate": "レベル3",
    "beginner": "レベル1",
    "unlearned": "未学習"
}

# レベル別の重み（テストデータ生成用）
LEVEL_WEIGHTS = [0.3, 0.15, 0.15, 0.1, 0.1, 0.1, 0.05, 0.05]  # 未学習が多め

def normalize_level(level_value) -> str:
    """
    レベル値を統一分類に正規化
    
    Args:
        level_value: 数値、文字列、または辞書のレベル値
        
    Returns:
        str: 統一分類レベル
    """
    if isinstance(level_value, (int, float)):
        level_num = int(level_value)
        if level_num == 0:
            return "レベル0"
        elif level_num == 1:
            return "レベル1"
        elif level_num == 2:
            return "レベル2"
        elif level_num == 3:
            return "レベル3"
        elif level_num == 4:
            return "レベル4"
        elif level_num == 5:
            return "レベル5"
        elif level_num >= 6:
            return "習得済み"
        else:
            return "未学習"
    
    elif isinstance(level_value, str):
        # 既に統一分類の場合
        if level_value in UNIFIED_LEVEL_ORDER:
            return level_value
        # 旧表記の変換
        elif level_value in MASTERY_STATUS_MAPPING:
            return MASTERY_STATUS_MAPPING[level_value]
        else:
            return level_value  # そのまま返す
    
    else:
        return "未学習"  # デフォルト

def validate_level_consistency():
    """レベル定義の一貫性をチェック"""
    assert len(UNIFIED_LEVEL_ORDER) == 8, "レベル分類は8つ（未学習+レベル0-5+習得済み）である必要があります"
    assert len(LEVEL_COLORS) == 8, "レベル色定義は8つである必要があります"
    assert len(LEVEL_WEIGHTS) == 8, "レベル重み定義は8つである必要があります"
    
    for level in UNIFIED_LEVEL_ORDER:
        assert level in LEVEL_COLORS, f"レベル {level} の色定義が不足しています"
    
    print("✅ レベル定義の一貫性チェック完了")

if __name__ == "__main__":
    validate_level_consistency()
