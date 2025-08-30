#!/usr/bin/env python3
"""
ユーザーの学習データ抽出ユーティリティ
自己評価ログ、演習ログ、カードレベルを効率的に抽出
"""

import sys
import os
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import json

# Firebase Admin SDK を直接使用
import firebase_admin
from firebase_admin import credentials, firestore

class UserDataExtractor:
    """ユーザー学習データ抽出クラス"""
    
    def __init__(self):
        self.db = None
        self._initialize_firebase()
    
    def _parse_timestamp(self, timestamp):
        """タイムスタンプを安全にパース"""
        if timestamp is None:
            return None
        
        try:
            # datetime.datetimeオブジェクトの場合
            if hasattr(timestamp, 'year') and hasattr(timestamp, 'month'):
                # timezone-awareなdatetimeの場合はUTCに変換してからnaiveに
                if hasattr(timestamp, 'tzinfo') and timestamp.tzinfo is not None:
                    timestamp = timestamp.replace(tzinfo=None)
                return timestamp
            
            # FirestoreのDatetimeWithNanosecondsオブジェクトの場合
            if hasattr(timestamp, 'timestamp'):
                return datetime.fromtimestamp(timestamp.timestamp())  # Unix timestampからdatetimeに変換
            
            # 文字列の場合はパース
            if isinstance(timestamp, str):
                # ISO形式の場合 (T区切り)
                if 'T' in timestamp:
                    # マイクロ秒部分を除去
                    if '.' in timestamp:
                        timestamp = timestamp.split('.')[0]
                    # タイムゾーン情報を除去
                    if '+' in timestamp:
                        timestamp = timestamp.split('+')[0]
                    if 'Z' in timestamp:
                        timestamp = timestamp.replace('Z', '')
                    return datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S")
                # 通常形式の場合
                elif '.' in timestamp:
                    timestamp = timestamp[:19]  # 秒まで
                    return datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
                else:
                    return datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
            
            return None
        except Exception as e:
            print(f"タイムスタンプパースエラー: {e} (input: {timestamp}, type: {type(timestamp)})")
            return None
    
    def _initialize_firebase(self):
        """Firebase Admin SDKを初期化"""
        try:
            # すでに初期化されている場合はスキップ
            if firebase_admin._apps:
                self.db = firestore.client()
                return
            
            # デフォルトの認証を使用（ADCが設定されている場合）
            cred = credentials.ApplicationDefault()
            firebase_admin.initialize_app(cred, {
                'projectId': 'dent-ai-4d8d8'
            })
            
            self.db = firestore.client()
            print("✅ Firebase接続完了")
            
        except Exception as e:
            print(f"❌ Firebase初期化エラー: {e}")
            raise e
    
    def get_user_comprehensive_stats(self, uid, analysis_target='国試'):
        """ユーザーの包括的な学習統計を取得（practice_page用）"""
        try:
            print(f"🎯 {uid} の包括的統計を分析中...")
            
            # 基本データ取得
            evaluation_logs = self.extract_self_evaluation_logs(uid)
            practice_logs = self.extract_practice_logs(uid)
            
            # analysis_targetに応じて試験種別フィルタを設定
            exam_type_filter = None
            if analysis_target == '学士試験' or analysis_target == '学士試験問題':
                exam_type_filter = '学士試験'
            elif analysis_target == '国試' or analysis_target == '国試問題':
                exam_type_filter = '歯科国試'
            
            card_levels = self.extract_card_levels(uid, exam_type_filter=exam_type_filter)
            
            if not evaluation_logs:
                return None
            
            # 弱点分野の特定
            try:
                weak_categories = self._identify_weak_categories(evaluation_logs)
            except Exception as e:
                print(f"弱点分野特定エラー: {e}")
                weak_categories = []
            
            # 習熟度分布の計算（全問題数を考慮、analysis_targetを渡す）
            try:
                level_distribution = self._calculate_comprehensive_level_distribution(uid, card_levels.get('cards', []), analysis_target)
            except Exception as e:
                print(f"習熟度分布計算エラー: {e}")
                level_distribution = {'未学習': 0, 'レベル0': 0, 'レベル1': 0, 'レベル2': 0, 'レベル3': 0, 'レベル4': 0, 'レベル5': 0, '習得済み': 0}
            
            # 学習効率スコアの計算
            try:
                learning_efficiency = self._calculate_learning_efficiency(evaluation_logs, practice_logs)
            except Exception as e:
                print(f"学習効率計算エラー: {e}")
                learning_efficiency = 0.0
            
            # 最近の学習傾向
            try:
                recent_trends = self._analyze_recent_trends(evaluation_logs)
            except Exception as e:
                print(f"学習傾向分析エラー: {e}")
                recent_trends = {'trend': 'unknown', 'daily_average': 0}
            
            # 最終学習日を取得
            try:
                last_study_date = self._get_last_study_date(evaluation_logs)
            except Exception as e:
                print(f"最終学習日取得エラー: {e}")
                last_study_date = None
            
            # 今日の学習数を計算
            try:
                today_study_count = self._calculate_today_study_count(evaluation_logs)
            except Exception as e:
                print(f"今日の学習数計算エラー: {e}")
                today_study_count = 0
            
            return {
                'weak_categories': weak_categories,
                'level_distribution': level_distribution,
                'learning_efficiency': learning_efficiency,
                'recent_trends': recent_trends,
                'total_studied_cards': len(card_levels.get('cards', [])),
                'last_study_date': last_study_date,
                '今日の学習数': today_study_count
            }
            
        except Exception as e:
            print(f"❌ 包括的統計エラー: {e}")
            return None
    
    def _identify_weak_categories(self, evaluation_logs):
        """弱点分野を特定"""
        try:
            category_performance = defaultdict(list)
            
            for log in evaluation_logs:
                category = log.get('category', '不明')
                quality = log.get('quality', 3)
                category_performance[category].append(quality)
            
            # 平均評価が3未満の分野を弱点とする
            weak_categories = []
            for category, qualities in category_performance.items():
                if qualities:
                    avg_quality = sum(qualities) / len(qualities)
                    if avg_quality < 3.0:
                        weak_categories.append(category)
            
            return weak_categories[:5]  # 上位5分野
            
        except Exception as e:
            print(f"弱点分野特定エラー: {e}")
            return []
    
    def _calculate_level_distribution(self, cards):
        """カードレベルの分布を計算（search_page.py形式に対応）"""
        try:
            # search_page.pyで期待される詳細なレベル分布形式
            distribution = {
                '未学習': 0,
                'レベル0': 0,
                'レベル1': 0,
                'レベル2': 0,
                'レベル3': 0,
                'レベル4': 0,
                'レベル5': 0,
                '習得済み': 0
            }
            
            if not cards:
                return distribution
            
            for i, card in enumerate(cards):
                try:
                    # 詳細ログ
                    if i < 3:  # 最初の3件だけログ出力
                        print(f"[DEBUG] card[{i}] type: {type(card)}, content: {card}")
                    
                    level = None
                    mastery_status = None
                    
                    # 辞書形式の場合
                    if isinstance(card, dict):
                        level = card.get('level')
                        mastery_status = card.get('mastery_status')
                    # リスト形式の場合（エラーの原因）
                    elif isinstance(card, list):
                        print(f"[ERROR] Unexpected list card: {card}")
                        continue
                    # 文字列形式の場合
                    elif isinstance(card, str):
                        print(f"[ERROR] Unexpected string card: {card}")
                        continue
                    else:
                        print(f"[ERROR] Unknown card type: {type(card)}")
                        continue
                    
                    # levelの型チェック
                    if level is None:
                        distribution['未学習'] += 1
                        continue
                    
                    if isinstance(level, (list, dict)):
                        print(f"[ERROR] Level is {type(level)}: {level}")
                        continue
                    
                    if not isinstance(level, (int, float)):
                        print(f"[ERROR] Level is not numeric: {level} (type: {type(level)})")
                        continue
                    
                    # 詳細なレベル分類（UserDataExtractorのlevel 6は習得済み扱い）
                    if mastery_status == '習得済み' or level >= 6:
                        distribution['習得済み'] += 1
                    elif level == 5:
                        distribution['レベル5'] += 1
                    elif level == 4:
                        distribution['レベル4'] += 1
                    elif level == 3:
                        distribution['レベル3'] += 1
                    elif level == 2:
                        distribution['レベル2'] += 1
                    elif level == 1:
                        distribution['レベル1'] += 1
                    elif level == 0:
                        distribution['レベル0'] += 1
                    else:
                        # 不明なレベルは未学習として扱う
                        distribution['未学習'] += 1
                        
                except Exception as e:
                    print(f"[ERROR] カード処理エラー (index {i}): {e}")
                    continue
            
            print(f"[DEBUG] 詳細レベル分布: {distribution}")
            return distribution
            
        except Exception as e:
            print(f"[ERROR] 習熟度分布計算エラー: {e}")
            return {'未学習': 0, 'レベル0': 0, 'レベル1': 0, 'レベル2': 0, 'レベル3': 0, 'レベル4': 0, 'レベル5': 0, '習得済み': 0}

    def _calculate_comprehensive_level_distribution(self, uid, studied_cards, analysis_target='国試'):
        """全問題数を考慮した包括的レベル分布を計算"""
        try:
            # 学習済みカードの分布を計算
            studied_distribution = self._calculate_level_distribution(studied_cards)
            
            # analysis_targetに応じて適切な問題数を設定
            if analysis_target == '学士試験' or analysis_target == '学士試験問題':
                total_questions_count = 4941  # 学士試験問題数
            else:
                total_questions_count = 8576  # 国試問題数（デフォルト）
            
            studied_count = len(studied_cards)
            unstudied_count = total_questions_count - studied_count
            
            # 未学習問題数を追加
            comprehensive_distribution = studied_distribution.copy()
            comprehensive_distribution['未学習'] = unstudied_count
            
            print(f"[DEBUG] 包括的レベル分布({analysis_target}): 全問題{total_questions_count}問, 学習済み{studied_count}問, 未学習{unstudied_count}問")
            print(f"[DEBUG] 分布詳細: {comprehensive_distribution}")
            
            return comprehensive_distribution
            
        except Exception as e:
            print(f"[ERROR] 包括的習熟度分布計算エラー: {e}")
            # エラー時もanalysis_targetに応じてデフォルト値を設定
            default_total = 4941 if (analysis_target == '学士試験' or analysis_target == '学士試験問題') else 8576
            return {'未学習': default_total, 'レベル0': 0, 'レベル1': 0, 'レベル2': 0, 'レベル3': 0, 'レベル4': 0, 'レベル5': 0, '習得済み': 0}
    
    def _calculate_learning_efficiency(self, evaluation_logs, practice_logs):
        """学習効率を計算"""
        try:
            if not evaluation_logs:
                return 0.0
            
            # 最近30日間の改善率を計算
            recent_date = datetime.now() - timedelta(days=30)
            recent_evaluations = []
            
            for log in evaluation_logs:
                log_datetime = self._parse_timestamp(log.get('timestamp'))
                if log_datetime and log_datetime > recent_date:
                    recent_evaluations.append(log)
            
            if len(recent_evaluations) < 5:
                return 0.0
            
            # 評価の改善傾向を分析
            quality_scores = [log.get('quality', 3) for log in recent_evaluations[-10:]]
            if len(quality_scores) >= 2:
                improvement = (quality_scores[-1] - quality_scores[0]) / len(quality_scores)
                return max(0.0, min(1.0, 0.5 + improvement * 0.1))
            
            return 0.5  # 中立値
            
        except Exception as e:
            print(f"学習効率計算エラー: {e}")
            return 0.0
    
    def _analyze_recent_trends(self, evaluation_logs):
        """最近の学習傾向を分析"""
        try:
            recent_date = datetime.now() - timedelta(days=7)
            recent_logs = []
            
            for log in evaluation_logs:
                log_datetime = self._parse_timestamp(log.get('timestamp'))
                if log_datetime and log_datetime > recent_date:
                    recent_logs.append(log)
            
            if not recent_logs:
                return {'trend': 'no_data', 'daily_average': 0}
            
            # 日別学習量
            daily_counts = defaultdict(int)
            for log in recent_logs:
                log_datetime = self._parse_timestamp(log.get('timestamp'))
                if log_datetime:
                    date_key = log_datetime.strftime('%Y-%m-%d')
                    daily_counts[date_key] += 1
            
            avg_daily = sum(daily_counts.values()) / 7 if daily_counts else 0
            
            return {
                'trend': 'active' if avg_daily > 5 else 'moderate' if avg_daily > 2 else 'low',
                'daily_average': avg_daily,
                'total_recent': len(recent_logs)
            }
            
        except Exception as e:
            print(f"学習傾向分析エラー: {e}")
            return {'trend': 'unknown', 'daily_average': 0}
    
    def _get_last_study_date(self, evaluation_logs):
        """最後の学習日を取得"""
        try:
            if not evaluation_logs:
                return None
            
            latest_timestamp = None
            
            for log in evaluation_logs:
                log_datetime = self._parse_timestamp(log.get('timestamp'))
                if log_datetime and (latest_timestamp is None or log_datetime > latest_timestamp):
                    latest_timestamp = log_datetime
            
            if latest_timestamp:
                return latest_timestamp.strftime('%Y-%m-%d')
            
            return None
            
        except Exception as e:
            print(f"最終学習日取得エラー: {e}")
            return None

    def _calculate_today_study_count(self, evaluation_logs):
        """今日の学習数を計算"""
        try:
            if not evaluation_logs:
                return 0
            
            from datetime import datetime, date
            today = date.today()
            today_count = 0
            
            for log in evaluation_logs:
                log_datetime = self._parse_timestamp(log.get('timestamp'))
                if log_datetime and log_datetime.date() == today:
                    today_count += 1
            
            return today_count
            
        except Exception as e:
            print(f"今日の学習数計算エラー: {e}")
            return 0

    def extract_self_evaluation_logs(self, uid, start_date=None, end_date=None):
        """自己評価ログを抽出"""
        try:
            print(f"📊 {uid} の自己評価ログを抽出中...")
            
            # ユーザーのカードデータを取得
            cards_ref = self.db.collection('study_cards')
            query = cards_ref.where('uid', '==', uid)
            cards_docs = query.get()
            
            evaluation_logs = []
            
            for doc in cards_docs:
                card_data = doc.to_dict()
                question_id = card_data.get('question_id')
                history = card_data.get('history', [])
                
                for entry in history:
                    timestamp = entry.get('timestamp')
                    quality = entry.get('quality')
                    
                    if quality is not None:
                        dt = self._parse_timestamp(timestamp)
                        if not dt:
                            continue
                        
                        # 日付フィルタリング
                        if start_date and dt < start_date:
                            continue
                        if end_date and dt > end_date:
                            continue
                        
                        evaluation_logs.append({
                            'question_id': question_id,
                            'timestamp': dt,
                            'quality': quality,
                            'quality_text': self._quality_to_text(quality),
                            'is_correct': quality >= 3,  # 3以上を正解とみなす
                            'subject': card_data.get('metadata', {}).get('subject', '不明'),
                            'difficulty': card_data.get('metadata', {}).get('difficulty', 'normal')
                        })
            
            # タイムスタンプでソート
            evaluation_logs.sort(key=lambda x: x['timestamp'])
            
            print(f"✅ {len(evaluation_logs)}件の自己評価ログを抽出")
            return evaluation_logs
            
        except Exception as e:
            print(f"❌ 自己評価ログ抽出エラー: {e}")
            return []
    
    def extract_practice_logs(self, uid, start_date=None, end_date=None):
        """演習ログを抽出（日別集計含む）"""
        try:
            print(f"📈 {uid} の演習ログを抽出中...")
            
            evaluation_logs = self.extract_self_evaluation_logs(uid, start_date, end_date)
            
            if not evaluation_logs:
                return {
                    'daily_stats': {},
                    'total_sessions': 0,
                    'total_problems': 0,
                    'accuracy_rate': 0.0,
                    'quality_distribution': {},
                    'subject_stats': {}
                }
            
            # 日別統計
            daily_stats = defaultdict(lambda: {
                'problems_solved': 0,
                'correct_answers': 0,
                'quality_sum': 0,
                'sessions': 0,
                'subjects': set(),
                'first_session': None,
                'last_session': None
            })
            
            # 科目別統計
            subject_stats = defaultdict(lambda: {
                'total': 0,
                'correct': 0,
                'quality_sum': 0,
                'avg_quality': 0.0
            })
            
            # 品質分布
            quality_distribution = Counter()
            
            # セッション検出（30分以内の連続学習を1セッションとみなす）
            sessions = []
            current_session = []
            last_timestamp = None
            
            for log in evaluation_logs:
                date_key = log['timestamp'].strftime('%Y-%m-%d')
                
                # 日別統計更新
                daily_stats[date_key]['problems_solved'] += 1
                if log['is_correct']:
                    daily_stats[date_key]['correct_answers'] += 1
                daily_stats[date_key]['quality_sum'] += log['quality']
                daily_stats[date_key]['subjects'].add(log['subject'])
                
                if daily_stats[date_key]['first_session'] is None:
                    daily_stats[date_key]['first_session'] = log['timestamp']
                daily_stats[date_key]['last_session'] = log['timestamp']
                
                # 科目別統計更新
                subject = log['subject']
                subject_stats[subject]['total'] += 1
                if log['is_correct']:
                    subject_stats[subject]['correct'] += 1
                subject_stats[subject]['quality_sum'] += log['quality']
                
                # 品質分布更新
                quality_distribution[log['quality']] += 1
                
                # セッション検出
                if last_timestamp is None or (log['timestamp'] - last_timestamp).total_seconds() <= 1800:  # 30分
                    current_session.append(log)
                else:
                    if current_session:
                        sessions.append(current_session)
                    current_session = [log]
                
                last_timestamp = log['timestamp']
            
            # 最後のセッションを追加
            if current_session:
                sessions.append(current_session)
            
            # セッション数を日別統計に追加
            for session in sessions:
                if session:
                    date_key = session[0]['timestamp'].strftime('%Y-%m-%d')
                    daily_stats[date_key]['sessions'] += 1
            
            # 科目別平均品質を計算
            for subject in subject_stats:
                if subject_stats[subject]['total'] > 0:
                    subject_stats[subject]['avg_quality'] = subject_stats[subject]['quality_sum'] / subject_stats[subject]['total']
                    subject_stats[subject]['accuracy_rate'] = subject_stats[subject]['correct'] / subject_stats[subject]['total']
            
            # 日別統計の後処理
            for date_key in daily_stats:
                daily_stats[date_key]['subjects'] = list(daily_stats[date_key]['subjects'])
                if daily_stats[date_key]['problems_solved'] > 0:
                    daily_stats[date_key]['accuracy_rate'] = daily_stats[date_key]['correct_answers'] / daily_stats[date_key]['problems_solved']
                    daily_stats[date_key]['avg_quality'] = daily_stats[date_key]['quality_sum'] / daily_stats[date_key]['problems_solved']
            
            total_problems = len(evaluation_logs)
            total_correct = sum(1 for log in evaluation_logs if log['is_correct'])
            accuracy_rate = total_correct / total_problems if total_problems > 0 else 0.0
            
            practice_data = {
                'daily_stats': dict(daily_stats),
                'sessions': sessions,
                'total_sessions': len(sessions),
                'total_problems': total_problems,
                'total_correct': total_correct,
                'accuracy_rate': accuracy_rate,
                'quality_distribution': dict(quality_distribution),
                'subject_stats': dict(subject_stats),
                'study_period': {
                    'start': evaluation_logs[0]['timestamp'] if evaluation_logs else None,
                    'end': evaluation_logs[-1]['timestamp'] if evaluation_logs else None,
                    'days': len(daily_stats)
                }
            }
            
            print(f"✅ 演習ログ抽出完了: {total_problems}問、{len(sessions)}セッション、{len(daily_stats)}日間")
            return practice_data
            
        except Exception as e:
            print(f"❌ 演習ログ抽出エラー: {e}")
            return {}
    
    def extract_card_levels(self, uid, level_filter=None, studied_only=True, exam_type_filter=None):
        """カードレベルデータを抽出（試験種別分析付き）"""
        try:
            print(f"🎯 {uid} のカードレベルを抽出中...")
            
            cards_ref = self.db.collection('study_cards')
            query = cards_ref.where('uid', '==', uid)
            cards_docs = query.get()
            
            card_levels = []
            level_distribution = Counter()
            unstudied_count = 0
            exam_type_distribution = Counter()
            subject_distribution = Counter()
            
            for doc in cards_docs:
                card_data = doc.to_dict()
                question_id = card_data.get('question_id')
                sm2_data = card_data.get('sm2_data', {})
                performance = card_data.get('performance', {})
                metadata = card_data.get('metadata', {})
                history = card_data.get('history', [])
                
                # 試験種別を判定
                exam_type = self._determine_exam_type_from_question_id(question_id)
                exam_type_distribution[exam_type] += 1
                
                # 科目分布
                subject = metadata.get('subject', '不明')
                subject_distribution[subject] += 1
                
                # 試験種別フィルタリング
                if exam_type_filter and exam_type != exam_type_filter:
                    continue
                
                # 実際に学習したかどうかの判定
                has_history = len(history) > 0
                has_attempts = performance.get('total_attempts', 0) > 0
                is_studied = has_history or has_attempts
                
                # studied_onlyがTrueの場合は、学習済みカードのみを対象にする
                if studied_only and not is_studied:
                    unstudied_count += 1
                    continue
                
                level = sm2_data.get('n', 0)  # SM2アルゴリズムの復習回数
                interval = sm2_data.get('interval', 0)
                ef = sm2_data.get('ef', 2.5)
                due_date = sm2_data.get('due_date')
                
                # レベルフィルタリング
                if level_filter is not None and level != level_filter:
                    continue
                
                # 習得度判定（学習済みカードのみ）
                mastery_status = self._determine_mastery_status(level, performance, sm2_data, is_studied)
                
                card_info = {
                    'question_id': question_id,
                    'exam_type': exam_type,
                    'level': level,
                    'interval': interval,
                    'easiness_factor': ef,
                    'due_date': due_date,
                    'total_attempts': performance.get('total_attempts', 0),
                    'correct_attempts': performance.get('correct_attempts', 0),
                    'avg_quality': performance.get('avg_quality', 0.0),
                    'last_quality': performance.get('last_quality', 0),
                    'subject': subject,
                    'difficulty': metadata.get('difficulty', 'normal'),
                    'mastery_status': mastery_status,
                    'is_due': self._is_card_due(due_date) if is_studied else False,
                    'accuracy_rate': performance.get('correct_attempts', 0) / max(performance.get('total_attempts', 1), 1),
                    'is_studied': is_studied,
                    'history_count': len(history)
                }
                
                card_levels.append(card_info)
                level_distribution[level] += 1
            
            # レベル順でソート
            card_levels.sort(key=lambda x: (-x['level'], x['question_id']))
            
            # 試験種別分析
            kokushi_cards = [card for card in card_levels if card['exam_type'] == '歯科国試']
            gakushi_cards = [card for card in card_levels if card['exam_type'] == '学士試験']
            
            # 統計情報
            stats = {
                'total_cards_in_db': len(cards_docs),
                'studied_cards': len(card_levels),
                'unstudied_cards': unstudied_count,
                'exam_type_distribution': dict(exam_type_distribution),
                'subject_distribution': dict(subject_distribution),
                'level_distribution': dict(level_distribution),
                'mastery_breakdown': Counter(card['mastery_status'] for card in card_levels),
                'due_cards': sum(1 for card in card_levels if card['is_due']),
                'avg_level': sum(card['level'] for card in card_levels) / len(card_levels) if card_levels else 0,
                'high_level_cards': sum(1 for card in card_levels if card['level'] >= 4),
                'struggling_cards': sum(1 for card in card_levels if card['accuracy_rate'] < 0.5 and card['total_attempts'] >= 2),
                'perfect_cards': sum(1 for card in card_levels if card['accuracy_rate'] == 1.0 and card['total_attempts'] >= 2),
                
                # 試験種別統計
                'kokushi_stats': {
                    'total_cards': len(kokushi_cards),
                    'total_problems_available': 8576,  # 既知の国試問題数
                    'coverage_rate': len([card for card in kokushi_cards if card['exam_type'] == '歯科国試']) / 8576 if 8576 > 0 else 0,
                    'studied_cards': len([card for card in kokushi_cards if card['is_studied']]),
                    'mastery_breakdown': Counter(card['mastery_status'] for card in kokushi_cards)
                },
                'gakushi_stats': {
                    'total_cards': len(gakushi_cards),
                    'total_problems_available': 4941,  # 既知の学士問題数
                    'coverage_rate': len([card for card in gakushi_cards if card['exam_type'] == '学士試験']) / 4941 if 4941 > 0 else 0,
                    'studied_cards': len([card for card in gakushi_cards if card['is_studied']]),
                    'mastery_breakdown': Counter(card['mastery_status'] for card in gakushi_cards)
                }
            }
            
            print(f"✅ カードレベル抽出完了: 学習済み{len(card_levels)}枚、未学習{unstudied_count}枚")
            print(f"   国試: {len(kokushi_cards)}枚、学士: {len(gakushi_cards)}枚")
            return {
                'cards': card_levels,
                'stats': stats
            }
            
        except Exception as e:
            print(f"❌ カードレベル抽出エラー: {e}")
            return {'cards': [], 'stats': {}}
    
    def _determine_exam_type_from_question_id(self, question_id):
        """問題IDから試験種別を判定"""
        if not question_id:
            return "不明"
        
        import re
        
        # 歯科国試の一般的なパターン (例: 100A1, 95B10, 118A1)
        if re.match(r'\d+[A-D]\d+', question_id):
            return "歯科国試"
        
        # 学士試験のパターン (例: GAKUSHI_001, G2023_A01)
        if re.match(r'[A-Z]+\d+', question_id) or 'GAKUSHI' in question_id.upper() or question_id.startswith('G'):
            return "学士試験"
        
        # その他のパターンも含めて詳細判定
        if any(char.isalpha() for char in question_id) and any(char.isdigit() for char in question_id):
            # 数字+アルファベット+数字のパターンは国試の可能性が高い
            if re.match(r'\d+[A-Z]\d*', question_id):
                return "歯科国試"
        
        return "その他"
    
    def _quality_to_text(self, quality):
        """品質値をテキストに変換"""
        quality_map = {
            1: "× もう一度",
            2: "△ 難しい", 
            3: "○ 普通",
            4: "◎ 簡単",
            5: "◎◎ 完璧"
        }
        return quality_map.get(quality, f"不明({quality})")
    
    def _determine_mastery_status(self, level, performance, sm2_data, is_studied):
        """習得度を判定（学習済みカードのみ）"""
        if not is_studied:
            return "未学習"
        
        total_attempts = performance.get('total_attempts', 0)
        avg_quality = performance.get('avg_quality', 0)
        
        if level == 0:
            return "新規学習"
        elif level >= 4 and avg_quality >= 3.5:
            return "習得済み"
        elif level >= 2 and avg_quality >= 3.0:
            return "練習中"
        elif total_attempts >= 2 and avg_quality < 2.5:
            return "要復習"
        else:
            return "学習中"
    
    def _is_card_due(self, due_date):
        """カードが復習期限に達しているかチェック"""
        if not due_date:
            return True
        
        try:
            if hasattr(due_date, 'seconds'):
                due_dt = datetime.fromtimestamp(due_date.seconds)
            elif isinstance(due_date, str):
                due_dt = datetime.fromisoformat(due_date.replace('Z', '+00:00'))
                due_dt = due_dt.replace(tzinfo=None)
            else:
                due_dt = due_date
                if hasattr(due_dt, 'tzinfo') and due_dt.tzinfo is not None:
                    due_dt = due_dt.replace(tzinfo=None)
            
            return due_dt <= datetime.now()
        except:
            return True
    
    def _display_exam_specific_stats(self, card_data, exam_type, total_problems):
        """試験種別専用の詳細統計表示"""
        cards = card_data['cards']
        stats = card_data['stats']
        
        print(f"\n🎓 {exam_type} 詳細統計")
        print("=" * 60)
        
        # 基本統計
        studied_cards = len([card for card in cards if card['is_studied']])
        unstudied_cards = stats.get('unstudied_cards', 0)
        
        print(f"📊 基本情報:")
        print(f"  総問題数（全体）: {total_problems:,}問")
        print(f"  保有カード数: {len(cards) + unstudied_cards:,}枚")
        print(f"  学習済みカード: {studied_cards}枚")
        print(f"  未学習カード: {unstudied_cards}枚")
        print(f"  カバー率: {((len(cards) + unstudied_cards) / total_problems * 100):.1f}%")
        print(f"  学習進捗率: {(studied_cards / (len(cards) + unstudied_cards) * 100):.1f}%")
        
        if not cards:
            print(f"\n❌ {exam_type}の学習済みカードがありません")
            return
        
        # レベル分布
        level_dist = Counter(card['level'] for card in cards)
        print(f"\n📈 レベル分布:")
        for level in sorted(level_dist.keys(), reverse=True):
            count = level_dist[level]
            percentage = (count / len(cards)) * 100
            print(f"  レベル {level}: {count}枚 ({percentage:.1f}%)")
        
        # 習得度分布
        mastery_dist = Counter(card['mastery_status'] for card in cards)
        print(f"\n🎯 習得度分布:")
        for status, count in mastery_dist.most_common():
            percentage = (count / len(cards)) * 100
            print(f"  {status}: {count}枚 ({percentage:.1f}%)")
        
        # 科目分布
        subject_dist = Counter(card['subject'] for card in cards)
        print(f"\n📚 科目分布:")
        for subject, count in subject_dist.most_common():
            percentage = (count / len(cards)) * 100
            print(f"  {subject}: {count}枚 ({percentage:.1f}%)")
        
        # パフォーマンス分析
        accuracy_rates = [card['accuracy_rate'] for card in cards if card['total_attempts'] > 0]
        if accuracy_rates:
            avg_accuracy = sum(accuracy_rates) / len(accuracy_rates)
            print(f"\n📊 パフォーマンス分析:")
            print(f"  平均正解率: {avg_accuracy:.1%}")
            print(f"  完璧カード: {sum(1 for rate in accuracy_rates if rate == 1.0)}枚")
            print(f"  苦手カード: {sum(1 for rate in accuracy_rates if rate < 0.5)}枚")
        
        # 復習期限分析
        due_cards = [card for card in cards if card['is_due']]
        print(f"\n⏰ 復習期限分析:")
        print(f"  復習期限カード: {len(due_cards)}枚")
        if due_cards:
            urgent_cards = [card for card in due_cards if card['level'] >= 2]  # レベル2以上で期限切れ
            print(f"  緊急復習カード: {len(urgent_cards)}枚")
        
        # 高レベルカード詳細
        high_level_cards = [card for card in cards if card['level'] >= 4]
        if high_level_cards:
            print(f"\n🏆 習得済みカード詳細:")
            print(f"  レベル4以上: {len(high_level_cards)}枚")
            for card in high_level_cards[:5]:  # 最初の5枚を表示
                print(f"    {card['question_id']}: レベル{card['level']}, 正解率{card['accuracy_rate']:.1%}")
        
        # 要復習カード詳細
        struggling_cards = [card for card in cards if card['mastery_status'] == '要復習']
        if struggling_cards:
            print(f"\n⚠️ 要復習カード詳細:")
            print(f"  要復習カード: {len(struggling_cards)}枚")
            for card in struggling_cards[:5]:  # 最初の5枚を表示
                print(f"    {card['question_id']}: レベル{card['level']}, 正解率{card['accuracy_rate']:.1%}, 科目:{card['subject']}")
    
    def generate_learning_report(self, uid, days=30):
        """総合学習レポートを生成"""
        try:
            print(f"📋 {uid} の学習レポートを生成中（過去{days}日間）...")
            
            # 期間設定
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            # データ抽出
            evaluation_logs = self.extract_self_evaluation_logs(uid, start_date, end_date)
            practice_data = self.extract_practice_logs(uid, start_date, end_date)
            card_data = self.extract_card_levels(uid)
            
            # レポート生成
            report = {
                'user_id': uid,
                'report_period': {
                    'start': start_date.strftime('%Y-%m-%d'),
                    'end': end_date.strftime('%Y-%m-%d'),
                    'days': days
                },
                'summary': {
                    'total_problems_solved': practice_data.get('total_problems', 0),
                    'total_sessions': practice_data.get('total_sessions', 0),
                    'accuracy_rate': practice_data.get('accuracy_rate', 0.0),
                    'total_cards_in_db': card_data['stats'].get('total_cards_in_db', 0),
                    'studied_cards': card_data['stats'].get('studied_cards', 0),
                    'unstudied_cards': card_data['stats'].get('unstudied_cards', 0),
                    'mastered_cards': card_data['stats'].get('high_level_cards', 0),
                    'due_cards': card_data['stats'].get('due_cards', 0)
                },
                'evaluation_logs': evaluation_logs,
                'practice_analytics': practice_data,
                'card_levels': card_data,
                'generated_at': datetime.now().isoformat()
            }
            
            print(f"✅ 学習レポート生成完了")
            return report
            
        except Exception as e:
            print(f"❌ レポート生成エラー: {e}")
            return {}

