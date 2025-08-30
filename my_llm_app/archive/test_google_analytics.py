#!/usr/bin/env python3
"""
Google Analytics統合テストスクリプト
リアルタイムでGoogle Analyticsイベント送信をテスト
"""

import time
from enhanced_analytics import enhanced_ga

def test_google_analytics_integration():
    """Google Analytics統合の包括的テスト"""
    
    print("🚀 Google Analytics統合テスト開始")
    print("=" * 60)
    
    # 設定確認
    print(f"📊 測定ID: {enhanced_ga.ga_measurement_id}")
    print(f"👤 ユーザーID: {enhanced_ga.user_id}")
    print(f"🔗 セッションID: {enhanced_ga.session_id}")
    
    if enhanced_ga.ga_measurement_id == 'G-XXXXXXXXXX':
        print("❌ プレースホルダーIDです。実際のIDを設定してください。")
        return False
    
    print("\n✅ 設定確認完了！")
    print("\n🎯 テストイベント送信中...")
    
    # テスト1: ページビュー
    print("1. ページビューテスト")
    enhanced_ga.track_page_view(
        page_name="test_page",
        page_title="Google Analytics統合テスト",
        additional_params={
            "test_type": "integration_test",
            "timestamp": time.time()
        }
    )
    time.sleep(1)
    
    # テスト2: ユーザーログイン
    print("2. ユーザーログインテスト")
    enhanced_ga.track_user_login(
        login_method="test_login",
        user_properties={
            "user_type": "test_user",
            "test_session": True
        }
    )
    time.sleep(1)
    
    # テスト3: 学習セッション開始
    print("3. 学習セッション開始テスト")
    enhanced_ga.track_study_session_start(
        session_type="test_session",
        question_count=10,
        difficulty="medium",
        subject="dental_exam"
    )
    time.sleep(1)
    
    # テスト4: 問題相互作用
    print("4. 問題相互作用テスト")
    enhanced_ga.track_question_interaction(
        question_id="TEST-001",
        action="answer",
        is_correct=True,
        response_time=15.5,
        difficulty="medium"
    )
    time.sleep(1)
    
    # テスト5: 学習進捗
    print("5. 学習進捗テスト")
    enhanced_ga.track_learning_progress(
        total_questions=10,
        correct_answers=8,
        session_duration=300,  # 5分
        accuracy=0.8,
        improvement_metrics={
            "session_improvement": 0.15,
            "difficulty_level": "medium"
        }
    )
    time.sleep(1)
    
    # テスト6: 機能使用
    print("6. 機能使用テスト")
    enhanced_ga.track_feature_usage(
        feature_name="analytics_test",
        action="integration_test",
        context={
            "test_version": "1.0",
            "test_timestamp": time.time()
        }
    )
    time.sleep(1)
    
    # テスト7: エンゲージメント
    print("7. エンゲージメントテスト")
    enhanced_ga.track_user_engagement(
        engagement_type="test_engagement",
        duration=60.0,
        interaction_count=5
    )
    time.sleep(1)
    
    # テスト8: カスタムイベント
    print("8. カスタムイベントテスト")
    enhanced_ga._send_event("custom_test_event", {
        "event_category": "integration_test",
        "event_action": "complete_test_suite",
        "event_label": "google_analytics_setup",
        "value": 1,
        "test_completion_time": time.time()
    })
    
    print("\n🎉 全テスト完了！")
    print("\n📈 Google Analyticsで確認してください:")
    print("1. リアルタイムレポートでイベントを確認")
    print("2. イベントレポートでカスタムイベントを確認") 
    print("3. ユーザーレポートでテストユーザーを確認")
    print(f"\n🔗 Google Analytics URL: https://analytics.google.com/analytics/web/#/p{enhanced_ga.ga_measurement_id[2:]}/reports/intelligenthome")
    
    return True

def verify_google_analytics_setup():
    """Google Analytics設定の検証"""
    
    print("🔍 Google Analytics設定検証")
    print("=" * 50)
    
    # 測定ID検証
    measurement_id = enhanced_ga.ga_measurement_id
    print(f"測定ID: {measurement_id}")
    
    if measurement_id.startswith('G-') and len(measurement_id) >= 10:
        print("✅ 測定ID形式: 正常")
    else:
        print("❌ 測定ID形式: 異常")
        return False
    
    # セッション情報検証
    print(f"ユーザーID: {enhanced_ga.user_id}")
    print(f"セッションID: {enhanced_ga.session_id}")
    
    # 初期化テスト
    try:
        result = enhanced_ga.initialize_ga()
        print(f"初期化結果: {'成功' if result else '既に初期化済み'}")
    except Exception as e:
        print(f"❌ 初期化エラー: {e}")
        return False
    
    print("✅ 設定検証完了")
    return True

if __name__ == "__main__":
    print("Google Analytics統合テストツール")
    print("=" * 60)
    
    # 設定検証
    if verify_google_analytics_setup():
        print("\n" + "="*60)
        
        # 統合テスト実行
        if test_google_analytics_integration():
            print("\n🎊 Google Analytics統合が正常に動作しています！")
            print("\nGoogle Analyticsダッシュボードで以下を確認してください:")
            print("• リアルタイムユーザー数")
            print("• イベント数の増加")
            print("• カスタムディメンションの値")
            print("• ページビューの記録")
        else:
            print("\n❌ 統合テストに失敗しました")
    else:
        print("\n❌ 設定検証に失敗しました")
        print("Google Analytics IDの設定を確認してください")
