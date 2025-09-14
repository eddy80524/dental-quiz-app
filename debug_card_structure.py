#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
簡易的にcard_levelsのデータ構造を確認
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'my_llm_app'))

from user_data_extractor import UserDataExtractor

def check_card_levels_structure():
    uid = "wLAvgm5MPZRnNwTZgFrl9iydUR33"
    
    extractor = UserDataExtractor()
    card_levels = extractor.extract_card_levels(uid, studied_only=False, exam_type_filter="国試")
    
    print(f"card_levelsのタイプ: {type(card_levels)}")
    print(f"card_levelsの内容: {card_levels}")
    
    if isinstance(card_levels, dict):
        print(f"キー: {list(card_levels.keys())}")
        for key, value in card_levels.items():
            print(f"{key}: {type(value)} = {value}")

if __name__ == "__main__":
    check_card_levels_structure()
