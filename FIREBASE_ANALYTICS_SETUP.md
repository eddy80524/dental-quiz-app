# 歯科国家試験対策アプリ - Firebase機能フル活用設定

## 📊 実装された機能

### 1. Google Analytics統合
- **ページビュー追跡**: ログインページ、メインアプリ
- **学習セッション開始追跡**: おまかせ学習、フォールバック学習
- **問題回答追跡**: 正誤情報、品質評価
- **学習完了追跡**: セッション時間、精度

### 2. Firebase Analytics詳細ログ
- **analytics_events コレクション**: 全学習イベントの詳細記録
- **daily_analytics_summary コレクション**: 日次集計データ
- **weekly_analytics_summary コレクション**: 週次集計データ

### 3. Cloud Functions機能
- **getDailyQuiz**: 個人最適化された問題選択
- **logStudyActivity**: 学習活動のログ記録
- **aggregateDailyRankings**: 日次ランキング集計
- **resetWeeklyPoints**: 週次ポイントリセット
- **recalculateProgressDistribution**: 統計再計算

### 4. 分析機能
- **弱点分析**: 科目別の正答率分析
- **学習動向分析**: 期間別の学習パターン
- **パフォーマンス追跡**: 習熟度の変化追跡

## 🔧 設定方法

### Google Analytics設定
1. Google Analyticsでプロパティを作成
2. 測定IDを取得
3. `.streamlit/secrets.toml` の `google_analytics_id` に設定

```toml
google_analytics_id = "G-YOUR-MEASUREMENT-ID"
```

### Firebase設定
1. Firebase プロジェクトが既に設定済み: `dent-ai-4d8d8`
2. Cloud Functions デプロイ済み
3. Firestore データベース設定済み

### Cloud Functions URL修正
- Firebase v2 Functions用URL形式に対応
- リージョン指定: `asia-northeast1`
- 適切なエラーハンドリングとフォールバック機能

## 📈 データ収集詳細

### 学習イベント追跡
```javascript
// Google Analytics イベント例
gtag('event', 'study_session_start', {
  'session_type': 'auto_learning',
  'question_count': 10,
  'user_id': 'user_uid'
});

gtag('event', 'question_answered', {
  'question_id': '118A5',
  'is_correct': true,
  'quality': 4
});
```

### Firebase Analytics データ構造
```json
{
  "event_type": "study_session_start",
  "uid": "user_uid",
  "session_type": "auto_learning",
  "timestamp": "2025-08-25T15:00:00Z",
  "metadata": {
    "target": "国試",
    "question_count": 10,
    "source": "cloud_function"
  }
}
```

## 💰 コスト最適化

### 実装済み最適化
1. **バッチ処理**: 複数の分析データを一括書き込み
2. **データクリーンアップ**: 90日以上古いデータの自動削除
3. **効率的なクエリ**: 必要な期間のみデータ取得
4. **増分更新**: Firestore の Increment 機能活用

### コスト監視ポイント
- Firestore読み取り/書き込み回数
- Cloud Functions実行時間
- Google Analytics イベント数

## 🚀 使用方法

### 学習セッション開始時
```python
# アプリ内での自動実行
AnalyticsUtils.track_study_session_start("auto_learning", question_count)
FirebaseAnalytics.log_study_session_start(uid, "auto_learning", metadata)
```

### 問題回答時
```python
# 選択肢回答時
FirebaseAnalytics.log_question_answered(uid, question_id, is_correct, quality=0)

# 自己評価時
FirebaseAnalytics.log_question_answered(uid, question_id, is_correct, quality, metadata)
```

### 分析レポート取得
```python
# ユーザー分析サマリー
summary = FirebaseAnalytics.get_user_analytics_summary(uid, days=30)

# 弱点分析
weak_areas = PerformanceAnalytics.analyze_weak_areas(uid, days=30)
```

## 🔍 デバッグ情報

### Cloud Function URL確認
- 正しい形式: `https://asia-northeast1-dent-ai-4d8d8.cloudfunctions.net/getDailyQuiz`
- デバッグログで実際のURLと応答を確認可能

### エラーハンドリング
- Cloud Function エラー時は自動的にローカルフォールバック
- 詳細なエラーログ出力
- ユーザーに対する適切なフィードバック

## 📝 次のステップ

1. **Google Analytics ID設定**: 実際の測定IDに置き換え
2. **Dashboard作成**: Firebase Console でダッシュボード構築
3. **アラート設定**: 学習パフォーマンス低下時の通知
4. **A/Bテスト**: 異なる学習方法の効果測定

## 🔐 セキュリティとプライバシー

- ユーザーIDは Firebase UID を使用（匿名化）
- 個人情報は含まない問題ID、正誤情報のみ記録
- Google Analytics は GDPR 準拠設定
- データ保持期間は90日間（調整可能）
