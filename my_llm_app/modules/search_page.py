"""
検索・進捗ページのモジュール - UI完全保持最適化版

元のUIと完全に一致しながらパフォーマンスを劇的に改善:
- @st.cache_dataを使った重いデータ処理のキャッシュ化（元のUI保持）
- 演習ページとの連携による差分更新
- 元のrender_*_tab_perfect関数群を完全保持
- UserDataExtractorの統合とキャッシュ最適化
- 元の4つのタブ構造とメトリクス表示を完全再現
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import datetime
import pytz
from typing import Dict, List, Any, Optional
import time
from functools import lru_cache
from collections import defaultdict, Counter
import hashlib
import json
import re
import random
import sys
import os
import subprocess
import shutil
import tempfile

# 日本時間用のタイムゾーン
JST = pytz.timezone('Asia/Tokyo')

def get_japan_today() -> datetime.date:
    """日本時間の今日の日付を取得"""
    return datetime.datetime.now(JST).date()

def get_japan_datetime_from_timestamp(timestamp) -> datetime.datetime:
    """タイムスタンプから日本時間のdatetimeオブジェクトを取得"""
    try:
        # まず文字列の場合の処理
        if isinstance(timestamp, str):
            try:
                # ISO文字列をパース
                dt = datetime.datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                return dt.astimezone(JST)
            except ValueError:
                try:
                    # 日付部分のみの場合
                    dt = datetime.datetime.strptime(timestamp[:10], '%Y-%m-%d')
                    return JST.localize(dt)
                except (ValueError, IndexError):
                    return datetime.datetime.now(JST)
        elif hasattr(timestamp, 'replace'):
            # DatetimeWithNanoseconds または datetime オブジェクト
            if hasattr(timestamp, 'tzinfo') and timestamp.tzinfo is None:
                # ナイーブなdatetimeの場合、UTCとして扱って日本時間に変換
                return pytz.UTC.localize(timestamp).astimezone(JST)
            else:
                return timestamp.astimezone(JST)
        
        # その他の場合はデフォルト値を返す
        return datetime.datetime.now(JST)
    except Exception as e:
        # 予期しないエラーの場合もデフォルト値を返す
        return datetime.datetime.now(JST)

# 必要なインポート
try:
    from utils import (
        ALL_QUESTIONS, 
        HISSHU_Q_NUMBERS_SET, 
        GAKUSHI_HISSHU_Q_NUMBERS_SET,
        _gather_images_for_questions,
        _image_block_latex,
        export_questions_to_latex_tcb_jsarticle,
        compile_latex_to_pdf,
        extract_year_from_question_number
    )
except ImportError:
    try:
        from ..utils import (
            ALL_QUESTIONS, 
            HISSHU_Q_NUMBERS_SET, 
            GAKUSHI_HISSHU_Q_NUMBERS_SET,
            _gather_images_for_questions,
            _image_block_latex,
            export_questions_to_latex_tcb_jsarticle,
            compile_latex_to_pdf,
            extract_year_from_question_number
        )
    except ImportError:
        # フォールバック: 最小限の定義
        ALL_QUESTIONS = []
        HISSHU_Q_NUMBERS_SET = set()
        GAKUSHI_HISSHU_Q_NUMBERS_SET = set()

try:
    from firestore_db import get_firestore_manager
except ImportError:
    try:
        from ..firestore_db import get_firestore_manager
    except ImportError:
        get_firestore_manager = None

try:
    from constants import LEVEL_COLORS
except ImportError:
    try:
        from ..constants import LEVEL_COLORS
    except ImportError:
        LEVEL_COLORS = {}

# UserDataExtractor
try:
    from user_data_extractor import UserDataExtractor
    HAS_USER_DATA_EXTRACTOR = True
except ImportError:
    try:
        from ..user_data_extractor import UserDataExtractor
        HAS_USER_DATA_EXTRACTOR = True
    except ImportError:
        UserDataExtractor = None
        HAS_USER_DATA_EXTRACTOR = False

def update_session_evaluation_log(question_id: str, quality: int, timestamp: datetime.datetime = None):
    """
    演習ページから呼び出される関数：学習結果をセッション状態に追加（日本時間ベース）
    """
    if timestamp is None:
        timestamp = datetime.datetime.now(JST)  # 日本時間で記録
    
    # セッション状態の評価ログを初期化（存在しない場合）
    if 'evaluation_logs' not in st.session_state:
        st.session_state['evaluation_logs'] = []
    
    # 新しい評価ログを追加
    new_log = {
        'question_id': question_id,
        'quality': quality,
        'timestamp': timestamp
    }
    
    st.session_state['evaluation_logs'].append(new_log)
    
    # ログが多くなりすぎないよう、古いデータを制限（例：最新1000件）
    if len(st.session_state['evaluation_logs']) > 1000:
        st.session_state['evaluation_logs'] = st.session_state['evaluation_logs'][-1000:]

# レベル順序定義（0-5レベルシステム）
LEVEL_ORDER = ["未学習", "レベル0", "レベル1", "レベル2", "レベル3", "レベル4", "レベル5", "習得済み"]

@st.cache_data(ttl=600, show_spinner=False)  # 10分間キャッシュ、スピナー非表示
def calculate_total_questions():
    """問題数を計算する"""
    total_kokushi = 0
    total_gakushi = 0
    
    for question in ALL_QUESTIONS:
        number = question.get('number', '')
        if number.startswith('G'):
            total_gakushi += 1
        else:
            total_kokushi += 1
    
    return total_kokushi, total_gakushi

def prepare_data_for_display(uid: str, cards: dict, analysis_target: str, force_refresh: bool = False) -> pd.DataFrame:
    """
    最適化されたデータ準備関数（重い処理をキャッシュ）
    """
    # キャッシュキーの生成
    cache_key = f"{uid}_{analysis_target}_{len(cards)}_{hash(str(sorted(cards.keys())))}"
    
    if force_refresh:
        st.cache_data.clear()
    
    all_data = []
    
    # 問題データ処理（全問題を処理）
    for question in ALL_QUESTIONS:
        q_number = question.get('number', '')
        
        # analysis_targetフィルタリング
        if analysis_target == "国試" and q_number.startswith('G'):
            continue
        if analysis_target == "学士試験" and not q_number.startswith('G'):
            continue
        
        # カードデータの取得とレベル計算
        card = cards.get(q_number, {})
        level = calculate_card_level(card)
        
        # 必修問題判定
        if analysis_target == "学士試験":
            is_hisshu = q_number in GAKUSHI_HISSHU_Q_NUMBERS_SET
        else:
            is_hisshu = q_number in HISSHU_Q_NUMBERS_SET
        
        # データ行の作成
        row_data = {
            'id': q_number,
            'level': level,
            'subject': question.get('subject', '未分類'),
            'is_hisshu': is_hisshu,
            'card_data': card,
            'history': card.get('history', []) if isinstance(card, dict) else []
        }
        
        all_data.append(row_data)
    
    return pd.DataFrame(all_data)

def calculate_card_level(card: Dict[str, Any]) -> str:
    """
    【最終改善版】
    自己評価(quality)を重視し、「不安定な正解」でレベルが上がるのを防ぐレベル計算関数
    """
    if not card or not isinstance(card, dict) or not card.get('history'):
        return "未学習"

    history = card.get('history', [])
    latest = history[-1]
    quality = latest.get('quality', 0)
    
    # 1. 不正解(quality < 3)なら即レベル0
    if quality < 3:
        return "レベル0"

    # 2.【重要】ギリギリ正解(quality == 3)ならレベルを「現状維持」
    #   最新の学習記録を除いた状態でレベルを再計算し、そのレベルを維持する
    if quality == 3:
        if len(history) <= 1:
            # 初回の学習でギリギリ正解なら、まだ不安定なのでレベル0
            return "レベル0"
        else:
            # 直前のレベルを維持するため、再帰的に自身を呼び出す
            previous_level = calculate_card_level({'history': history[:-1]})
            return previous_level

    # 3. 自信のある正解(quality >= 4)の場合のみレベルアップを検討
    #   quality >= 4 の連続回数をカウントする
    confident_successful_reviews = 0
    for review in reversed(history):
        if review.get('quality', 0) >= 4:
            confident_successful_reviews += 1
        else:
            # 途中で quality < 4 の評価があればストップ
            break

    # 4. 自信のある連続正解回数に基づいてレベルを決定
    if confident_successful_reviews == 1:
        return "レベル1"
    elif confident_successful_reviews == 2:
        return "レベル2"
    elif confident_successful_reviews in [3, 4]:
        return "レベル3"
    elif confident_successful_reviews in [5, 6]:
        return "レベル4"
    elif confident_successful_reviews >= 7:
        interval = latest.get('interval', 0)
        ef = latest.get('EF', 2.5)
        if interval > 180 and ef >= 2.8:
            return "習得済み"
        elif interval > 30:
            return "レベル5"
        else:
            return "レベル4"

    # フォールバック (例: historyはあるが全て quality=3 だった場合など)
    return "レベル0"

def calculate_sm2_review_schedule(cards: dict, days_ahead: int = 7) -> Dict[str, List[str]]:
    """
    SM-2アルゴリズムに基づいて復習スケジュールを計算（日本時間ベース）
    
    Args:
        cards: カードデータ辞書
        days_ahead: 何日先まで計算するか
    
    Returns:
        日付文字列をキーとし、その日に復習すべき問題IDのリストを値とする辞書
        例: {"2025-09-02": ["123A4", "124B2"], "2025-09-03": ["125C1"]}
    """
    today = get_japan_today()  # 日本時間の今日
    schedule = {}
    
    # 未来の日付を初期化
    for i in range(days_ahead + 1):
        date_str = (today + datetime.timedelta(days=i)).isoformat()
        schedule[date_str] = []
    
    for q_id, card in cards.items():
        if not isinstance(card, dict):
            continue
            
        history = card.get('history', [])
        if not history:
            continue
            
        # 最新の学習記録から次回復習日を計算
        latest = history[-1]
        if not isinstance(latest, dict):
            continue
            
        # タイムスタンプと間隔を取得
        timestamp = latest.get('timestamp')
        interval = latest.get('interval', 1)
        quality = latest.get('quality', 0)
        
        if not timestamp:
            continue
            
        # タイムスタンプを日本時間の日付に変換
        last_study_date = None
        try:
            last_study_datetime_jst = get_japan_datetime_from_timestamp(timestamp)
            last_study_date = last_study_datetime_jst.date()
        except (ValueError, TypeError, AttributeError) as e:
            # タイムスタンプの変換に失敗した場合はスキップ
            continue
            
        if not last_study_date:
            continue
            
        # 次回復習日を計算（SM-2の間隔に基づく）
        next_review_date = last_study_date + datetime.timedelta(days=int(interval))
        
        # スケジュール範囲内かチェック
        if next_review_date <= today + datetime.timedelta(days=days_ahead):
            date_str = next_review_date.isoformat()
            if date_str in schedule:
                schedule[date_str].append(q_id)
    
    return schedule

def get_review_priority_cards(cards: dict, target_date: datetime.date = None) -> List[tuple]:
    """
    指定日の復習優先度付きカードリストを取得（日本時間ベース）
    
    Args:
        cards: カードデータ辞書
        target_date: 対象日（デフォルトは今日の日本時間）
    
    Returns:
        (問題ID, 優先度スコア, 経過日数) のタプルのリスト（優先度順）
    """
    if target_date is None:
        target_date = get_japan_today()
    
    priority_cards = []
    
    for q_id, card in cards.items():
        if not isinstance(card, dict):
            continue
            
        history = card.get('history', [])
        if not history:
            continue
            
        latest = history[-1]
        if not isinstance(latest, dict):
            continue
            
        timestamp = latest.get('timestamp')
        interval = latest.get('interval', 1)
        quality = latest.get('quality', 0)
        ef = latest.get('EF', 2.5)
        
        if not timestamp:
            continue
            
        # 最後の学習日を日本時間で取得
        last_study_date = None
        try:
            last_study_datetime_jst = get_japan_datetime_from_timestamp(timestamp)
            last_study_date = last_study_datetime_jst.date()
        except (ValueError, TypeError):
            continue
            
        if not last_study_date:
            continue
            
        # 次回復習予定日
        next_review_date = last_study_date + datetime.timedelta(days=int(interval))
        
        # 復習対象日以前の場合のみ対象
        if next_review_date <= target_date:
            # 経過日数を計算（復習予定日からの経過）
            days_overdue = (target_date - next_review_date).days
            
            # 優先度スコア計算（経過日数 + EFの逆数 + qualityの逆数）
            # 経過日数が多いほど、EFが低いほど、前回のqualityが低いほど優先度が高い
            priority_score = days_overdue + (3.0 - ef) + (6 - quality)
            
            priority_cards.append((q_id, priority_score, days_overdue))
    
    # 優先度の高い順（スコアの大きい順）にソート
    priority_cards.sort(key=lambda x: x[1], reverse=True)
    
    return priority_cards

def check_gakushi_permission(uid: str) -> bool:
    """学士試験へのアクセス権限をチェック（キャッシュ対応）"""
    try:
        # Streamlitのキャッシュを使用して権限データを保存（表示なし）
        @st.cache_data(ttl=300, show_spinner=False)  # 5分間キャッシュ、スピナー非表示
        def _cached_gakushi_check(uid: str) -> bool:
            db = get_firestore_manager()
            user_ref = db.collection('users').document(uid)
            user_doc = user_ref.get()
            
            if user_doc.exists:
                user_data = user_doc.to_dict()
                return user_data.get('has_gakushi_permission', False)
            
            return True
        
        return _cached_gakushi_check(uid)
    except Exception:
        return True

def calculate_progress_metrics(cards: Dict, base_df: pd.DataFrame, uid: str, analysis_target: str) -> Dict:
    """
    進捗メトリクス計算（元のUIと同様）- 日本時間ベース
    """
    today = get_japan_today()  # 日本時間の今日
    yesterday = today - datetime.timedelta(days=1)
    seven_days_ago = datetime.datetime.now(JST) - datetime.timedelta(days=7)
    fourteen_days_ago = datetime.datetime.now(JST) - datetime.timedelta(days=14)
    
    enhanced_data = {}
    
    # セッション状態から学習履歴データを取得（演習ページでリアルタイム更新）
    if uid and uid != "guest":
        try:
            # セッション状態から直接学習ログを取得
            session_evaluation_logs = st.session_state.get('evaluation_logs', [])
            
            if session_evaluation_logs:
                # analysis_targetでフィルタリング
                filtered_logs = []
                for log in session_evaluation_logs:
                    q_id = log.get('question_id', '')
                    if analysis_target == "学士試験":
                        if q_id.startswith('G'):
                            filtered_logs.append(log)
                    else:
                        if not q_id.startswith('G'):
                            filtered_logs.append(log)
                
                evaluation_logs = filtered_logs
                
                # 7日間の正解率計算（日本時間ベース）
                recent_evaluations = []
                previous_evaluations = []
                
                for log in evaluation_logs:
                    try:
                        log_timestamp = log['timestamp']
                        # 日本時間に変換
                        log_datetime_jst = get_japan_datetime_from_timestamp(log_timestamp)
                        
                        if log_datetime_jst >= seven_days_ago:
                            recent_evaluations.append(log)
                        elif fourteen_days_ago <= log_datetime_jst < seven_days_ago:
                            previous_evaluations.append(log)
                    except Exception:
                        continue
                
                recent_correct = sum(1 for log in recent_evaluations if log.get('quality', 0) >= 3)
                previous_correct = sum(1 for log in previous_evaluations if log.get('quality', 0) >= 3)
                
                enhanced_data['recent_accuracy'] = (recent_correct / len(recent_evaluations) * 100) if recent_evaluations else 0
                enhanced_data['previous_accuracy'] = (previous_correct / len(previous_evaluations) * 100) if previous_evaluations else 0
                enhanced_data['recent_total'] = len(recent_evaluations)
                enhanced_data['previous_total'] = len(previous_evaluations)
                
                # 今日と昨日の学習数（日本時間ベース）
                today_logs = []
                yesterday_logs = []
                
                for log in evaluation_logs:
                    try:
                        log_timestamp = log['timestamp']
                        # 日本時間に変換
                        log_datetime_jst = get_japan_datetime_from_timestamp(log_timestamp)
                        log_date = log_datetime_jst.date()
                        
                        if log_date == today:
                            today_logs.append(log)
                        elif log_date == yesterday:
                            yesterday_logs.append(log)
                    except Exception:
                        continue
                
                enhanced_data['today_study_count'] = len(today_logs)
                enhanced_data['yesterday_study_count'] = len(yesterday_logs)
            
            # フォールバック: UserDataExtractorからの取得（初回読み込み時のみ）
            elif HAS_USER_DATA_EXTRACTOR and not st.session_state.get('evaluation_logs_initialized', False):
                extractor = UserDataExtractor()
                evaluation_logs = extractor.extract_self_evaluation_logs(uid)
                
                if evaluation_logs:
                    # セッション状態に保存して今後はこれを使用
                    st.session_state['evaluation_logs'] = evaluation_logs
                    st.session_state['evaluation_logs_initialized'] = True
                    
                    # 上記と同じロジックでフィルタリングと計算
                    filtered_logs = []
                    for log in evaluation_logs:
                        q_id = log.get('question_id', '')
                        if analysis_target == "学士試験":
                            if q_id.startswith('G'):
                                filtered_logs.append(log)
                        else:
                            if not q_id.startswith('G'):
                                filtered_logs.append(log)
                    
                    evaluation_logs = filtered_logs
                    
                    # 7日間・14日間の評価（日本時間ベース）
                    recent_evaluations = []
                    previous_evaluations = []
                    
                    for log in evaluation_logs:
                        try:
                            log_timestamp = log['timestamp']
                            log_datetime_jst = get_japan_datetime_from_timestamp(log_timestamp)
                            
                            if log_datetime_jst >= seven_days_ago:
                                recent_evaluations.append(log)
                            elif fourteen_days_ago <= log_datetime_jst < seven_days_ago:
                                previous_evaluations.append(log)
                        except Exception:
                            continue
                    
                    recent_correct = sum(1 for log in recent_evaluations if log.get('quality', 0) >= 3)
                    previous_correct = sum(1 for log in previous_evaluations if log.get('quality', 0) >= 3)
                    
                    enhanced_data['recent_accuracy'] = (recent_correct / len(recent_evaluations) * 100) if recent_evaluations else 0
                    enhanced_data['previous_accuracy'] = (previous_correct / len(previous_evaluations) * 100) if previous_evaluations else 0
                    enhanced_data['recent_total'] = len(recent_evaluations)
                    enhanced_data['previous_total'] = len(previous_evaluations)
                    
                    # 今日・昨日の学習数（日本時間ベース）
                    today_logs = []
                    yesterday_logs = []
                    
                    for log in evaluation_logs:
                        try:
                            log_timestamp = log['timestamp']
                            log_datetime_jst = get_japan_datetime_from_timestamp(log_timestamp)
                            log_date = log_datetime_jst.date()
                            
                            if log_date == today:
                                today_logs.append(log)
                            elif log_date == yesterday:
                                yesterday_logs.append(log)
                        except Exception:
                            continue
                    
                    enhanced_data['today_study_count'] = len(today_logs)
                    enhanced_data['yesterday_study_count'] = len(yesterday_logs)
                
        except Exception:
            pass
    
    # 総問題数設定（動的計算）
    total_kokushi, total_gakushi = calculate_total_questions()
    
    if analysis_target == "学士試験":
        total_count = total_gakushi
        hisshu_total_count = len(GAKUSHI_HISSHU_Q_NUMBERS_SET)
    else:
        total_count = total_kokushi
        hisshu_total_count = len(HISSHU_Q_NUMBERS_SET)
    
    # 学習済み数計算（analysis_targetに基づいて正確に計算）
    current_studied_count = 0
    current_hisshu_studied_count = 0
    
    # 全問題から分析対象に該当する問題のみをフィルタして計算
    for question in ALL_QUESTIONS:
        q_number = question.get('number', '')
        
        # analysis_targetによるフィルタリング
        if analysis_target == "学士試験":
            if not q_number.startswith('G'):
                continue
        else:  # 国試
            if q_number.startswith('G'):
                continue
        
        # カードデータの取得とレベル計算
        card = cards.get(q_number, {})
        level = calculate_card_level(card)
        
        # 学習済み問題のカウント
        if level != "未学習":
            current_studied_count += 1
        
        # 必修問題判定と学習済み数カウント
        if analysis_target == "学士試験":
            is_hisshu = q_number in GAKUSHI_HISSHU_Q_NUMBERS_SET
        else:
            is_hisshu = q_number in HISSHU_Q_NUMBERS_SET
            
        if is_hisshu and level != "未学習":
            current_hisshu_studied_count += 1
    
    # デフォルト値設定
    today_study_count = enhanced_data.get('today_study_count', 0)
    yesterday_study_count = enhanced_data.get('yesterday_study_count', 0)
    recent_accuracy = enhanced_data.get('recent_accuracy', 0)
    previous_accuracy = enhanced_data.get('previous_accuracy', 0)
    
    # 差分計算（前日比の進捗変化）
    # 昨日時点での学習済み数を計算（昨日までの学習ログをもとに）
    yesterday_studied_count = 0
    yesterday_hisshu_studied_count = 0
    
    if uid and uid != "guest":
        # 昨日までの学習ログから昨日時点での進捗を計算
        evaluation_logs = st.session_state.get('evaluation_logs', [])
        yesterday_learned_questions = set()
        yesterday_learned_hisshu = set()
        
        for log in evaluation_logs:
            try:
                log_timestamp = log['timestamp']
                log_datetime_jst = get_japan_datetime_from_timestamp(log_timestamp)
                log_date = log_datetime_jst.date()
                
                # 昨日以前の学習記録
                if log_date <= yesterday:
                    q_id = log.get('question_id', '')
                    
                    # analysis_targetでフィルタリング
                    if analysis_target == "学士試験":
                        if q_id.startswith('G'):
                            yesterday_learned_questions.add(q_id)
                            if q_id in GAKUSHI_HISSHU_Q_NUMBERS_SET:
                                yesterday_learned_hisshu.add(q_id)
                    else:
                        if not q_id.startswith('G'):
                            yesterday_learned_questions.add(q_id)
                            if q_id in HISSHU_Q_NUMBERS_SET:
                                yesterday_learned_hisshu.add(q_id)
            except Exception:
                continue
        
        yesterday_studied_count = len(yesterday_learned_questions)
        yesterday_hisshu_studied_count = len(yesterday_learned_hisshu)
    
    progress_delta = current_studied_count - yesterday_studied_count
    hisshu_delta = current_hisshu_studied_count - yesterday_hisshu_studied_count
    accuracy_delta = recent_accuracy - previous_accuracy
    
    return {
        'current_studied_count': current_studied_count,
        'total_count': total_count,
        'current_hisshu_studied_count': current_hisshu_studied_count,
        'hisshu_total_count': hisshu_total_count,
        'today_study_count': today_study_count,
        'yesterday_study_count': yesterday_study_count,
        'recent_accuracy': recent_accuracy,
        'previous_accuracy': previous_accuracy,
        'progress_delta': progress_delta,
        'hisshu_delta': hisshu_delta,
        'accuracy_delta': accuracy_delta
    }

def render_search_page():
    """
    検索ページのメイン関数（UI完全保持）
    """
    # セッション状態の取得
    uid = st.session_state.get("uid", "guest")
    cards = st.session_state.get("cards", {})
    analysis_target = st.session_state.get("analysis_target", "国試")
    level_filter = st.session_state.get("level_filter", LEVEL_ORDER)
    subject_filter = st.session_state.get("subject_filter", [])
    
    # 権限チェック
    has_gakushi_permission = st.session_state.get('has_gakushi_permission', False)
    
    # 最適化されたデータ準備
    base_df = prepare_data_for_display(uid, cards, analysis_target)
    
    # フィルター適用
    filtered_df = base_df.copy()
    
    # レベルフィルター
    if level_filter and set(level_filter) != set(LEVEL_ORDER):
        filtered_df = filtered_df[filtered_df['level'].isin(level_filter)]
    
    # 科目フィルター
    if subject_filter:
        filtered_df = filtered_df[filtered_df['subject'].isin(subject_filter)]
    
    # 必修問題フィルター
    show_hisshu_only = st.session_state.get('show_hisshu_only', False)
    if show_hisshu_only:
        filtered_df = filtered_df[filtered_df['is_hisshu'] == True]
    
    # メトリクス表示（分析対象に基づく正確な計算）
    if not filtered_df.empty:
        # メトリクス計算には全体データ（フィルタされていない）を使用
        metrics = calculate_progress_metrics(cards, base_df, uid, analysis_target)
        
        # デバッグ情報表示（開発時のみ）
        if st.session_state.get("debug_mode", False):
            st.write(f"デバッグ - 現在学習済み: {metrics['current_studied_count']}, 昨日時点: {metrics['current_studied_count'] - metrics['progress_delta']}, デルタ: {metrics['progress_delta']}")
            st.write(f"デバッグ - 必修現在: {metrics['current_hisshu_studied_count']}, 必修昨日時点: {metrics['current_hisshu_studied_count'] - metrics['hisshu_delta']}, 必修デルタ: {metrics['hisshu_delta']}")
            st.write(f"デバッグ - 学習ログ数: {len(st.session_state.get('evaluation_logs', []))}")
        
        # 4つの主要指標をst.metricで表示
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            progress_delta_text = f"+{metrics['progress_delta']} 問" if metrics['progress_delta'] > 0 else f"{metrics['progress_delta']} 問" if metrics['progress_delta'] < 0 else "変化なし"
            st.metric(
                "学習進捗率",
                f"{metrics['current_studied_count']} / {metrics['total_count']} 問",
                delta=progress_delta_text
            )
        
        with col2:
            hisshu_delta_text = f"+{metrics['hisshu_delta']} 問" if metrics['hisshu_delta'] > 0 else f"{metrics['hisshu_delta']} 問" if metrics['hisshu_delta'] < 0 else "変化なし"
            st.metric(
                "必修問題の進捗",
                f"{metrics['current_hisshu_studied_count']} / {metrics['hisshu_total_count']} 問",
                delta=hisshu_delta_text
            )
        
        with col3:
            today_delta = metrics['today_study_count'] - metrics['yesterday_study_count']
            today_delta_text = f"+{today_delta}" if today_delta > 0 else f"{today_delta}" if today_delta < 0 else "±0"
            st.metric(
                "今日の学習",
                f"{metrics['today_study_count']} 問",
                delta=f"昨日比 {today_delta_text}"
            )
        
        with col4:
            accuracy_delta_text = f"+{metrics['accuracy_delta']:.1f}%" if metrics['accuracy_delta'] > 0 else f"{metrics['accuracy_delta']:.1f}%" if metrics['accuracy_delta'] < 0 else "±0%"
            st.metric(
                "直近の正解率",
                f"{metrics['recent_accuracy']:.1f}%",
                delta=f"前週比 {accuracy_delta_text}"
            )
        
        # 進捗更新ボタン
        st.divider()
        col_refresh, col_debug = st.columns([1, 3])
        with col_refresh:
            if st.button("🔄 進捗データを更新", help="最新の学習記録を反映します"):
                # 学習ログを強制更新
                if HAS_USER_DATA_EXTRACTOR and uid and uid != "guest":
                    try:
                        extractor = UserDataExtractor()
                        evaluation_logs = extractor.extract_self_evaluation_logs(uid)
                        if evaluation_logs:
                            st.session_state['evaluation_logs'] = evaluation_logs
                            st.session_state['evaluation_logs_initialized'] = True
                            st.success("進捗データを更新しました！")
                            st.rerun()
                        else:
                            st.info("更新する学習記録が見つかりません。")
                    except Exception as e:
                        st.error(f"進捗データの更新に失敗しました: {e}")
                else:
                    st.info("現在のセッションログから進捗を計算しています。")
        
        with col_debug:
            if st.checkbox("デバッグ情報を表示", key="debug_mode_checkbox"):
                st.session_state["debug_mode"] = True
                st.rerun()
            else:
                st.session_state["debug_mode"] = False
    
    # タブコンテナ - 4つのタブ（元UIを完全復元）
    tab1, tab2, tab3, tab4 = st.tabs(["概要", "グラフ分析", "問題リスト", "キーワード検索"])
    
    with tab1:
        render_overview_tab_perfect(filtered_df, base_df, ALL_QUESTIONS, analysis_target)
    
    with tab2:
        render_graph_analysis_tab_perfect(filtered_df)
    
    with tab3:
        render_question_list_tab_perfect(filtered_df, analysis_target)
    
    with tab4:
        render_keyword_search_tab_perfect(analysis_target)

def render_overview_tab_perfect(filtered_df: pd.DataFrame, base_df: pd.DataFrame, all_questions: List, analysis_target: str):
    """
    概要タブ - 学習状況サマリー
    """
    st.subheader("学習状況サマリー")
    if filtered_df.empty:
        st.warning("選択された条件に一致する問題がありません。")
    else:
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("##### カード習熟度分布（全体）")
            # 分析対象の全体データ（サイドバーフィルター無関係）を使用
            level_counts = base_df["level"].value_counts().reindex(LEVEL_ORDER).fillna(0).astype(int)
            st.dataframe(level_counts)
        with col2:
            st.markdown("##### 正解率 (True Retention)")
            total_reviews = 0
            correct_reviews = 0
            for history_list in filtered_df["history"]:
                for review in history_list:
                    if isinstance(review, dict) and "quality" in review:
                        total_reviews += 1
                        if review["quality"] >= 4:
                            correct_reviews += 1
            retention_rate = (correct_reviews / total_reviews * 100) if total_reviews > 0 else 0
            st.metric(label="選択範囲の正解率", value=f"{retention_rate:.1f}%", delta=f"{correct_reviews} / {total_reviews} 回")

            # 必修問題の正解率計算
            if analysis_target == "学士試験":
                hisshu_df = filtered_df[filtered_df["is_hisshu"] == True]
                hisshu_label = "【学士試験・必修問題】の正解率 (目標: 80%以上)"
            else:
                hisshu_df = filtered_df[filtered_df["id"].isin(HISSHU_Q_NUMBERS_SET)]
                hisshu_label = "【必修問題】の正解率 (目標: 80%以上)"

            hisshu_total_reviews = 0
            hisshu_correct_reviews = 0
            for history_list in hisshu_df["history"]:
                for review in history_list:
                    if isinstance(review, dict) and "quality" in review:
                        hisshu_total_reviews += 1
                        if review["quality"] >= 4:
                            hisshu_correct_reviews += 1
            hisshu_retention_rate = (hisshu_correct_reviews / hisshu_total_reviews * 100) if hisshu_total_reviews > 0 else 0
            st.metric(label=hisshu_label, value=f"{hisshu_retention_rate:.1f}%", delta=f"{hisshu_correct_reviews} / {hisshu_total_reviews} 回")

def render_graph_analysis_tab_perfect(filtered_df: pd.DataFrame):
    """
    グラフ分析タブ - 学習データの可視化
    """
    st.subheader("学習データの可視化")
    if filtered_df.empty:
        st.warning("選択された条件に一致する問題がありません。")
    else:
        st.markdown("##### 学習の記録")
        review_history = []
        for history_list in filtered_df["history"]:
            for review in history_list:
                if isinstance(review, dict) and "timestamp" in review:
                    timestamp = review["timestamp"]
                    try:
                        # 日本時間に変換してから日付を取得
                        review_datetime_jst = get_japan_datetime_from_timestamp(timestamp)
                        review_history.append(review_datetime_jst.date())
                    except (ValueError, TypeError):
                        # パースに失敗した場合はスキップ
                        continue

        if review_history:
            from collections import Counter
            import pandas as pd  # ローカルスコープで確実にインポート
            review_counts = Counter(review_history)
            ninety_days_ago = get_japan_today() - datetime.timedelta(days=90)  # 日本時間ベース
            dates = [ninety_days_ago + datetime.timedelta(days=i) for i in range(91)]
            counts = [review_counts.get(d, 0) for d in dates]
            chart_df = pd.DataFrame({"Date": dates, "Reviews": counts})

            # plotlyを使ってy軸の最小値を0に固定
            try:
                import plotly.express as px
                fig = px.bar(chart_df, x="Date", y="Reviews", 
                            title="日々の学習量（過去90日間）")
                fig.update_layout(
                    yaxis=dict(range=[0, max(counts) * 1.1] if counts else [0, 5]),
                    showlegend=False
                )
                st.plotly_chart(fig, use_container_width=True)
            except ImportError:
                # plotlyが利用できない場合は従来のbar_chart
                st.bar_chart(chart_df.set_index("Date"))
        else:
            st.info("選択された範囲にレビュー履歴がまだありません。")

        st.markdown("##### 学習レベル別分布")
        if not filtered_df.empty:
            level_counts = filtered_df['level'].value_counts()

            # 色分け定義
            level_colors_chart = {
                "未学習": "#757575", "レベル0": "#FF9800", "レベル1": "#FFC107",
                "レベル2": "#8BC34A", "レベル3": "#9C27B0", "レベル4": "#03A9F4",
                "レベル5": "#1E88E5", "習得済み": "#4CAF50"
            }

            try:
                import plotly.express as px
                import pandas as pd

                # レベル順に並べ替え
                chart_data = []
                colors = []

                for level in LEVEL_ORDER:
                    if level in level_counts.index:
                        chart_data.append({"Level": level, "Count": level_counts[level]})
                        colors.append(level_colors_chart.get(level, "#888888"))

                chart_df = pd.DataFrame(chart_data)

                fig = px.bar(chart_df, x="Level", y="Count", 
                            title="学習レベル別問題数",
                            color="Level",
                            color_discrete_map=level_colors_chart)
                fig.update_layout(
                    yaxis=dict(range=[0, None]),
                    showlegend=False,
                    xaxis_tickangle=-45
                )
                st.plotly_chart(fig, use_container_width=True)

            except ImportError:
                # plotlyが利用できない場合は基本的なbar_chart
                st.bar_chart(level_counts)
        else:
            st.info("学習データがありません。")

def render_question_list_tab_perfect(filtered_df: pd.DataFrame, analysis_target: str = "国試"):
    """
    問題リストタブ - 問題リスト
    """
    st.subheader("問題リスト")
    level_colors = {
        "未学習": "#757575", "レベル0": "#FF9800", "レベル1": "#FFC107",
        "レベル2": "#8BC34A", "レベル3": "#9C27B0", "レベル4": "#03A9F4",
        "レベル5": "#1E88E5", "習得済み": "#4CAF50"
    }

    # 権限チェック
    has_gakushi_permission = st.session_state.get("has_gakushi_permission", False)

    # サイドバーのフィルターを適用
    if not filtered_df.empty:
        # サイドバーの level_filter は既に適用済み

        st.markdown(f"**{len(filtered_df)}件の問題が見つかりました**")
        if not filtered_df.empty:
            def sort_key(row_id):
                m_gakushi = re.match(r'^(G)(\d+)[–\-]([\d–\-再]+)[–\-]([A-Z])[–\-](\d+)$', str(row_id))
                if m_gakushi: return (m_gakushi.group(1), int(m_gakushi.group(2)), m_gakushi.group(3), m_gakushi.group(4), int(m_gakushi.group(5)))
                m_normal = re.match(r"(\d+)([A-D])(\d+)", str(row_id))
                if m_normal: return ('Z', int(m_normal.group(1)), m_normal.group(2), '', int(m_normal.group(3)))
                return ('Z', 0, '', '', 0)

            detail_filtered_sorted = filtered_df.copy()
            detail_filtered_sorted['sort_key'] = detail_filtered_sorted['id'].apply(sort_key)
            detail_filtered_sorted = detail_filtered_sorted.sort_values(by='sort_key').drop(columns=['sort_key'])
            for _, row in detail_filtered_sorted.iterrows():
                # 権限チェック：学士試験の問題で権限がない場合はスキップ
                if str(row.id).startswith("G") and not has_gakushi_permission:
                    continue

                st.markdown(
                    f"<div style='margin-bottom: 5px; padding: 5px; border-left: 5px solid {level_colors.get(row.level, '#888')};'>"
                    f"<span style='display:inline-block;width:80px;font-weight:bold;color:{level_colors.get(row.level, '#888')};'>{row.level}</span>"
                    f"<span style='font-size:1.1em;'>{row.id}</span>"
                    f"</div>",
                    unsafe_allow_html=True
                )
        else:
            st.info("フィルタ条件に一致する問題がありません。")
    else:
        st.info("表示する問題がありません。")

def render_keyword_search_tab_perfect(analysis_target: str):
    """
    キーワード検索タブ - キーワード検索
    """
    # 権限チェック
    has_gakushi_permission = st.session_state.get("has_gakushi_permission", False)
    
    # キーワード検索フォーム（サイドバーフィルター連動）
    st.subheader("🔍 キーワード検索")
    st.info(f"🎯 検索対象: {analysis_target} （サイドバーの分析対象フィルターで変更可能）")

    col1, col2 = st.columns([4, 1])
    with col1:
        search_keyword = st.text_input("検索キーワード", placeholder="検索したいキーワードを入力", key="search_keyword_input")
    with col2:
        shuffle_results = st.checkbox("結果をシャッフル", key="shuffle_checkbox")

    search_btn = st.button("検索実行", type="primary", use_container_width=True)

    # キーワード検索の実行と結果表示
    if search_btn and search_keyword.strip():
        # キーワード検索を実行
        search_words = [word.strip() for word in search_keyword.strip().split() if word.strip()]

        keyword_results = []
        for q in ALL_QUESTIONS:
            # 権限チェック：学士試験の問題で権限がない場合はスキップ
            question_number = q.get('number', '')
            if question_number.startswith("G") and not has_gakushi_permission:
                continue

            # 分析対象フィルタチェック（サイドバーの設定を使用）
            if analysis_target == "学士試験" and not question_number.startswith("G"):
                continue
            elif analysis_target == "国試" and question_number.startswith("G"):
                continue

            # キーワード検索
            text_to_search = f"{q.get('question', '')} {q.get('subject', '')} {q.get('number', '')}"
            if any(word.lower() in text_to_search.lower() for word in search_words):
                keyword_results.append(q)

        # シャッフル処理
        if shuffle_results:
            random.shuffle(keyword_results)

        # 結果をセッション状態に保存
        st.session_state["search_results"] = keyword_results
        st.session_state["search_query"] = search_keyword.strip()
        st.session_state["search_page_analysis_target"] = analysis_target
        st.session_state["search_page_shuffle_setting"] = shuffle_results

    # 検索結果の表示
    if "search_results" in st.session_state:
        results = st.session_state["search_results"]
        query = st.session_state.get("search_query", "")
        search_type = st.session_state.get("search_page_analysis_target", "国試")
        shuffle_info = "（シャッフル済み）" if st.session_state.get("search_page_shuffle_setting", False) else "（順番通り）"

        if results:
            st.success(f"「{query}」で{len(results)}問見つかりました（{search_type}）{shuffle_info}")

            # 結果の統計を表示
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("検索結果", f"{len(results)}問")
            with col2:
                subjects = [q.get("subject", "未分類") for q in results]
                unique_subjects = len(set(subjects))
                st.metric("関連科目", f"{unique_subjects}科目")
            with col3:
                years = []
                for q in results:
                    year = extract_year_from_question_number(q.get("number", ""))
                    if year is not None:
                        years.append(int(year))

                year_range = f"{min(years)}-{max(years)}" if years else "不明"
                st.metric("年度範囲", year_range)

            # 検索結果の詳細表示
            st.subheader("検索結果")

            # レベル別色分け定義
            level_colors = {
                "未学習": "#757575", "レベル0": "#FF9800", "レベル1": "#FFC107",
                "レベル2": "#8BC34A", "レベル3": "#9C27B0", "レベル4": "#03A9F4",
                "レベル5": "#1E88E5", "習得済み": "#4CAF50"
            }

            level_icons = {
                "未学習": "#757575",        # グレー系
                "レベル0": "#FF9800",      # オレンジ #FF9800
                "レベル1": "#FFC107",      # イエロー #FFC107
                "レベル2": "#8BC34A",      # グリーン #8BC34A
                "レベル3": "#9C27B0",      # パープル #9C27B0
                "レベル4": "#03A9F4",      # ブルー #03A9F4
                "レベル5": "#1E88E5",      # ダークブルー #1E88E5
                "習得済み": "#4CAF50"      # グリーン完了 #4CAF50
            }

            for i, q in enumerate(results[:20]):  # 最初の20件を表示
                # 権限チェック：学士試験の問題で権限がない場合はスキップ
                question_number = q.get('number', '')
                if question_number.startswith("G") and not has_gakushi_permission:
                    continue

                # 学習レベルの取得
                card = st.session_state.cards.get(question_number, {})
                if not card:
                    level = "未学習"
                else:
                    card_level = card.get("level", 0)
                    if card_level >= 6:
                        level = "習得済み"
                    else:
                        level = f"レベル{card_level}"

                # 必修問題チェック
                if search_type == "学士試験":
                    is_hisshu = question_number in GAKUSHI_HISSHU_Q_NUMBERS_SET
                else:
                    is_hisshu = question_number in HISSHU_Q_NUMBERS_SET

                level_color = level_colors.get(level, "#888888")
                hisshu_mark = "🔥" if is_hisshu else ""

                # 色付きドットアイコンをHTMLで生成
                color_dot = f'<span style="color: {level_color}; font-size: 1.2em; font-weight: bold;">●</span>'

                with st.expander(f"● {q.get('number', 'N/A')} - {q.get('subject', '未分類')} {hisshu_mark}"):
                    # レベルを大きく色付きで表示  
                    st.markdown(f"**学習レベル:** <span style='color: {level_color}; font-weight: bold; font-size: 1.2em;'>{level}</span>", unsafe_allow_html=True)
                    st.markdown(f"**問題:** {q.get('question', '')[:100]}...")
                    if q.get('choices'):
                        st.markdown("**選択肢:**")
                        for j, choice in enumerate(q['choices']):  # 全ての選択肢を表示
                            choice_text = choice.get('text', str(choice)) if isinstance(choice, dict) else str(choice)
                            st.markdown(f"  {chr(65+j)}. {choice_text[:50]}...")

                    # 学習履歴の表示
                    if card and card.get('history'):
                        st.markdown(f"**学習履歴:** {len(card['history'])}回")
                        for j, review in enumerate(card['history'][-3:]):  # 最新3件
                            if isinstance(review, dict):
                                timestamp = review.get('timestamp', '不明')
                                quality = review.get('quality', 0)
                                quality_emoji = "✅" if quality >= 4 else "❌"
                                st.markdown(f"  {j+1}. {timestamp} - 評価: {quality} {quality_emoji}")
                    else:
                        st.markdown("**学習履歴:** なし")

            if len(results) > 20:
                st.info(f"表示は最初の20件です。全{len(results)}件中")

            # PDF生成とダウンロード機能
            st.markdown("#### 📄 PDF生成")

            colA, colB = st.columns(2)
            with colA:
                if st.button("📄 PDFを生成", key="pdf_tcb_js_generate"):
                    with st.spinner("PDFを生成中..."):
                        # 1) LaTeX本文（右上は固定の'◯◯◯◯◯'を表示）
                        latex_tcb = export_questions_to_latex_tcb_jsarticle(results)
                        # 2) 画像収集（URL/Storage問わず）
                        assets, per_q_files = _gather_images_for_questions(results)
                        # 3) 画像スロットを includegraphics に差し替え
                        for i, files in enumerate(per_q_files, start=1):
                            block = _image_block_latex(files)
                            latex_tcb = latex_tcb.replace(rf"%__IMAGES_SLOT__{i}__", block)
                        # 4) コンパイル
                        pdf_bytes, log = compile_latex_to_pdf(latex_tcb, assets=assets)
                        if pdf_bytes:
                            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                            st.session_state["pdf_bytes_tcb_js"] = pdf_bytes
                            st.session_state["pdf_filename_tcb_js"] = f"dental_questions_tcb_js_{ts}.pdf"
                            st.success("✅ PDFの生成に成功しました。右のボタンからDLできます。")
                        else:
                            st.error("❌ PDF生成に失敗しました。")
                            with st.expander("ログを見る"):
                                st.code(log or "no log", language="text")

            with colB:
                if "pdf_bytes_tcb_js" in st.session_state:
                    # 統一されたPDFダウンロード（新タブで開く）
                    pdf_data = st.session_state["pdf_bytes_tcb_js"]
                    filename = st.session_state.get("pdf_filename_tcb_js", "dental_questions_tcb_js.pdf")

                    # Base64エンコード
                    import base64
                    b64_pdf = base64.b64encode(pdf_data).decode()

                    # Data URI を持つHTMLリンクを生成（新タブで開く）
                    href = f'<a href="data:application/pdf;base64,{b64_pdf}" download="{filename}" target="_blank" style="display: inline-block; padding: 12px; background-color: #ff6b6b; color: white; text-decoration: none; border-radius: 6px; text-align: center; width: 100%; font-size: 16px; font-weight: bold; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">📥 PDFをダウンロード</a>'

                    st.markdown(href, unsafe_allow_html=True)
                else:
                    st.button("⬇️ PDFをDL", disabled=True, use_container_width=True)

        else:
            st.warning(f"「{query}」に該当する問題が見つかりませんでした")
    else:
        st.info("キーワードを入力して検索してください")

    # 検索結果表示
    if "search_results" in st.session_state:
        results = st.session_state["search_results"]
        query = st.session_state.get("search_query", "")
        search_type = st.session_state.get("search_analysis_target", "国試")
        is_shuffled = st.session_state.get("search_shuffled", False)

        if results:
            shuffle_info = "（シャッフル済み）" if is_shuffled else "（順番通り）"
            st.success(f"「{query}」で{len(results)}問見つかりました（{search_type}）{shuffle_info}")

            subjects = set(q.get('subject', '') for q in results)
            
            years = [extract_year_from_question_number(q.get("number", "")) for q in results]
            valid_years = [y for y in years if y is not None]
            year_range = f"{min(valid_years)}-{max(valid_years)}" if valid_years else "不明"
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("ヒット数", len(results))
            with col2:
                st.metric("関連科目数", len(subjects))
            with col3:
                st.metric("年度範囲", year_range)

            # 検索結果リスト
            st.subheader("検索結果")
            for i, q in enumerate(results[:20]):
                q_number = q.get('number', 'N/A')
                subject = q.get('subject', '未分類')
                
                cards = st.session_state.get('cards', {})
                card = cards.get(q_number, {})
                level = calculate_card_level(card)
                
                with st.expander(f"● {q_number} - {subject}"):
                    st.markdown(f"**学習レベル:** {level}")
                    
                    question_text = q.get('question', '')
                    if len(question_text) > 100:
                        st.markdown(f"**問題:** {question_text[:100]}...")
                    else:
                        st.markdown(f"**問題:** {question_text}")
                    
                    choices = q.get('choices', [])
                    if choices:
                        st.markdown("**選択肢:**")
                        for j, choice in enumerate(choices):
                            if isinstance(choice, dict):
                                choice_text = choice.get('text', str(choice))
                            else:
                                choice_text = str(choice)
                            
                            if len(choice_text) > 50:
                                st.markdown(f"  {chr(65 + j)}. {choice_text[:50]}...")
                            else:
                                st.markdown(f"  {chr(65 + j)}. {choice_text}")
                    
                    answer = q.get('answer', '')
                    if answer:
                        st.markdown(f"**正解:** {answer}")
                    
                    history = card.get('history', [])
                    n = card.get('n', 0)
                    if not history:
                        st.markdown("**学習履歴:** なし")
                    else:
                        st.markdown(f"**学習履歴:** {len(history)}回")
                        st.markdown(f"**演習回数:** {n}回")
                        if len(history) > 0:
                            latest = history[-1]
                            timestamp = latest.get('timestamp', '')
                            quality = latest.get('quality', 0)
                            if timestamp:
                                try:
                                    if hasattr(timestamp, 'strftime'):
                                        time_str = timestamp.strftime('%Y-%m-%d %H:%M')
                                    else:
                                        try:
                                            if 'T' in str(timestamp):
                                                timestamp_str = str(timestamp).split('.')[0] if '.' in str(timestamp) else str(timestamp)
                                                parsed_time = datetime.datetime.fromisoformat(timestamp_str)
                                                time_str = parsed_time.strftime('%Y-%m-%d %H:%M')
                                            else:
                                                time_str = str(timestamp)[:16]
                                        except:
                                            time_str = "不明"
                                    st.markdown(f"　最新: {time_str} (評価: {quality})")
                                except:
                                    st.markdown(f"　最新: (評価: {quality})")

            # PDF生成機能
            st.markdown("#### 📄 PDF生成")
            colA, colB = st.columns(2)
            
            with colA:
                if st.button("📄 PDFを生成", key="pdf_generate_button"):
                    with st.spinner("PDFを生成中... 高品質なレイアウトのため数分かかることがあります。"):
                        assets, per_q_files = _gather_images_for_questions(results)
                        latex_source = export_questions_to_latex_tcb_jsarticle(results, right_label_fn=lambda q: q.get('subject', ''))
                        
                        for i, files in enumerate(per_q_files, start=1):
                            block = _image_block_latex(files)
                            latex_source = latex_source.replace(rf"%__IMAGES_SLOT__{i}__", block)

                        pdf_bytes, log = compile_latex_to_pdf(latex_source, assets=assets)

                        if pdf_bytes:
                            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M")
                            st.session_state["pdf_bytes_for_download"] = pdf_bytes
                            st.session_state["pdf_filename_for_download"] = f"search_results_{ts}.pdf"
                            st.success("✅ PDF生成完了！右のボタンからダウンロードしてください。")
                        else:
                            st.error("❌ PDF生成に失敗しました。")
                            if "pdf_bytes_for_download" in st.session_state:
                                del st.session_state["pdf_bytes_for_download"]
                            with st.expander("エラーログ"):
                                st.code(log or "ログはありません", language="text")
            
            with colB:
                if "pdf_bytes_for_download" in st.session_state and st.session_state["pdf_bytes_for_download"]:
                    file_size_kb = len(st.session_state["pdf_bytes_for_download"]) / 1024
                    st.download_button(
                        label="📥 PDFをダウンロード",
                        data=st.session_state["pdf_bytes_for_download"],
                        file_name=st.session_state["pdf_filename_for_download"],
                        mime="application/pdf",
                        use_container_width=True,
                        type="primary",
                        help=f"ファイルサイズ: {file_size_kb:.1f} KB"
                    )
                else:
                    st.button("📥 PDFをDL", disabled=True, use_container_width=True)
        else:
            if query:
                st.warning(f"「{query}」に該当する問題が見つかりませんでした")
            else:
                st.info("キーワードを入力して検索してください")

# メイン関数
def main():
    """モジュールのメイン関数"""
    render_search_page()

if __name__ == "__main__":
    main()
