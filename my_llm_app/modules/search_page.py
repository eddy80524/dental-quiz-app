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
import math
import pytz
from typing import Dict, List, Any, Optional, Tuple
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


def inject_search_page_styles():
    """iOSライクな柔らかなUIスタイルを常時適用"""
    st.markdown(
        """
        <style>
        :root {
            --ios-bg-start: #f5f7ff;
            --ios-bg-end: #eef1ff;
            --ios-card-bg: rgba(255, 255, 255, 0.92);
            --ios-card-border: rgba(255, 255, 255, 0.55);
            --ios-accent: #5b7fff;
            --ios-accent-soft: rgba(91, 127, 255, 0.18);
        }

        div[data-testid="stAppViewContainer"] {
            background: linear-gradient(180deg, var(--ios-bg-start) 0%, var(--ios-bg-end) 100%);
        }

        section[data-testid="stSidebar"] {
            background: rgba(255, 255, 255, 0.85) !important;
            backdrop-filter: blur(14px);
        }

        .block-container {
            padding-top: 1.2rem;
            padding-bottom: 3rem;
        }

        .ios-hero {
            border-radius: 28px;
            padding: 30px;
            margin-bottom: 1.2rem;
            background: linear-gradient(135deg, #5b7fff 0%, #7f9bff 45%, #a2b7ff 100%);
            color: #ffffff;
            box-shadow: 0 20px 40px rgba(91, 127, 255, 0.25);
            position: relative;
            overflow: hidden;
        }

        .ios-hero::after {
            content: "";
            position: absolute;
            top: -40%;
            right: -30%;
            width: 55%;
            height: 120%;
            background: rgba(255, 255, 255, 0.18);
            filter: blur(0px);
            transform: rotate(25deg);
        }

        .ios-hero__badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 6px 14px;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.3);
            font-size: 0.85rem;
            font-weight: 500;
            letter-spacing: 0.02em;
        }

        .ios-hero__title {
            font-size: 2rem;
            font-weight: 700;
            margin: 12px 0 6px;
        }

        .ios-hero__subtitle {
            font-size: 1rem;
            opacity: 0.92;
            max-width: 520px;
            line-height: 1.7;
        }

        .ios-section-title {
            font-size: 1.08rem;
            font-weight: 600;
            color: #1c1c1e;
            margin-bottom: 0.4rem;
            letter-spacing: 0.01em;
        }

        .ios-hero__chips {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            margin-top: 18px;
        }

        .ios-chip {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding: 6px 14px;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.3);
            color: #ffffff;
            font-size: 0.82rem;
            font-weight: 500;
            letter-spacing: 0.01em;
        }

        div[data-testid="stMetric"] {
            border-radius: 20px;
            padding: 16px 18px;
            background: var(--ios-card-bg);
            border: 1px solid var(--ios-card-border);
            box-shadow: 0 12px 32px rgba(15, 23, 42, 0.08);
        }

        div[data-testid="stMetric"] > div:nth-child(1) {
            color: #636366;
            font-size: 0.85rem;
            font-weight: 500;
        }

        div[data-testid="stMetricValue"] {
            color: #1c1c1e;
            font-size: 1.6rem;
            font-weight: 600;
        }

        div[data-testid="stMetricDelta"] {
            font-size: 0.85rem;
            font-weight: 500;
        }

        div[data-testid="stSlider"] {
            padding: 14px 18px 10px;
            border-radius: 20px;
            background: var(--ios-card-bg);
            border: 1px solid var(--ios-card-border);
            box-shadow: 0 12px 32px rgba(15, 23, 42, 0.07);
        }

        div[data-testid="stSlider"] label {
            font-weight: 600;
            color: #1c1c1e;
        }

        div[data-testid="stSlider"] span {
            color: #636366;
        }

        .stDataFrame {
            border-radius: 20px;
            overflow: hidden;
            box-shadow: 0 12px 32px rgba(15, 23, 42, 0.07);
        }

        .stCaption {
            color: #3a3a3c;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

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


def _extract_card_review_metadata(
    q_id: str,
    card: Dict[str, Any],
    today: Optional[datetime.date] = None
) -> Optional[Dict[str, Any]]:
    """レビュー計画作成用にカードのメタ情報を抽出"""
    if not isinstance(card, dict):
        return None

    history = card.get('history')
    if not history:
        return None

    latest = history[-1]
    if not isinstance(latest, dict):
        return None

    timestamp = latest.get('timestamp')
    interval = latest.get('interval', 0)
    quality = latest.get('quality', 0)
    ef = latest.get('EF', 2.5)

    if not timestamp:
        return None

    try:
        last_study_date = get_japan_datetime_from_timestamp(timestamp).date()
    except Exception:
        return None

    try:
        interval_days = int(interval) if interval is not None else 0
    except (ValueError, TypeError):
        interval_days = 0

    next_review_date = last_study_date + datetime.timedelta(days=max(interval_days, 0))

    today = today or get_japan_today()
    level = calculate_card_level(card)
    is_mature = level in {"レベル5", "習得済み"} or interval_days >= 45

    return {
        'id': q_id,
        'level': level,
        'interval': interval_days,
        'quality': quality if isinstance(quality, (int, float)) else 0,
        'ef': float(ef) if isinstance(ef, (int, float)) else 2.5,
        'next_review_date': next_review_date,
        'last_study_date': last_study_date,
        'is_mature': is_mature,
        'today': today
    }


def build_balanced_review_plan(
    cards: Dict[str, Any],
    daily_target: int = 120,
    horizon_days: int = 7,
    hisshu_set: Optional[set] = None,
    mature_daily_quota_factor: float = 0.25
) -> Dict[str, Any]:
    """膨らみがちな復習量を平準化するレビュー計画を生成"""
    if daily_target <= 0:
        daily_target = 1

    today = get_japan_today()
    hisshu_set = hisshu_set or set()

    backlog_non_mature: List[Dict[str, Any]] = []
    backlog_mature: List[Dict[str, Any]] = []
    future_non_mature: Dict[datetime.date, List[Dict[str, Any]]] = defaultdict(list)
    future_mature: Dict[datetime.date, List[Dict[str, Any]]] = defaultdict(list)

    considered_total = 0

    for q_id, card in cards.items():
        metadata = _extract_card_review_metadata(q_id, card, today)
        if not metadata:
            continue

        considered_total += 1
        entry = {
            'id': q_id,
            'due_date': metadata['next_review_date'],
            'quality': metadata['quality'],
            'ef': metadata['ef'],
            'level': metadata['level'],
            'is_mature': metadata['is_mature'],
            'is_hisshu': q_id in hisshu_set
        }

        if metadata['next_review_date'] <= today:
            if metadata['is_mature']:
                backlog_mature.append(entry)
            else:
                backlog_non_mature.append(entry)
        else:
            target_map = future_mature if metadata['is_mature'] else future_non_mature
            target_map[metadata['next_review_date']].append(entry)

    backlog_non_mature.sort(key=lambda x: (x['due_date'], x['quality'], x['ef']))
    backlog_mature.sort(key=lambda x: (x['due_date'], x['quality'], x['ef']))

    initial_backlog = len(backlog_non_mature) + len(backlog_mature)

    non_mature_dates = sorted(future_non_mature.keys())
    mature_dates = sorted(future_mature.keys())
    non_idx = 0
    mature_idx = 0

    days: List[Dict[str, Any]] = []
    served_total = 0

    for offset in range(max(horizon_days, 0)):
        current_date = today + datetime.timedelta(days=offset)

        while non_idx < len(non_mature_dates) and non_mature_dates[non_idx] <= current_date:
            due_date = non_mature_dates[non_idx]
            backlog_non_mature.extend(future_non_mature.pop(due_date, []))
            non_idx += 1
        while mature_idx < len(mature_dates) and mature_dates[mature_idx] <= current_date:
            due_date = mature_dates[mature_idx]
            backlog_mature.extend(future_mature.pop(due_date, []))
            mature_idx += 1

        backlog_non_mature.sort(key=lambda x: (x['due_date'], x['quality'], x['ef']))
        backlog_mature.sort(key=lambda x: (x['due_date'], x['quality'], x['ef']))

        assigned: List[Dict[str, Any]] = []
        hisshu_count = 0
        mature_count = 0

        take_non = min(len(backlog_non_mature), daily_target)
        if take_non > 0:
            assigned.extend(backlog_non_mature[:take_non])
            hisshu_count += sum(1 for item in backlog_non_mature[:take_non] if item['is_hisshu'])
            mature_count += sum(1 for item in backlog_non_mature[:take_non] if item['is_mature'])
            backlog_non_mature = backlog_non_mature[take_non:]

        remaining_slots = daily_target - len(assigned)
        mature_quota = max(2, int(daily_target * mature_daily_quota_factor))

        if remaining_slots > 0 and backlog_mature:
            take_mature = min(remaining_slots, len(backlog_mature))
            if len(assigned) > 0 and take_mature > mature_quota:
                take_mature = mature_quota

            if take_mature > 0:
                assigned.extend(backlog_mature[:take_mature])
                hisshu_count += sum(1 for item in backlog_mature[:take_mature] if item['is_hisshu'])
                mature_count += take_mature
                backlog_mature = backlog_mature[take_mature:]

        # それでも枠が余り、未成熟カードが無い場合は成熟カードで埋める
        remaining_slots = daily_target - len(assigned)
        if remaining_slots > 0 and not backlog_non_mature and backlog_mature:
            take_additional = min(remaining_slots, len(backlog_mature))
            assigned.extend(backlog_mature[:take_additional])
            hisshu_count += sum(1 for item in backlog_mature[:take_additional] if item['is_hisshu'])
            mature_count += take_additional
            backlog_mature = backlog_mature[take_additional:]

        served_total += len(assigned)
        overdue_served = sum(1 for item in assigned if item['due_date'] < current_date)
        due_today_served = sum(1 for item in assigned if item['due_date'] == current_date)

        days.append({
            'date': current_date,
            'count': len(assigned),
            'overdue_served': overdue_served,
            'due_today_served': due_today_served,
            'hisshu_count': hisshu_count,
            'mature_count': mature_count,
            'card_examples': [item['id'] for item in assigned[:10]],
            'remaining_backlog': len(backlog_non_mature) + len(backlog_mature)
        })

    remaining_future = sum(len(v) for v in future_non_mature.values()) + sum(len(v) for v in future_mature.values())
    backlog_after_horizon = len(backlog_non_mature) + len(backlog_mature)

    outstanding = backlog_after_horizon + remaining_future
    projected_clear_days = horizon_days + math.ceil(outstanding / daily_target) if outstanding > 0 else horizon_days

    return {
        'today': today,
        'daily_target': daily_target,
        'considered_total': considered_total,
        'served_total': served_total,
        'overdue_total': initial_backlog,
        'backlog_start': initial_backlog,
        'backlog_after_horizon': backlog_after_horizon,
        'remaining_future': remaining_future,
        'projected_clear_days': projected_clear_days,
        'days': days
    }

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

    inject_search_page_styles()

    today_date = get_japan_today()
    today_label = today_date.strftime("%Y/%m/%d (%a)")
    daily_limit = st.session_state.get('daily_review_limit')
    plan_registry = st.session_state.get('review_plan_registry', {})
    active_plan = plan_registry.get(analysis_target)
    today_plan = None
    if active_plan and active_plan.get('days'):
        for day in active_plan['days']:
            day_date = day.get('date')
            if isinstance(day_date, datetime.date) and day_date == today_date:
                today_plan = day
                break
            if isinstance(day_date, str) and day_date == today_date.isoformat():
                today_plan = day
                break

    chip_html = []
    if isinstance(daily_limit, int):
        chip_html.append(f"<span class='ios-chip'>復習上限 {daily_limit}枚</span>")
    chip_html.append(f"<span class='ios-chip'>対象 {analysis_target}</span>")
    if today_plan and isinstance(today_plan.get('count'), int):
        chip_html.append(f"<span class='ios-chip'>今日の復習 {today_plan['count']}枚</span>")

    st.markdown(
        f"""
        <div class="ios-hero">
            <span class="ios-hero__badge">進捗ビュー</span>
            <div class="ios-hero__title">学習ダッシュボード</div>
            <div class="ios-hero__subtitle">検索・進捗ページでは、演習データをもとに復習量の偏りや達成状況を確認できます。今日 ({today_label}) の指標をチェックして、次の一手を決めましょう。</div>
            <div class="ios-hero__chips">{''.join(chip_html)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

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
            st.write(f"デバッグ - 現在学習済み問題数({analysis_target}): {metrics['current_studied_count']}, 昨日時点: {metrics['current_studied_count'] - metrics['progress_delta']}, デルタ: {metrics['progress_delta']}")
            st.write(f"デバッグ - 必修現在: {metrics['current_hisshu_studied_count']}, 必修昨日時点: {metrics['current_hisshu_studied_count'] - metrics['hisshu_delta']}, 必修デルタ: {metrics['hisshu_delta']}")
            
            # 全体の練習記録数と現在の分析対象の関係を表示
            total_practice_records = len(st.session_state.get('evaluation_logs', []))
            all_cards = st.session_state.get("cards", {})
            total_learned_all = sum(1 for card in all_cards.values() if card.get('history') and calculate_card_level(card) != "未学習")
            
            st.write(f"デバッグ - 総練習記録数: {total_practice_records}回 | 全分野学習済み: {total_learned_all}問 | {analysis_target}学習済み: {metrics['current_studied_count']}問")
            st.info(f"💡 表示中: {analysis_target}の学習進捗。全分野の合計は{total_learned_all}問です。")
        
        # 4つの主要指標をst.metricで表示
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            progress_delta_text = f"+{metrics['progress_delta']} 問" if metrics['progress_delta'] > 0 else f"{metrics['progress_delta']} 問" if metrics['progress_delta'] < 0 else "変化なし"
            st.metric(
                f"学習進捗率（{analysis_target}）",
                f"{metrics['current_studied_count']} / {metrics['total_count']} 問",
                delta=progress_delta_text,
                help=f"{analysis_target}で学習済みのユニークな問題数です。同じ問題の復習は重複カウントされません。"
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
        

    
    # タブコンテナ - 4つのタブ（元UIを完全復元）
    tab1, tab2, tab3, tab4 = st.tabs(["概要", "グラフ分析", "問題リスト", "キーワード検索"])
    
    with tab1:
        render_overview_tab_perfect(filtered_df, base_df, ALL_QUESTIONS, analysis_target)
    
    with tab2:
        render_graph_analysis_tab_perfect(filtered_df, base_df, analysis_target)
    
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
        cards_state = st.session_state.get('cards', {})
        relevant_ids = [q_id for q_id in filtered_df['id'].tolist() if q_id]
        target_cards = {q_id: cards_state[q_id] for q_id in relevant_ids if q_id in cards_state}

        hisshu_set = GAKUSHI_HISSHU_Q_NUMBERS_SET if analysis_target == "学士試験" else HISSHU_Q_NUMBERS_SET

        min_limit = 30
        max_limit = 400
        default_limit = st.session_state.get('daily_review_limit', 120)
        if default_limit < min_limit:
            default_limit = min_limit
        elif default_limit > max_limit:
            default_limit = max_limit

        st.markdown('<div class="ios-section-title">📅 デイリーレビュープランナー</div>', unsafe_allow_html=True)
        daily_limit = st.slider(
            "1日の復習上限",
            min_value=min_limit,
            max_value=max_limit,
            value=default_limit,
            step=10,
            help="毎日の復習上限を設定すると、遅延カードを数日間に分散して消化できます。"
        )
        st.session_state['daily_review_limit'] = daily_limit

        review_plan = build_balanced_review_plan(
            target_cards,
            daily_target=daily_limit,
            horizon_days=7,
            hisshu_set=hisshu_set
        )

        plan_days_storage = []
        for day in review_plan.get('days', []):
            plan_days_storage.append({
                'date': day.get('date'),
                'count': day.get('count', 0),
                'overdue_served': day.get('overdue_served', 0),
                'hisshu_count': day.get('hisshu_count', 0),
                'mature_count': day.get('mature_count', 0),
                'remaining_backlog': day.get('remaining_backlog', 0)
            })

        plan_registry = dict(st.session_state.get('review_plan_registry', {}))
        plan_registry[analysis_target] = {
            'generated_on': review_plan.get('today'),
            'days': plan_days_storage,
            'daily_limit': daily_limit,
            'overdue_total': review_plan.get('overdue_total', 0),
            'served_total': review_plan.get('served_total', 0),
            'considered_total': review_plan.get('considered_total', 0),
            'backlog_after_horizon': review_plan.get('backlog_after_horizon', 0),
            'remaining_future': review_plan.get('remaining_future', 0)
        }
        st.session_state['review_plan_registry'] = plan_registry

        today_plan_entry = None
        today_date = review_plan.get('today')
        for day in plan_days_storage:
            day_date = day.get('date')
            if isinstance(day_date, datetime.date) and day_date == today_date:
                today_plan_entry = day
                break
            if isinstance(day_date, str) and today_date and isinstance(today_date, datetime.date) and day_date == today_date.isoformat():
                today_plan_entry = day
                break

        today_summary_registry = dict(st.session_state.get('review_plan_today_summary', {}))
        if today_plan_entry:
            today_summary_registry[analysis_target] = today_plan_entry
        else:
            today_summary_registry.pop(analysis_target, None)
        st.session_state['review_plan_today_summary'] = today_summary_registry

        if review_plan['considered_total'] == 0:
            st.info("対象の復習カードがまだありません。演習を進めるとここに計画が表示されます。")
        else:
            served_ratio = (review_plan['served_total'] / review_plan['considered_total'] * 100) if review_plan['considered_total'] else 0
            backlog_after = review_plan['backlog_after_horizon'] + review_plan['remaining_future']

            col_plan_a, col_plan_b, col_plan_c = st.columns(3)
            with col_plan_a:
                st.metric("今日までの未消化復習", f"{review_plan['overdue_total']} 問")
            with col_plan_b:
                st.metric("7日間の処理見込み", f"{review_plan['served_total']} / {review_plan['considered_total']} 問", help=f"約{served_ratio:.1f}%を今週中に解消できます。")
            with col_plan_c:
                st.metric("完了までの目安", f"約{review_plan['projected_clear_days']}日")

            if review_plan['days']:
                plan_rows = []
                for day in review_plan['days']:
                    plan_rows.append({
                        '日付': day['date'].strftime('%m/%d (%a)'),
                        '予定復習数': day['count'],
                        '遅延解消数': day['overdue_served'],
                        '必修カード': day['hisshu_count'],
                        '成熟カード': day['mature_count'],
                        '処理後残数': day['remaining_backlog']
                    })

                plan_df = pd.DataFrame(plan_rows)
                st.dataframe(plan_df, hide_index=True, use_container_width=True)

            if backlog_after > 0:
                st.caption(f"7日後も残るカード: {backlog_after} 問。上限を一時的に+{max(20, daily_limit//2)}するか、演習ペースを抑えて調整してください。")

        st.markdown("---")

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

def render_graph_analysis_tab_perfect(filtered_df: pd.DataFrame, base_df: pd.DataFrame, analysis_target: str):
    """
    グラフ分析タブ - 学習データの可視化
    """
    st.subheader("学習データの可視化")
    if filtered_df.empty:
        st.warning("選択された条件に一致する問題がありません。")

    if not filtered_df.empty:
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
            review_counts = Counter(review_history)
            ninety_days_ago = get_japan_today() - datetime.timedelta(days=90)  # 日本時間ベース
            dates = [ninety_days_ago + datetime.timedelta(days=i) for i in range(91)]
            counts = [review_counts.get(d, 0) for d in dates]
            chart_df = pd.DataFrame({"Date": dates, "Reviews": counts})

            # plotlyを使ってy軸の最小値を0に固定
            try:
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
        level_counts = filtered_df['level'].value_counts()

        # 色分け定義
        level_colors_chart = {
            "未学習": "#757575", "レベル0": "#FF9800", "レベル1": "#FFC107",
            "レベル2": "#8BC34A", "レベル3": "#9C27B0", "レベル4": "#03A9F4",
            "レベル5": "#1E88E5", "習得済み": "#4CAF50"
        }

        try:
            # レベル順に並べ替え
            chart_data = []
            for level in LEVEL_ORDER:
                if level in level_counts.index:
                    chart_data.append({"Level": level, "Count": level_counts[level]})

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

    # --- 科目別の進捗状況と正答率（analysis_targetに応じて更新） ---
    if base_df.empty:
        st.info(f"{analysis_target}の科目データがまだ読み込まれていません。")
        return

    subject_filter = st.session_state.get("subject_filter", [])
    subject_df = base_df.copy()
    if subject_filter:
        subject_df = subject_df[subject_df['subject'].isin(subject_filter)]

    if subject_df.empty:
        st.info("表示対象の科目がありません。サイドバーの科目フィルターを確認してください。")
        return

    subject_df = subject_df.copy()
    subject_df['subject_display'] = subject_df['subject'].apply(
        lambda s: s.strip() if isinstance(s, str) and s.strip() else "未分類"
    )
    subject_df['is_studied'] = subject_df['level'].fillna('未学習') != "未学習"

    progress_summary = (
        subject_df.groupby('subject_display')
        .agg(
            total_questions=('id', 'count'),
            studied_questions=('is_studied', 'sum')
        )
        .reset_index()
    )
    if progress_summary.empty:
        st.info("科目別の進捗データがありません。")
    else:
        progress_summary['studied_questions'] = progress_summary['studied_questions'].astype(int)
        progress_summary['progress_pct'] = (
            progress_summary['studied_questions'] / progress_summary['total_questions']
        ) * 100
        progress_summary['progress_text'] = progress_summary.apply(
            lambda row: f"{row['progress_pct']:.1f}% ({int(row['studied_questions'])}/{int(row['total_questions'])}問)",
            axis=1
        )
        progress_chart_df = progress_summary.sort_values('progress_pct', ascending=True)

        try:
            progress_fig = px.bar(
                progress_chart_df,
                x='progress_pct',
                y='subject_display',
                orientation='h',
                text='progress_text',
                color='progress_pct',
                color_continuous_scale='Blues',
                title=f"{analysis_target} 科目別進捗率（学習済み問題割合）"
            )
            x_max = max(105, float(progress_chart_df['progress_pct'].max()) + 5)
            bar_count = len(progress_chart_df)
            chart_height = max(420, 36 * bar_count + 140)
            progress_fig.update_layout(
                xaxis=dict(title='進捗率 (%)', range=[0, min(110, x_max)]),
                yaxis=dict(title=None, automargin=True),
                coloraxis_showscale=False,
                height=chart_height,
                margin=dict(l=240, r=60, t=80, b=60)
            )
            progress_fig.update_traces(textposition='outside', cliponaxis=False)
            st.plotly_chart(progress_fig, use_container_width=True)
        except ImportError:
            st.bar_chart(progress_chart_df.set_index('subject_display')['progress_pct'])

    def _count_history_attempts(history_list: Any) -> Tuple[int, int]:
        attempts = 0
        correct = 0
        if isinstance(history_list, list):
            for record in history_list:
                if not isinstance(record, dict):
                    continue
                if 'is_correct' in record:
                    attempts += 1
                    if record.get('is_correct'):
                        correct += 1
                elif 'quality' in record:
                    attempts += 1
                    if record.get('quality', 0) >= 3:
                        correct += 1
        return attempts, correct

    attempts_series = subject_df['history'].apply(_count_history_attempts)
    subject_df['total_attempts'] = attempts_series.apply(lambda x: x[0])
    subject_df['correct_attempts'] = attempts_series.apply(lambda x: x[1])

    accuracy_summary = (
        subject_df.groupby('subject_display')
        .agg(
            total_attempts=('total_attempts', 'sum'),
            correct_attempts=('correct_attempts', 'sum')
        )
        .reset_index()
    )

    accuracy_summary['accuracy_pct'] = accuracy_summary.apply(
        lambda row: (row['correct_attempts'] / row['total_attempts'] * 100) if row['total_attempts'] > 0 else None,
        axis=1
    )

    accuracy_valid = accuracy_summary.dropna(subset=['accuracy_pct'])
    if accuracy_valid.empty:
        st.info("科目別の正答率を算出できる学習履歴がまだありません。")
    else:
        accuracy_valid['accuracy_text'] = accuracy_valid.apply(
            lambda row: f"{row['accuracy_pct']:.1f}% ({int(row['correct_attempts'])}/{int(row['total_attempts'])}回)",
            axis=1
        )
        accuracy_chart_df = accuracy_valid.sort_values('accuracy_pct', ascending=False)

        try:
            accuracy_fig = px.bar(
                accuracy_chart_df,
                x='accuracy_pct',
                y='subject_display',
                orientation='h',
                text='accuracy_text',
                color='accuracy_pct',
                color_continuous_scale='Teal',
                title=f"{analysis_target} 科目別平均正答率"
            )
            bar_count = len(accuracy_chart_df)
            chart_height = max(420, 36 * bar_count + 140)
            accuracy_fig.update_layout(
                xaxis=dict(title='平均正答率 (%)', range=[0, 105]),
                yaxis=dict(title=None, automargin=True),
                coloraxis_showscale=False,
                height=chart_height,
                margin=dict(l=240, r=60, t=80, b=60)
            )
            accuracy_fig.update_traces(textposition='outside', cliponaxis=False)
            st.plotly_chart(accuracy_fig, use_container_width=True)
        except ImportError:
            st.bar_chart(accuracy_chart_df.set_index('subject_display')['accuracy_pct'])

    no_history_subjects = accuracy_summary[
        accuracy_summary['total_attempts'] == 0
    ]['subject_display'].tolist()
    if no_history_subjects:
        st.caption("学習履歴が未登録の科目: " + "、".join(no_history_subjects))

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
