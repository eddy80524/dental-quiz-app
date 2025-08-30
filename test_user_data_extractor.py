#!/usr/bin/env python3
"""
UserDataExtractorのエラーをデバッグ
"""

import sys
import os
from datetime import datetime, timedelta

# Firebase Admin SDK を直接使用
import firebase_admin
from firebase_admin import credentials, firestore

# Firebase初期化
if not firebase_admin._apps:
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred, {
        'projectId': 'dent-ai-4d8d8'
    })

from user_data_extractor import UserDataExtractor

def test_user_data_extractor():
    """UserDataExtractorのエラーをテスト"""
    uid = "wLAvgm5MPZRnNwTZgFrl9iydUR33"
    
    print(f"🔍 {uid} のUserDataExtractor分析テスト")
    
    extractor = UserDataExtractor()
    
    # 包括的統計を段階的にテスト
    print("\n🎯 包括的統計の段階的実行テスト:")
    try:
        print("1. 評価ログを取得中...")
        evaluation_logs = extractor.extract_self_evaluation_logs(uid)
        print(f"   評価ログ取得成功: {len(evaluation_logs)}件")
        
        print("2. 演習ログを取得中...")
        practice_logs = extractor.extract_practice_logs(uid)
        print(f"   演習ログ取得成功: セッション数 = レスポンス次第")
        
        print("3. カードレベルを取得中...")
        card_levels = extractor.extract_card_levels(uid)
        print(f"   カードレベル取得成功: {type(card_levels)}")
        
        print("4. 弱点分野を特定中...")
        weak_categories = extractor._identify_weak_categories(evaluation_logs)
        print(f"   弱点分野特定成功: {weak_categories}")
        
        print("5. 習熟度分布を計算中...")
        level_distribution = extractor._calculate_level_distribution(card_levels.get('cards', []))
        print(f"   習熟度分布計算成功: {level_distribution}")
        
        print("6. 学習効率を計算中...")
        learning_efficiency = extractor._calculate_learning_efficiency(evaluation_logs, practice_logs)
        print(f"   学習効率計算成功: {learning_efficiency}")
        
        print("7. 最近の傾向を分析中...")
        recent_trends = extractor._analyze_recent_trends(evaluation_logs)
        print(f"   最近の傾向分析成功: {recent_trends}")
        
        print("8. 最終学習日を取得中...")
        last_study_date = extractor._get_last_study_date(evaluation_logs)
        print(f"   最終学習日取得成功: {last_study_date}")
        
    except Exception as e:
        print(f"包括的統計取得エラー: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_user_data_extractor()