def main():
    """メイン実行関数"""
    if len(sys.argv) < 2:
        print("使用方法: python user_data_extractor.py <user_id> [action]")
        print("action: evaluation_logs, practice_logs, card_levels, kokushi_levels, gakushi_levels, report")
        return
    
    uid = sys.argv[1]
    action = sys.argv[2] if len(sys.argv) > 2 else "report"
    
    extractor = UserDataExtractor()
    
    print(f"🎯 ユーザー: {uid}")
    print(f"📊 アクション: {action}")
    print("=" * 70)
    
    if action == "evaluation_logs":
        logs = extractor.extract_self_evaluation_logs(uid)
        print(f"\n📊 自己評価ログ（最新10件）:")
        for log in logs[-10:]:
            print(f"  {log['timestamp'].strftime('%m/%d %H:%M')} - {log['question_id'][:8]}... - {log['quality_text']}")
    
    elif action == "practice_logs":
        practice = extractor.extract_practice_logs(uid)
        print(f"\n📈 演習統計:")
        print(f"  総問題数: {practice.get('total_problems', 0)}")
        print(f"  総セッション数: {practice.get('total_sessions', 0)}")
        print(f"  正解率: {practice.get('accuracy_rate', 0):.1%}")
        print(f"  学習日数: {practice.get('study_period', {}).get('days', 0)}")
    
    elif action == "card_levels":
        card_data = extractor.extract_card_levels(uid)
        print(f"\n🎯 カードレベル統計:")
        stats = card_data['stats']
        print(f"  データベース総カード数: {stats.get('total_cards_in_db', 0)}")
        print(f"  学習済みカード数: {stats.get('studied_cards', 0)}")
        print(f"  未学習カード数: {stats.get('unstudied_cards', 0)}")
        print(f"  平均レベル: {stats.get('avg_level', 0):.1f}")
        print(f"  習得済みカード: {stats.get('high_level_cards', 0)}")
        print(f"  復習期限カード: {stats.get('due_cards', 0)}")
        print(f"  完璧カード: {stats.get('perfect_cards', 0)}")
        
        print(f"\n📊 試験種別分布:")
        exam_dist = stats.get('exam_type_distribution', {})
        for exam_type, count in exam_dist.items():
            print(f"  {exam_type}: {count}枚")
        
        print(f"\n🎓 歯科国試進捗:")
        kokushi_stats = stats.get('kokushi_stats', {})
        print(f"  保有カード: {kokushi_stats.get('total_cards', 0)}枚 / 8,576問")
        print(f"  カバー率: {kokushi_stats.get('coverage_rate', 0):.1%}")
        print(f"  学習済み: {kokushi_stats.get('studied_cards', 0)}枚")
        
        print(f"\n🎓 学士試験進捗:")
        gakushi_stats = stats.get('gakushi_stats', {})
        print(f"  保有カード: {gakushi_stats.get('total_cards', 0)}枚 / 4,941問")
        print(f"  カバー率: {gakushi_stats.get('coverage_rate', 0):.1%}")
        print(f"  学習済み: {gakushi_stats.get('studied_cards', 0)}枚")
        
        print(f"\n📈 習得度分布: {dict(stats.get('mastery_breakdown', {}))}")
    
    elif action == "kokushi_levels":
        card_data = extractor.extract_card_levels(uid, exam_type_filter="歯科国試")
        extractor._display_exam_specific_stats(card_data, "歯科国試", 8576)
    
    elif action == "gakushi_levels":
        card_data = extractor.extract_card_levels(uid, exam_type_filter="学士試験")
        extractor._display_exam_specific_stats(card_data, "学士試験", 4941)
    
    elif action == "report":
        report = extractor.generate_learning_report(uid)
        print(f"\n📋 学習レポート要約:")
        summary = report.get('summary', {})
        print(f"  問題解答数: {summary.get('total_problems_solved', 0)}")
        print(f"  学習セッション: {summary.get('total_sessions', 0)}")
        print(f"  正解率: {summary.get('accuracy_rate', 0):.1%}")
        print(f"  学習済みカード: {summary.get('studied_cards', 0)} / {summary.get('total_cards_in_db', 0)}")
        print(f"  習得カード: {summary.get('mastered_cards', 0)}")
        print(f"  復習期限カード: {summary.get('due_cards', 0)}")
        
        # JSONファイルとして保存
        filename = f"learning_report_{uid}_{datetime.now().strftime('%Y%m%d')}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2, default=str)
        print(f"  💾 詳細レポートを {filename} に保存しました")

if __name__ == "__main__":
    main()
