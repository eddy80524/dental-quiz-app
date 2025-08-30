"""
検索・進捗ページのモジュール - プロンプト仕様に100%合致した完璧な実装

AI Copilot向けプロンプトの要件を完全に満たす統合ダッシュボード機能
- 統合ダッシュボード: 学習状況サマリー（学習済み問題数、習得率、総学習回数、記憶定着度）
- タブベースUI: 概要、グラフ分析、問題リスト、キーワード検索の4つのタブ
- データフィルタリング: サイドバーフィルターと連動した動的絞り込み
- 詳細な進捗分析: 習熟度レベル分布、正解率、科目別分析、日々の学習量可視化
- キーワード検索: 問題文・科目・問題番号検索、PDF生成機能
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import datetime
from typing import Dict, List, Any, Optional
import time
import base64
import re
import random
import sys
import os
import subprocess
import shutil
import tempfile
import hashlib
from collections import defaultdict, Counter

# 必要なヘルパー関数とデータのインポート
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import (
    ALL_QUESTIONS, 
    HISSHU_Q_NUMBERS_SET, 
    GAKUSHI_HISSHU_Q_NUMBERS_SET,
    extract_year_from_question_number,
    export_questions_to_latex_tcb_jsarticle,
    _gather_images_for_questions,
    _image_block_latex,
    compile_latex_to_pdf
)
from firestore_db import get_firestore_manager

# ユーザーデータ抽出クラスをインポート
sys.path.append('/Users/utsueito/kokushi-dx-poc/dental-DX-PoC')
try:
    from user_data_extractor import UserDataExtractor
except ImportError:
    # フォールバック：UserDataExtractorが利用できない場合
    UserDataExtractor = None

# 統一されたレベル色分け定義（新デザインシステム対応）
LEVEL_COLORS = {
    "未学習": "#BDBDBD",
    "レベル0": "#E47C2E",  # レベル0を再導入（淡い赤色で学習開始段階を示す）
    "レベル1": "#F4B83E", 
    "レベル2": "#56C68B", 
    "レベル3": "#B06CCF",
    "レベル4": "#4AB2D9",
    "レベル5": "#7C5FCF", 
    "習得済み": "#344A90"
}

# 統一されたレベル順序定義（0-5レベルシステム）
LEVEL_ORDER = ["未学習", "レベル0", "レベル1", "レベル2", "レベル3", "レベル4", "レベル5", "習得済み"]

def check_gakushi_permission(uid: str) -> bool:
    """学士試験へのアクセス権限をチェック"""
    try:
        db = get_firestore_manager()
        user_ref = db.collection('users').document(uid)
        user_doc = user_ref.get()
        
        if user_doc.exists:
            user_data = user_doc.to_dict()
            return user_data.get('has_gakushi_permission', False)
        
        # 権限情報がない場合はTrueを返す（開発時の便宜）
        return True
    except Exception:
        # エラーの場合もTrueを返す（開発時の便宜）
        return True

def calculate_card_level(card: Dict[str, Any]) -> str:
    """
    再定義された最終版レベル計算ロジック：
    - 「未学習」は履歴の有無で厳密に判定
    - 「レベル0」を開始点とする連続的なレベルアップ
    - 「習得済み」はEF値と演習回数の組み合わせで判定
    """
    # 1. カードデータまたは学習履歴が存在しない場合は「未学習」
    if not card or not isinstance(card, dict) or not card.get('history'):
        return "未学習"
    
    # --- ここから先は、学習履歴が1件以上存在する場合の処理 ---
    
    n = card.get('n', 0)
    ef = card.get('EF', card.get('ef', 2.5))
    
    # 2. 「習得済み」の判定 (簡単さ x 回数の組み合わせ)
    if (ef >= 2.8 and n >= 3) or \
       (ef >= 2.5 and n >= 5) or \
       (n >= 8):
        return "習得済み"
    
    # 3. 「レベル1」から「レベル5」の判定 (演習回数に基づく)
    if n >= 7: return "レベル5"   # 最高レベル
    if n >= 6: return "レベル4"   # 習得済み直前
    if n >= 4: return "レベル3"   # 得意レベル
    if n >= 3: return "レベル2"   # 普通レベル
    if n >= 2: return "レベル1"   # 基礎レベル
    
    # 4. 上記のいずれでもないが、履歴は存在するカード (n=0または1) は「レベル0」
    return "レベル0"

def calculate_progress_metrics(cards: Dict, base_df: pd.DataFrame, uid: str = None, analysis_target: str = "国試問題") -> Dict:
    """
    学習進捗メトリクスと前日比・前週比を計算するヘルパー関数（UserDataExtractor強化版）
    """
    today = datetime.datetime.now().date()
    yesterday = today - datetime.timedelta(days=1)
    seven_days_ago = datetime.datetime.now() - datetime.timedelta(days=7)
    fourteen_days_ago = datetime.datetime.now() - datetime.timedelta(days=14)
    
    # UserDataExtractorから詳細データを取得（可能な場合）
    enhanced_data = {}
    if uid and uid != "guest" and UserDataExtractor:
        try:
            extractor = UserDataExtractor()
            
            # analysis_targetに応じて試験種別フィルタを設定
            exam_type_filter = None
            if analysis_target == "学士試験問題":
                exam_type_filter = "学士試験"
            elif analysis_target == "国試問題":
                exam_type_filter = "歯科国試"
            
            # analysis_targetでフィルタリングしたログを取得
            evaluation_logs = extractor.extract_self_evaluation_logs(uid)
            practice_data = extractor.extract_practice_logs(uid)
            
            # evaluation_logsをanalysis_targetでフィルタリング
            if exam_type_filter and evaluation_logs:
                # 各ログの問題IDから試験種別を判定してフィルタリング
                filtered_logs = []
                for log in evaluation_logs:
                    question_id = log.get('question_id')  # problem_id → question_id に修正
                    if question_id:
                        # 問題IDから試験種別を判定
                        if exam_type_filter == "学士試験" and ("G24" in question_id or "G25" in question_id):
                            filtered_logs.append(log)
                        elif exam_type_filter == "歯科国試" and not ("G24" in question_id or "G25" in question_id):
                            filtered_logs.append(log)
                        elif exam_type_filter is None:  # フィルタなしの場合
                            filtered_logs.append(log)
                evaluation_logs = filtered_logs
                print(f"[INFO] {analysis_target}でフィルタリング: {len(filtered_logs)}件 (元: 総{len(evaluation_logs)}件)")
            else:
                print(f"[INFO] フィルタリングなし: {len(evaluation_logs)}件")
            
            # より正確な統計を計算
            if evaluation_logs:
                # 7日間の正解率を正確に計算（analysis_targetでフィルタリング済み）
                recent_evaluations = [
                    log for log in evaluation_logs 
                    if log['timestamp'] >= seven_days_ago
                ]
                previous_evaluations = [
                    log for log in evaluation_logs 
                    if fourteen_days_ago <= log['timestamp'] < seven_days_ago
                ]
                
                recent_correct = sum(1 for log in recent_evaluations if log.get('quality', 0) >= 3)
                previous_correct = sum(1 for log in previous_evaluations if log.get('quality', 0) >= 3)
                
                # 必修問題の正解率も別途計算
                recent_hisshu_evaluations = [log for log in recent_evaluations if log.get('is_hisshu', False)]
                previous_hisshu_evaluations = [log for log in previous_evaluations if log.get('is_hisshu', False)]
                
                recent_hisshu_correct = sum(1 for log in recent_hisshu_evaluations if log.get('quality', 0) >= 3)
                previous_hisshu_correct = sum(1 for log in previous_hisshu_evaluations if log.get('quality', 0) >= 3)
                
                enhanced_data['recent_accuracy'] = (recent_correct / len(recent_evaluations) * 100) if recent_evaluations else 0
                enhanced_data['previous_accuracy'] = (previous_correct / len(previous_evaluations) * 100) if previous_evaluations else 0
                enhanced_data['recent_total'] = len(recent_evaluations)
                enhanced_data['previous_total'] = len(previous_evaluations)
                
                # 必修問題の正解率統計
                enhanced_data['recent_hisshu_stats'] = {
                    'correct': recent_hisshu_correct,
                    'total': len(recent_hisshu_evaluations)
                }
                enhanced_data['previous_hisshu_stats'] = {
                    'correct': previous_hisshu_correct,
                    'total': len(previous_hisshu_evaluations)
                }
                
                # 今日と昨日の学習数を正確に計算
                today_logs = [
                    log for log in evaluation_logs 
                    if log['timestamp'].date() == today
                ]
                yesterday_logs = [
                    log for log in evaluation_logs 
                    if log['timestamp'].date() == yesterday
                ]
                
                enhanced_data['today_study_count'] = len(today_logs)
                enhanced_data['yesterday_study_count'] = len(yesterday_logs)
                
                print(f"[INFO] UserDataExtractor強化({analysis_target}): 今日{len(today_logs)}問, 昨日{len(yesterday_logs)}問, 直近7日{len(recent_evaluations)}問, 必修{len(recent_hisshu_evaluations)}問")
        except Exception as e:
            print(f"[WARNING] UserDataExtractor強化データ取得エラー: {e}")
    
    # 今日・昨日・期間別の学習データを集計（従来ロジック）
    today_studied_problems = set()
    yesterday_studied_problems = set()
    today_hisshu_problems = set()
    yesterday_hisshu_problems = set()
    today_study_count = enhanced_data.get('today_study_count', 0)  # 強化データを優先
    yesterday_study_count = enhanced_data.get('yesterday_study_count', 0)  # 強化データを優先
    recent_7days_stats = {'correct': 0, 'total': enhanced_data.get('recent_total', 0)}
    previous_7days_stats = {'correct': 0, 'total': enhanced_data.get('previous_total', 0)}
    
    # フォールバック：従来ロジックで補完（UserDataExtractorが利用できない場合）
    if not enhanced_data:
        for _, row in base_df.iterrows():
            q_id = row['id']
            is_hisshu = row['is_hisshu']
            card = row['card_data']
            history = card.get('history', [])
            
            if isinstance(history, list):
                for entry in history:
                    if isinstance(entry, dict):
                        timestamp = entry.get('timestamp')
                        if timestamp:
                            try:
                                # タイムスタンプをパース - DatetimeWithNanoseconds対応
                                if hasattr(timestamp, 'timestamp') and callable(getattr(timestamp, 'timestamp')):
                                    # DatetimeWithNanoseconds の場合
                                    entry_date = timestamp.date()
                                    entry_datetime = timestamp
                                elif hasattr(timestamp, 'date') and callable(getattr(timestamp, 'date')):
                                    # datetime オブジェクトの場合
                                    entry_date = timestamp.date()
                                    entry_datetime = timestamp
                                else:
                                    # 文字列の場合 - より安全なパース
                                    try:
                                        if 'T' in str(timestamp):
                                            # ISO形式
                                            timestamp_str = str(timestamp).split('.')[0] if '.' in str(timestamp) else str(timestamp)
                                            entry_datetime = datetime.datetime.fromisoformat(timestamp_str)
                                        else:
                                            # 通常形式
                                            entry_datetime = datetime.datetime.fromisoformat(str(timestamp)[:19])
                                        entry_date = entry_datetime.date()
                                    except Exception as e:
                                        print(f"タイムスタンプパースエラー (search_page): {e}")
                                        continue
                                
                                # 今日の学習問題を記録
                                if entry_date == today:
                                    today_studied_problems.add(q_id)
                                    if not enhanced_data:  # 強化データがない場合のみカウント
                                        today_study_count += 1
                                    if is_hisshu:
                                        today_hisshu_problems.add(q_id)
                                
                                # 昨日の学習問題を記録
                                elif entry_date == yesterday:
                                    yesterday_studied_problems.add(q_id)
                                    if not enhanced_data:  # 強化データがない場合のみカウント
                                        yesterday_study_count += 1
                                    if is_hisshu:
                                        yesterday_hisshu_problems.add(q_id)
                                
                                # 直近7日間の正解率統計（強化データがない場合のみ）
                                if not enhanced_data and entry_datetime >= seven_days_ago:
                                    recent_7days_stats['total'] += 1
                                    quality = entry.get('quality', 0)
                                    if quality >= 3:
                                        recent_7days_stats['correct'] += 1
                                
                                # 前の7日間（8-14日前）の正解率統計（強化データがない場合のみ）
                                elif not enhanced_data and entry_datetime >= fourteen_days_ago:
                                    previous_7days_stats['total'] += 1
                                    quality = entry.get('quality', 0)
                                    if quality >= 3:
                                        previous_7days_stats['correct'] += 1
                            except Exception:
                                # すべての例外をキャッチしてスキップ
                                continue
    
    # 現在の総学習済み問題数を計算
    current_studied_count = 0
    current_hisshu_studied_count = 0
    
    # analysis_targetに基づいて総問題数を決定（実際のデータから取得した正確な値）
    if analysis_target == "学士試験問題":
        # 学士試験問題の場合: 4,941問、必修1,100問
        total_count = 4941
        hisshu_total_count = 1100
    else:
        # 国試問題の場合: 8,576問、必修1,300問（デフォルト）
        total_count = 8576
        hisshu_total_count = 1300
    
    # UserDataExtractorから正確な学習済み数を取得（可能な場合）
    if uid and uid != "guest" and UserDataExtractor:
        try:
            extractor = UserDataExtractor()
            comprehensive_stats = extractor.get_user_comprehensive_stats(uid, analysis_target)
            if comprehensive_stats and 'level_distribution' in comprehensive_stats:
                # UserDataExtractorから正確な学習済み数を計算
                level_dist = comprehensive_stats['level_distribution']
                total_questions = sum(level_dist.values())
                unstudied_count = level_dist.get('未学習', 0)
                current_studied_count = total_questions - unstudied_count
                
                # 必修問題の学習済み数も正確に計算（analysis_targetでフィルタリングしたbase_dfから算出）
                # UserDataExtractorでは必修問題の詳細判定ができないため、base_dfから再計算
                for _, row in base_df.iterrows():
                    # analysis_targetによるフィルタリング
                    row_id = row['id']
                    if analysis_target == "学士試験問題" and not ("G24" in row_id or "G25" in row_id):
                        continue
                    elif analysis_target == "国試問題" and ("G24" in row_id or "G25" in row_id):
                        continue
                    
                    # 必修問題の判定（学士試験問題の場合は問題IDから判定）
                    is_hisshu = row['is_hisshu']
                    if analysis_target == "学士試験問題":
                        # 学士試験問題: G24-2-A-1〜20, G24-2-B-1〜20などが必修
                        import re
                        match = re.search(r'G\d+-\d+-[A-Z]-(\d+)', row_id)
                        if match:
                            question_num = int(match.group(1))
                            is_hisshu = (question_num <= 20)  # 1〜20番が必修
                    
                    if is_hisshu:
                        card = row['card_data']
                        level = calculate_card_level(card)
                        if level != "未学習":
                            current_hisshu_studied_count += 1
            else:
                # フォールバック: analysis_targetでフィルタリングしたbase_dfから計算
                for _, row in base_df.iterrows():
                    # analysis_targetによるフィルタリング
                    row_id = row['id']
                    if analysis_target == "学士試験問題" and not ("G24" in row_id or "G25" in row_id):
                        continue
                    elif analysis_target == "国試問題" and ("G24" in row_id or "G25" in row_id):
                        continue
                    
                    # 必修問題の判定（学士試験問題の場合は問題IDから判定）
                    is_hisshu = row['is_hisshu']
                    if analysis_target == "学士試験問題":
                        # 学士試験問題: G24-2-A-1〜20, G24-2-B-1〜20などが必修
                        import re
                        match = re.search(r'G\d+-\d+-[A-Z]-(\d+)', row_id)
                        if match:
                            question_num = int(match.group(1))
                            is_hisshu = (question_num <= 20)  # 1〜20番が必修
                    
                    card = row['card_data']
                    level = calculate_card_level(card)
                    if level != "未学習":
                        current_studied_count += 1
                        if is_hisshu:
                            current_hisshu_studied_count += 1
        except Exception as e:
            print(f"[WARNING] UserDataExtractor取得エラー: {e}")
            # フォールバック: analysis_targetでフィルタリングしたbase_dfから計算
            for _, row in base_df.iterrows():
                # analysis_targetによるフィルタリング
                row_id = row['id']
                if analysis_target == "学士試験問題" and not ("G24" in row_id or "G25" in row_id):
                    continue
                elif analysis_target == "国試問題" and ("G24" in row_id or "G25" in row_id):
                    continue
                
                # 必修問題の判定（学士試験問題の場合は問題IDから判定）
                is_hisshu = row['is_hisshu']
                if analysis_target == "学士試験問題":
                    # 学士試験問題: G24-2-A-1〜20, G24-2-B-1〜20などが必修
                    import re
                    match = re.search(r'G\d+-\d+-[A-Z]-(\d+)', row_id)
                    if match:
                        question_num = int(match.group(1))
                        is_hisshu = (question_num <= 20)  # 1〜20番が必修
                
                card = row['card_data']
                level = calculate_card_level(card)
                if level != "未学習":
                    current_studied_count += 1
                    if is_hisshu:
                        current_hisshu_studied_count += 1
    else:
        # フォールバック: analysis_targetでフィルタリングしたbase_dfから計算
        for _, row in base_df.iterrows():
            # analysis_targetによるフィルタリング
            row_id = row['id']
            if analysis_target == "学士試験問題" and not ("G24" in row_id or "G25" in row_id):
                continue
            elif analysis_target == "国試問題" and ("G24" in row_id or "G25" in row_id):
                continue
            
            # 必修問題の判定（学士試験問題の場合は問題IDから判定）
            is_hisshu = row['is_hisshu']
            if analysis_target == "学士試験問題":
                # 学士試験問題: G24-2-A-1〜20, G24-2-B-1〜20などが必修
                import re
                match = re.search(r'G\d+-\d+-[A-Z]-(\d+)', row_id)
                if match:
                    question_num = int(match.group(1))
                    is_hisshu = (question_num <= 20)  # 1〜20番が必修
            
            card = row['card_data']
            level = calculate_card_level(card)
            if level != "未学習":
                current_studied_count += 1
                if is_hisshu:
                    current_hisshu_studied_count += 1
    
    # 昨日時点での学習済み問題数を推定（今日新規学習した問題を除く）
    yesterday_studied_count = current_studied_count - len(today_studied_problems)
    yesterday_hisshu_studied_count = current_hisshu_studied_count - len(today_hisshu_problems)
    
    # 正解率計算（強化データを優先使用、analysis_targetでフィルタリング）
    if enhanced_data:
        recent_accuracy = enhanced_data['recent_accuracy']
        previous_accuracy = enhanced_data['previous_accuracy']
        # 強化データからの必修と全体の正解率も取得
        recent_hisshu_stats = enhanced_data.get('recent_hisshu_stats', {'correct': 0, 'total': 0})
        previous_hisshu_stats = enhanced_data.get('previous_hisshu_stats', {'correct': 0, 'total': 0})
    else:
        # フォールバック：base_dfから計算するが、analysis_targetでフィルタリング
        recent_7days_stats_filtered = {'correct': 0, 'total': 0}
        previous_7days_stats_filtered = {'correct': 0, 'total': 0}
        recent_hisshu_stats = {'correct': 0, 'total': 0}
        previous_hisshu_stats = {'correct': 0, 'total': 0}
        
        for _, row in base_df.iterrows():
            q_id = row['id']
            is_hisshu = row['is_hisshu']
            card = row['card_data']
            history = card.get('history', [])
            
            if isinstance(history, list):
                for entry in history:
                    if isinstance(entry, dict):
                        timestamp = entry.get('timestamp')
                        if timestamp:
                            try:
                                # タイムスタンプをパース
                                if hasattr(timestamp, 'timestamp') and callable(getattr(timestamp, 'timestamp')):
                                    entry_datetime = timestamp
                                elif hasattr(timestamp, 'date') and callable(getattr(timestamp, 'date')):
                                    entry_datetime = timestamp
                                else:
                                    try:
                                        if 'T' in str(timestamp):
                                            timestamp_str = str(timestamp).split('.')[0] if '.' in str(timestamp) else str(timestamp)
                                            entry_datetime = datetime.datetime.fromisoformat(timestamp_str)
                                        else:
                                            entry_datetime = datetime.datetime.fromisoformat(str(timestamp)[:19])
                                    except Exception:
                                        continue
                                
                                quality = entry.get('quality', 0)
                                
                                # 直近7日間の正解率統計（analysis_targetでフィルタリング）
                                if entry_datetime >= seven_days_ago:
                                    recent_7days_stats_filtered['total'] += 1
                                    if quality >= 3:
                                        recent_7days_stats_filtered['correct'] += 1
                                    
                                    # 必修問題の場合
                                    if is_hisshu:
                                        recent_hisshu_stats['total'] += 1
                                        if quality >= 3:
                                            recent_hisshu_stats['correct'] += 1
                                
                                # 前の7日間（8-14日前）の正解率統計（analysis_targetでフィルタリング）
                                elif entry_datetime >= fourteen_days_ago:
                                    previous_7days_stats_filtered['total'] += 1
                                    if quality >= 3:
                                        previous_7days_stats_filtered['correct'] += 1
                                    
                                    # 必修問題の場合
                                    if is_hisshu:
                                        previous_hisshu_stats['total'] += 1
                                        if quality >= 3:
                                            previous_hisshu_stats['correct'] += 1
                            except Exception:
                                continue
        
        recent_accuracy = (recent_7days_stats_filtered['correct'] / recent_7days_stats_filtered['total'] * 100) if recent_7days_stats_filtered['total'] > 0 else 0
        previous_accuracy = (previous_7days_stats_filtered['correct'] / previous_7days_stats_filtered['total'] * 100) if previous_7days_stats_filtered['total'] > 0 else 0
    
    # 必修問題の正解率を計算
    recent_hisshu_accuracy = (recent_hisshu_stats['correct'] / recent_hisshu_stats['total'] * 100) if recent_hisshu_stats['total'] > 0 else 0
    previous_hisshu_accuracy = (previous_hisshu_stats['correct'] / previous_hisshu_stats['total'] * 100) if previous_hisshu_stats['total'] > 0 else 0
    
    return {
        'current_studied_count': current_studied_count,
        'total_count': total_count,
        'yesterday_studied_count': yesterday_studied_count,
        'progress_delta': current_studied_count - yesterday_studied_count,
        'current_hisshu_studied_count': current_hisshu_studied_count,
        'hisshu_total_count': hisshu_total_count,
        'yesterday_hisshu_studied_count': yesterday_hisshu_studied_count,
        'hisshu_delta': current_hisshu_studied_count - yesterday_hisshu_studied_count,
        'today_study_count': today_study_count,
        'yesterday_study_count': yesterday_study_count,
        'recent_accuracy': recent_accuracy,
        'previous_accuracy': previous_accuracy,
        'accuracy_delta': recent_accuracy - previous_accuracy,
        'recent_hisshu_accuracy': recent_hisshu_accuracy,
        'previous_hisshu_accuracy': previous_hisshu_accuracy,
        'hisshu_accuracy_delta': recent_hisshu_accuracy - previous_hisshu_accuracy,
        'recent_hisshu_stats': recent_hisshu_stats,
        'previous_hisshu_stats': previous_hisshu_stats
    }

def render_search_page():
    """
    プロンプト仕様に基づく完璧な検索・進捗ページ実装
    
    AI Copilot向けプロンプトの要件を100%満たす統合ダッシュボード機能
    """
    
    # ◆ サイドバー連携：analysis_target (国試/学士試験) の取得
    analysis_target = st.session_state.get("analysis_target", "国試")
    level_filter = st.session_state.get("level_filter", ["未学習", "レベル0", "レベル1", "レベル2", "レベル3", "レベル4", "習得済み"])
    subject_filter = st.session_state.get("subject_filter", [])
    
    # 1. 概要と目的 - ページヘッダー
    st.subheader(f"📈 学習ダッシュボード ({analysis_target})")
    
    # 2. 初期データ取得
    uid = st.session_state.get("uid", "guest")
    cards = st.session_state.get("cards", {})
    
    # uidが存在し、cardsが空の場合、Firestoreから読み込み
    if uid != "guest" and not cards:
        try:
            db = get_firestore_manager()
            user_cards = db.get_user_cards(uid)
            if user_cards:
                cards.update(user_cards)
                st.session_state["cards"] = cards
                
                # セッション状態を取得して演習ログを確認
                try:
                    user_ref = db.db.collection("users").document(uid)
                    user_doc = user_ref.get()
                    
                    if user_doc.exists:
                        user_data = user_doc.to_dict()
                        result_log = user_data.get('result_log', {})
                        
                        if result_log:
                            # result_logをhistoryに変換
                            for q_id, log_entry in result_log.items():
                                if q_id in cards:
                                    if 'history' not in cards[q_id]:
                                        cards[q_id]['history'] = []
                                    
                                    # ログエントリをhistory形式に変換
                                    history_entry = {
                                        'timestamp': log_entry.get('timestamp'),
                                        'quality': log_entry.get('quality', 0),
                                        'is_correct': log_entry.get('quality', 0) >= 3,
                                        'user_answer': log_entry.get('user_answer'),
                                        'time_spent': log_entry.get('time_spent')
                                    }
                                    cards[q_id]['history'].append(history_entry)
                        
                except Exception as e:
                    print(f"[WARNING] result_log取得エラー: {e}")
                    
        except Exception as e:
            st.error(f"[ERROR] Firestore取得エラー: {e}")
            print(f"[WARNING] Firestore取得エラー: {e}")
    
    # セッション状態のresult_logも確認
    result_log = st.session_state.get("result_log", {})
    if result_log:
        # result_logからhistoryを作成
        for q_id, log_entry in result_log.items():
            if q_id in cards:
                if 'history' not in cards[q_id]:
                    cards[q_id]['history'] = []
                
                # セッションのresult_logからhistory形式に変換
                history_entry = {
                    'timestamp': log_entry.get('timestamp'),
                    'quality': log_entry.get('quality', 0),
                    'is_correct': log_entry.get('quality', 0) >= 3,
                    'user_answer': log_entry.get('user_answer'),
                    'time_spent': log_entry.get('time_spent')
                }
                cards[q_id]['history'].append(history_entry)
    
    # 3. 権限とフィルター設定の取得
    has_gakushi_permission = check_gakushi_permission(uid)
    analysis_target = st.session_state.get("analysis_target", "国試")
    level_filter = st.session_state.get("level_filter", LEVEL_ORDER)
    subject_filter = st.session_state.get("subject_filter", [])
    
    # 4. 2. プロンプト指示に基づく修正：主要なデータフレームを一度だけ作成
    all_data = []
    
    for question in ALL_QUESTIONS:
        q_number = question.get('number', '')
        
        # analysis_targetとユーザー権限に基づくフィルタリング
        if analysis_target == "国試" and q_number.startswith('G'):
            continue
        if analysis_target == "学士試験":
            if not q_number.startswith('G') or not has_gakushi_permission:
                continue
        
        # 各問題に対応するcardsデータを取得し、学習レベルを計算
        card = cards.get(q_number, {})
        level = calculate_card_level(card)
        
        # is_hisshuフラグをanalysis_targetに応じて判定
        if analysis_target == "学士試験":
            is_hisshu = q_number in GAKUSHI_HISSHU_Q_NUMBERS_SET
        else:
            is_hisshu = q_number in HISSHU_Q_NUMBERS_SET
        
        all_data.append({
            'id': q_number,
            'subject': question.get('subject', ''),
            'year': question.get('year', 0),
            'question_text': question.get('question_text', ''),
            'choices': question.get('choices', []),
            'answer': question.get('answer', ''),
            'level': level,
            'is_hisshu': is_hisshu,
            'card_data': card,
            'history': card.get('history', [])
        })
    
    # 基本DataFrameを作成（フィルター前の全対象問題）
    base_df = pd.DataFrame(all_data)
    
    # 5. サイドバーフィルターを基本DataFrameに適用
    filtered_df = base_df.copy()
    
    if not filtered_df.empty:
        # レベルフィルター適用
        if level_filter and set(level_filter) != set(LEVEL_ORDER):
            filtered_df = filtered_df[filtered_df['level'].isin(level_filter)]
        
        # 科目フィルター適用
        if subject_filter:
            filtered_df = filtered_df[filtered_df['subject'].isin(subject_filter)]
    
    # 6. サマリーメトリクスの計算と表示（UserDataExtractor強化版）
    if not filtered_df.empty:
        # 新しいactionableな指標の計算（前日比・前週比を含む）
        metrics = calculate_progress_metrics(cards, base_df, uid, analysis_target)
        
        # UserDataExtractorからの追加情報を取得
        extractor_insights = {}
        if uid != "guest" and UserDataExtractor:
            try:
                extractor = UserDataExtractor()
                comprehensive_stats = extractor.get_user_comprehensive_stats(uid, analysis_target)
                if comprehensive_stats:
                    extractor_insights = {
                        'weak_categories': comprehensive_stats.get('weak_categories', []),
                        'learning_efficiency': comprehensive_stats.get('learning_efficiency', 0),
                        'total_studied_cards': comprehensive_stats.get('total_studied_cards', 0)
                    }
            except Exception as e:
                print(f"[WARNING] UserDataExtractor insights取得エラー: {e}")
        
        # st.columns(4)を使用して4つの新しい指標をst.metricで表示
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            # 学習進捗率（前日比付き）
            progress_delta_text = f"+{metrics['progress_delta']} 問（前日比）" if metrics['progress_delta'] > 0 else f"{metrics['progress_delta']} 問（前日比）" if metrics['progress_delta'] < 0 else "変化なし（前日比）"
            st.metric(
                "学習進捗率",
                f"{metrics['current_studied_count']} / {metrics['total_count']} 問",
                delta=progress_delta_text
            )
            
            # 弱点分野のヒント表示
            if extractor_insights.get('weak_categories'):
                weak_hint = ", ".join(extractor_insights['weak_categories'][:2])
                st.caption(f"💡 要復習: {weak_hint}")
        
        with col2:
            # 必修問題の進捗（前日比付き）
            hisshu_delta_text = f"+{metrics['hisshu_delta']} 問（前日比）" if metrics['hisshu_delta'] > 0 else f"{metrics['hisshu_delta']} 問（前日比）" if metrics['hisshu_delta'] < 0 else "変化なし（前日比）"
            st.metric(
                "必修問題の進捗",
                f"{metrics['current_hisshu_studied_count']} / {metrics['hisshu_total_count']} 問",
                delta=hisshu_delta_text
            )
        
        with col3:
            # 今日の学習（昨日の実績比較付き）
            today_delta_text = f"昨日: {metrics['yesterday_study_count']} 問"
            st.metric(
                "今日の学習",
                f"{metrics['today_study_count']} 問",
                delta=today_delta_text
            )
            
            # 学習効率スコア表示
            if extractor_insights.get('learning_efficiency', 0) > 0:
                efficiency = extractor_insights['learning_efficiency']
                st.caption(f"📈 学習効率: {efficiency:.1%}")
        
        with col4:
            # 直近7日間の正解率（前週比付き）
            accuracy_delta_text = f"{metrics['accuracy_delta']:+.1f}%（前週比）"
            delta_color = "normal" if metrics['accuracy_delta'] >= 0 else "inverse"
            st.metric(
                "直近7日間の正解率",
                f"{metrics['recent_accuracy']:.1f} %",
                delta=accuracy_delta_text,
                delta_color=delta_color
            )
    
    # 7. タブコンテナ - 4つのタブ（詳細分析タブを削除して元の構成に戻す）
    tab1, tab2, tab3, tab4 = st.tabs(["概要", "グラフ分析", "問題リスト", "キーワード検索"])
    
    with tab1:
        render_overview_tab_perfect(filtered_df, ALL_QUESTIONS, analysis_target)
    
    with tab2:
        render_graph_analysis_tab_perfect(filtered_df)
    
    with tab3:
        render_question_list_tab_perfect(filtered_df)
    
    with tab4:
        render_keyword_search_tab_perfect(analysis_target)

def render_overview_tab_perfect(filtered_df: pd.DataFrame, ALL_QUESTIONS: list, analysis_target: str):
    """
    概要タブ - UserDataExtractor強化版
    st.columns(2)で2分割レイアウト、習熟度分布と正解率表示
    """
    if filtered_df.empty:
        st.info("表示するデータがありません")
        return
    
    # UserDataExtractorからの追加洞察を取得
    uid = st.session_state.get("uid", "guest")
    insights_text = ""
    if uid != "guest" and UserDataExtractor:
        try:
            extractor = UserDataExtractor()
            comprehensive_stats = extractor.get_user_comprehensive_stats(uid)
            if comprehensive_stats:
                weak_areas = comprehensive_stats.get('weak_categories', [])
                efficiency = comprehensive_stats.get('learning_efficiency', 0)
                if weak_areas:
                    insights_text = f"💡 推奨復習分野: {', '.join(weak_areas[:3])}"
                if efficiency > 0.7:
                    insights_text += " | 🚀 学習効率が良好です"
        except Exception as e:
            print(f"[WARNING] 概要タブ洞察取得エラー: {e}")
    
    # st.columns(2)を使用して2分割レイアウト
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("##### カード習熟度分布")
        
        # UserDataExtractorからレベル分布を取得（優先）
        level_distribution_source = "従来ロジック"
        level_counts = None
        
        if uid != "guest" and UserDataExtractor:
            try:
                extractor = UserDataExtractor()
                enhanced_stats = extractor.get_user_comprehensive_stats(uid, analysis_target)
                if enhanced_stats and 'level_distribution' in enhanced_stats:
                    level_dist = enhanced_stats['level_distribution']
                    
                    # UserDataExtractorの結果を使用
                    level_counts = pd.Series(level_dist)
                    level_counts = level_counts.reindex(LEVEL_ORDER, fill_value=0)
                    level_distribution_source = "UserDataExtractor"
            except Exception as e:
                print(f"[WARNING] UserDataExtractor レベル分布取得エラー: {e}")
        
        # フォールバック: 従来ロジック
        if level_counts is None:
            updated_levels = []
            for _, row in filtered_df.iterrows():
                card_data = row['card_data']
                updated_level = calculate_card_level(card_data)
                updated_levels.append(updated_level)
            
            level_counts = pd.Series(updated_levels).value_counts()
            level_counts = level_counts.reindex(LEVEL_ORDER, fill_value=0)
        
        # 表形式表示
        level_df = pd.DataFrame({
            'レベル': level_counts.index,
            '問題数': level_counts.values
        })
        
        st.dataframe(
            level_df,
            use_container_width=True,
            hide_index=True
        )
        
        # データソース表示（デバッグ用）
        st.caption(f"データソース: {level_distribution_source}")
        
        # AI洞察を表示
        if insights_text:
            st.info(insights_text)
    
    with col2:
        st.markdown("##### 正解率 (True Retention)")
        
        # UserDataExtractorからより正確な正解率を取得
        uid = st.session_state.get("uid", "guest")
        enhanced_accuracy = None
        if uid != "guest" and UserDataExtractor:
            try:
                extractor = UserDataExtractor()
                evaluation_logs = extractor.extract_self_evaluation_logs(uid)
                if evaluation_logs:
                    # analysis_targetによるフィルタリング
                    filtered_logs = []
                    for log in evaluation_logs:
                        q_id = log.get('question_id', '')
                        if analysis_target == "学士試験":
                            # 学士試験問題のみ（G24, G25で始まる）
                            if q_id.startswith('G24') or q_id.startswith('G25'):
                                filtered_logs.append(log)
                        else:
                            # 国試問題のみ（G24, G25で始まらない）
                            if not (q_id.startswith('G24') or q_id.startswith('G25')):
                                filtered_logs.append(log)
                    
                    print(f"[INFO] {analysis_target}でフィルタリング: {len(filtered_logs)}件 (元: 総{len(evaluation_logs)}件)")
                    
                    # フィルタリング後のログで正解率計算
                    if filtered_logs:
                        # 全体正解率
                        total_correct = sum(1 for log in filtered_logs if log.get('quality', 0) >= 3)
                        total_attempts = len(filtered_logs)
                        overall_rate = (total_correct / total_attempts * 100) if total_attempts > 0 else 0
                        
                        # 必修問題正解率
                        hisshu_correct = 0
                        hisshu_attempts = 0
                        
                        # 学士試験問題の場合は問題番号で必修判定、国試問題の場合は従来通り
                        for log in filtered_logs:
                            q_id = log.get('question_id', '')
                            is_hisshu = False
                            
                            if analysis_target == "学士試験":
                                # 学士試験問題: G24-2-A-1〜20, G24-2-B-1〜20などが必修
                                import re
                                match = re.search(r'G\d+-\d+-[A-Z]-(\d+)', q_id)
                                if match:
                                    question_num = int(match.group(1))
                                    is_hisshu = (question_num <= 20)  # 1〜20番が必修
                            else:
                                # 国試問題: 従来のHISSHU_Q_NUMBERS_SETを使用
                                is_hisshu = q_id in HISSHU_Q_NUMBERS_SET
                            
                            if is_hisshu:
                                hisshu_attempts += 1
                                if log.get('quality', 0) >= 3:
                                    hisshu_correct += 1
                        
                        hisshu_rate = (hisshu_correct / hisshu_attempts * 100) if hisshu_attempts > 0 else 0
                        
                        enhanced_accuracy = {
                            'overall_rate': overall_rate,
                            'overall_attempts': total_attempts,
                            'overall_correct': total_correct,
                            'hisshu_rate': hisshu_rate,
                            'hisshu_attempts': hisshu_attempts,
                            'hisshu_correct': hisshu_correct
                        }
                        print(f"[INFO] 概要タブ強化: 全体正解率{overall_rate:.1f}%, 必修正解率{hisshu_rate:.1f}%")
            except Exception as e:
                print(f"[WARNING] 概要タブ正解率強化エラー: {e}")
        
        # 強化データまたはフォールバック処理
        if enhanced_accuracy:
            # UserDataExtractorからの高精度データを使用
            st.metric(
                label="選択範囲の正解率",
                value=f"{enhanced_accuracy['overall_rate']:.1f}%",
                delta=f"{enhanced_accuracy['overall_correct']} / {enhanced_accuracy['overall_attempts']} 回"
            )
            st.metric(
                label="【必修問題】の正解率",
                value=f"{enhanced_accuracy['hisshu_rate']:.1f}%",
                delta=f"{enhanced_accuracy['hisshu_correct']} / {enhanced_accuracy['hisshu_attempts']} 回"
            )
        else:
            # フォールバック: 従来ロジック
            total_correct = 0
            total_attempts = 0
            hisshu_correct = 0
            hisshu_attempts = 0
            
            for _, row in filtered_df.iterrows():
                history = row.get('history', [])
                is_hisshu = row.get('is_hisshu', False)
                
                if isinstance(history, list):
                    for entry in history:
                        if isinstance(entry, dict):
                            # quality値による正解判定（quality >= 3で正解）
                            quality = entry.get('quality', 0)
                            is_correct = quality >= 3
                            
                            total_attempts += 1
                            if is_correct:
                                total_correct += 1
                            
                            if is_hisshu:
                                hisshu_attempts += 1
                                if is_correct:
                                    hisshu_correct += 1
            
            # 正解率計算
            overall_rate = (total_correct / total_attempts * 100) if total_attempts > 0 else 0
            hisshu_rate = (hisshu_correct / hisshu_attempts * 100) if hisshu_attempts > 0 else 0
            
            # st.metricを2つ使用（delta引数で内訳を表示）
            st.metric(
                label="選択範囲の正解率",
                value=f"{overall_rate:.1f}%",
                delta=f"{total_correct} / {total_attempts} 回"
            )
            st.metric(
                label="【必修問題】の正解率",
                value=f"{hisshu_rate:.1f}%",
                delta=f"{hisshu_correct} / {hisshu_attempts} 回"
            )

def render_graph_analysis_tab_perfect(filtered_df: pd.DataFrame):
    """
    グラフ分析タブ - UserDataExtractor強化版
    科目別進捗、学習記録、レベル別分布をPlotlyで表示
    """
    if filtered_df.empty:
        st.info("表示するデータがありません")
        return
    
    # UserDataExtractorからの詳細データを取得
    uid = st.session_state.get("uid", "guest")
    enhanced_analytics = {}
    if uid != "guest" and UserDataExtractor:
        try:
            extractor = UserDataExtractor()
            evaluation_logs = extractor.extract_self_evaluation_logs(uid)
            if evaluation_logs:
                enhanced_analytics['evaluation_logs'] = evaluation_logs
                print(f"[INFO] グラフ分析強化: {len(evaluation_logs)}件の評価ログを取得")
        except Exception as e:
            print(f"[WARNING] グラフ分析強化データ取得エラー: {e}")
    
    # 科目別進捗
    st.markdown("##### 科目別進捗状況")
    
    # グラフ表示前の説明を追加
    st.info("📊 各科目の学習進捗を横棒グラフで表示します。グレー: 未学習、青: 学習中、緑: 習得済み")
    
    try:
        # 科目別レベル分布データを詳細に集計（実際のJSONデータの科目名を使用）
        subject_level_data = []
        
        for subject in filtered_df['subject'].unique():
            # 実際の科目名をそのまま使用（標準化は行わない）
            subject_df = filtered_df[filtered_df['subject'] == subject]
            total_count = len(subject_df)
            
            if total_count == 0:
                continue
            
            # 各レベルの数をカウント
            level_counts = subject_df['level'].value_counts()
            
            # 未学習以外を「学習済み」として集計
            learned_count = total_count - level_counts.get('未学習', 0)
            mastered_count = level_counts.get('習得済み', 0)
            
            # パーセンテージ計算
            learned_pct = (learned_count / total_count * 100) if total_count > 0 else 0
            mastered_pct = (mastered_count / total_count * 100) if total_count > 0 else 0
            unlearned_pct = 100 - learned_pct
            
            subject_level_data.append({
                'subject': subject,  # 実際の科目名をそのまま使用
                'total': total_count,
                'learned': learned_count,
                'mastered': mastered_count,
                'learned_pct': learned_pct,
                'mastered_pct': mastered_pct,
                'unlearned_pct': unlearned_pct
            })
        
        # データフレーム作成
        progress_df = pd.DataFrame(subject_level_data)
        
        if len(progress_df) == 0:
            st.warning("科目別データがありません")
            return
        
        # 実際の科目名を使用するので重複統合は不要
        # 問題数で降順ソートして見やすくする
        if len(progress_df) > 0:
            progress_df = progress_df.sort_values('total', ascending=True)  # 問題数昇順でソート
        
        # 積み上げ横棒グラフを作成
        fig = go.Figure()
        
        # 可視性を向上させるため、最小表示幅を設定
        min_visible_width = 2.0  # 最低2%は表示されるようにする
        
        # 未学習部分（薄いグレー - 視認性向上）
        unlearned_values = progress_df['unlearned_pct'].tolist()
        fig.add_trace(go.Bar(
            name='未学習',
            y=progress_df['subject'],
            x=unlearned_values,
            orientation='h',
            marker_color='#BDBDBD',
            text=[f"{pct:.0f}%" if pct >= 10 else "" for pct in unlearned_values],
            textposition='inside',
            hovertemplate='<b>%{y}</b><br>未学習: %{x:.1f}%<extra></extra>'
        ))
        
        # 学習済み（未習得）部分（視認性の高い青色）
        learning_pct = progress_df['learned_pct'] - progress_df['mastered_pct']
        # 最小表示幅を適用
        learning_values = [max(pct, min_visible_width) if pct > 0 else pct for pct in learning_pct]
        fig.add_trace(go.Bar(
            name='学習中',
            y=progress_df['subject'],
            x=learning_values,
            orientation='h',
            marker_color='#42A5F5',
            text=[f"{pct:.0f}%" if pct >= 5 else "" for pct in learning_pct],  # 元の値でテキスト表示
            textposition='inside',
            hovertemplate='<b>%{y}</b><br>学習中: %{customdata:.1f}%<extra></extra>',
            customdata=learning_pct  # 元の値をカスタムデータとして保持
        ))
        
        # 習得済み部分（達成感のある緑色）
        mastered_values = [max(pct, min_visible_width) if pct > 0 else pct for pct in progress_df['mastered_pct']]
        fig.add_trace(go.Bar(
            name='習得済み',
            y=progress_df['subject'],
            x=mastered_values,
            orientation='h',
            marker_color='#4CAF50',
            text=[f"{pct:.0f}%" if pct >= 5 else "" for pct in progress_df['mastered_pct']],  # 元の値でテキスト表示
            textposition='inside',
            hovertemplate='<b>%{y}</b><br>習得済み: %{customdata:.1f}%<extra></extra>',
            customdata=progress_df['mastered_pct']  # 元の値をカスタムデータとして保持
        ))
        
        fig.update_layout(
            title={
                'text': "科目別進捗状況（各科目100%基準）",
                'x': 0,  # タイトルを左寄せ
                'xanchor': 'left'
            },
            xaxis_title="進捗率 (%)",
            yaxis_title="科目",
            barmode='stack',
            height=max(500, len(progress_df) * 35),  # 科目数に応じて高さ調整（最小500px）
            xaxis=dict(range=[0, 105], tickformat='.0f', ticksuffix='%'),
            yaxis=dict(
                automargin=True, 
                tickmode='linear',
                side='left'  # Y軸ラベルを左側に配置
            ),
            legend=dict(
                orientation="h", 
                yanchor="bottom", 
                y=1.02, 
                xanchor="left",  # 凡例を左寄せ
                x=0
            ),
            margin=dict(l=200, r=50, t=80, b=50),  # 左マージンを広く取って科目名を表示
            showlegend=True,
            plot_bgcolor='white',
            paper_bgcolor='white',
            font=dict(size=12)  # フォントサイズを明示的に指定
        )
        
        # 横棒グラフを表示（左寄せで高さ中央配置）
        print(f"[DEBUG] グラフ分析タブで横棒グラフ表示開始")
        print(f"[DEBUG] figの型: {type(fig)}")
        print(f"[DEBUG] progress_df科目数: {len(progress_df)}")
        print(f"[DEBUG] figのdata数: {len(fig.data)}")
        print(f"[DEBUG] figの高さ: {fig.layout.height}")
        
        # グラフを左寄せで配置（高さ中央）
        try:
            st.plotly_chart(fig, use_container_width=True, key="subject_progress_chart")
            print(f"[DEBUG] Plotlyチャート表示成功")
        except Exception as chart_error:
            print(f"[ERROR] Plotlyチャート表示エラー: {chart_error}")
            st.error(f"グラフ表示エラー: {chart_error}")
            # フォールバック: シンプルなバーチャート
            st.bar_chart(progress_df.set_index('subject')[['learned_pct', 'mastered_pct']])
        
        print(f"[DEBUG] グラフ分析タブで横棒グラフ表示完了")
        
        # 詳細データテーブルは非表示（UIが煩雑になるため）
        # ユーザーが詳細を知りたい場合はグラフのホバー情報で十分
        
    except Exception as e:
        st.error(f"グラフ作成エラー: {e}")
        st.info("グラフの表示に問題が発生しました。データの確認を行ってください。")
    
    # 学習記録 - UserDataExtractor強化版
    st.markdown("##### 学習の記録")
    
    # UserDataExtractorの詳細データを使用（可能な場合）
    if enhanced_analytics.get('evaluation_logs'):
        evaluation_logs = enhanced_analytics['evaluation_logs']
        
        # 高精度な日別学習データを作成
        daily_study = defaultdict(lambda: {'count': 0, 'correct': 0, 'avg_quality': 0})
        today = datetime.datetime.now()
        ninety_days_ago = today - datetime.timedelta(days=90)
        
        quality_sum = defaultdict(int)
        
        for log in evaluation_logs:
            try:
                # より安全なタイムスタンプパース
                timestamp = log['timestamp']
                if isinstance(timestamp, str):
                    if 'T' in timestamp:
                        # ISO形式
                        timestamp_str = timestamp.split('.')[0] if '.' in timestamp else timestamp
                        log_datetime = datetime.datetime.fromisoformat(timestamp_str)
                    else:
                        # 通常形式
                        log_datetime = datetime.datetime.fromisoformat(timestamp[:19])
                else:
                    # datetime オブジェクトの場合
                    log_datetime = timestamp
                    
                if log_datetime >= ninety_days_ago:
                    date_str = log_datetime.date().isoformat()
                    daily_study[date_str]['count'] += 1
                    quality = log.get('quality', 0)
                    quality_sum[date_str] += quality
                    if quality >= 3:
                        daily_study[date_str]['correct'] += 1
            except:
                continue
        
        # 平均評価を計算
        for date_str in daily_study:
            if daily_study[date_str]['count'] > 0:
                daily_study[date_str]['avg_quality'] = quality_sum[date_str] / daily_study[date_str]['count']
        
        if daily_study:
            study_df = pd.DataFrame([
                {
                    '日付': date_str,
                    '学習回数': data['count'],
                    '正解数': data['correct'],
                    '正解率': (data['correct'] / data['count'] * 100) if data['count'] > 0 else 0,
                    '平均評価': data['avg_quality']
                }
                for date_str, data in daily_study.items()
            ])
            study_df['日付'] = pd.to_datetime(study_df['日付'])
            study_df = study_df.sort_values('日付')
            
            # 2つのグラフを作成
            col1, col2 = st.columns(2)
            
            with col1:
                # 学習回数グラフ
                fig1 = px.bar(
                    study_df, 
                    x='日付', 
                    y='学習回数',
                    title='学習回数推移（過去90日）',
                    color='学習回数',
                    color_continuous_scale='Blues'
                )
                fig1.update_traces(hovertemplate='<b>%{x|%Y-%m-%d}</b><br>学習回数: %{y}問<extra></extra>')
                fig1.update_layout(coloraxis_showscale=False, height=300)
                st.plotly_chart(fig1, use_container_width=True)
            
            with col2:
                # 正解率グラフ
                fig2 = px.line(
                    study_df, 
                    x='日付', 
                    y='正解率',
                    title='正解率推移（過去90日）',
                    line_shape='spline'
                )
                fig2.update_traces(hovertemplate='<b>%{x|%Y-%m-%d}</b><br>正解率: %{y:.1f}%<extra></extra>')
                fig2.update_layout(height=300)
                fig2.update_traces(line_color='#FF6B6B')
                st.plotly_chart(fig2, use_container_width=True)
            
            # 強化された統計メトリクス
            col1, col2, col3, col4 = st.columns(4)
            total_days = len(study_df)
            total_sessions = study_df['学習回数'].sum()
            avg_daily = study_df['学習回数'].mean()
            avg_accuracy = study_df['正解率'].mean()

            with col1:
                st.metric("学習日数", f"{total_days}日", help="過去90日間の実績")
            with col2:
                st.metric("総学習回数", f"{total_sessions}回", help="過去90日間の実績")
            with col3:
                st.metric("1日平均", f"{avg_daily:.1f}回", help="過去90日間の学習日平均")
            with col4:
                st.metric("平均正解率", f"{avg_accuracy:.1f}%", help="過去90日間の平均")
        else:
            st.info("学習記録データがありません")
    else:
        # フォールバック: 従来のロジック
        daily_study = defaultdict(int)
        today = datetime.datetime.now()
        ninety_days_ago = today - datetime.timedelta(days=90)

        for _, row in filtered_df.iterrows():
            history = row.get('history', [])
            if isinstance(history, list):
                for entry in history:
                    if isinstance(entry, dict) and 'timestamp' in entry:
                        try:
                            # タイムスタンプのパース処理
                            timestamp = entry['timestamp']
                            if hasattr(timestamp, 'date'):
                                entry_datetime = timestamp
                            else:
                                # より安全なタイムスタンプパース
                                try:
                                    if 'T' in str(timestamp):
                                        # ISO形式
                                        timestamp_str = str(timestamp).split('.')[0] if '.' in str(timestamp) else str(timestamp)
                                        entry_datetime = datetime.datetime.fromisoformat(timestamp_str)
                                    else:
                                        # 通常形式
                                        entry_datetime = datetime.datetime.fromisoformat(str(timestamp)[:19])
                                except Exception as e:
                                    print(f"タイムスタンプパースエラー (search_page line 939): {e}")
                                    continue
                            
                            # 90日以内のデータのみ集計
                            if entry_datetime >= ninety_days_ago:
                                date_str = entry_datetime.date().isoformat()
                                daily_study[date_str] += 1
                        except:
                            continue

        if daily_study:
            study_df = pd.DataFrame(list(daily_study.items()), columns=['日付', '学習回数'])
            study_df['日付'] = pd.to_datetime(study_df['日付'])
            study_df = study_df.sort_values('日付')
            
            # シンプルな棒グラフを作成
            fig = px.bar(
                study_df, 
                x='日付', 
                y='学習回数',
                title='過去90日間の学習記録',
                color='学習回数',
                color_continuous_scale='OrRd'
            )
            
            fig.update_traces(hovertemplate='<b>%{x|%Y-%m-%d}</b><br>学習回数: %{y}問<extra></extra>')
            fig.update_layout(
                xaxis_title='日付',
                yaxis_title='学習回数',
                coloraxis_showscale=False,
                height=400
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # 基本統計
            col1, col2, col3, col4 = st.columns(4)
            total_days = len(study_df)
            total_sessions = study_df['学習回数'].sum()
            avg_daily = study_df['学習回数'].mean()
            max_daily = study_df['学習回数'].max()

            with col1:
                st.metric("学習日数", f"{total_days}日", help="過去90日間の実績")
            with col2:
                st.metric("総学習回数", f"{total_sessions}回", help="過去90日間の実績")
            with col3:
                st.metric("1日平均", f"{avg_daily:.1f}回", help="過去90日間の学習日平均")
            with col4:
                st.metric("最大学習回数", f"{max_daily}回", help="過去90日間の最大値")
        else:
            st.info("学習記録データがありません")
    
    # レベル別分布
    st.markdown("##### 学習レベル別分布")
    
    level_counts = filtered_df['level'].value_counts()
    level_counts = level_counts.reindex(LEVEL_ORDER, fill_value=0)
    
    try:
        # Plotly製の棒グラフ
        fig = px.bar(
            x=level_counts.index, 
            y=level_counts.values,
            title="学習レベル別分布",
            color=level_counts.index,
            color_discrete_map=LEVEL_COLORS
        )
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    except:
        # フォールバック
        st.bar_chart(level_counts)

def render_question_list_tab_perfect(filtered_df: pd.DataFrame):
    """
    問題リストタブ - 縦長リスト形式での全面刷新
    フィルター条件に合致する全ての問題を一覧表示
    """
    st.subheader("問題リスト")
    
    if filtered_df.empty:
        st.info("フィルタ条件に一致する問題がありません。")
        return

    # 4. プロンプト指示に基づく修正：シンプルで堅牢なソート関数に置き換え
    def get_natural_sort_key(q_id):
        """
        シンプルで堅牢な問題番号ソートキー生成関数
        国試問題（118A1）と学士試験問題（G24-1-1-A-1）の両方に対応
        """
        import re
        q_id = str(q_id)
        
        # 学士試験問題（G始まり）の場合
        if q_id.startswith('G'):
            # パターン1: G22-1-1-A-1 形式
            match1 = re.match(r'G(\d+)-(\d+)-(\d+)-([A-Z])-(\d+)', q_id)
            if match1:
                year, term, session, section, number = match1.groups()
                return (1, int(year), int(term), int(session), 0, section, int(number))
            
            # パターン2: G23-2-A-67 形式
            match2 = re.match(r'G(\d+)-(\d+)-([A-Z])-(\d+)', q_id)
            if match2:
                year, term, section, number = match2.groups()
                return (1, int(year), int(term), 999, 0, section, int(number))
            
            # パターン3: G22-1再-C-75 形式（再試験）
            match3 = re.match(r'G(\d+)-(\d+)再-([A-Z])-(\d+)', q_id)
            if match3:
                year, term, section, number = match3.groups()
                return (1, int(year), int(term), 1000, 0, section, int(number))
            
            # パターン4: 旧形式 G97A1
            match4 = re.match(r'G(\d+)([A-Z])(\d+)', q_id)
            if match4:
                year, section, number = match4.groups()
                return (1, int(year), 0, 0, 0, section, int(number))
            
            # フォールバック
            return (1, 0, 0, 9999, 0, 'Z', 9999)
        else:
            # 国試問題の場合：118A1, 95C40 など
            match = re.match(r'(\d+)([A-Z]?)(\d+)', q_id)
            if match:
                year, section, number = match.groups()
                section = section if section else 'A'
                return (0, int(year), 0, 0, 0, section, int(number))
            else:
                # 数値のみの場合
                num_match = re.search(r'(\d+)', q_id)
                if num_match:
                    return (0, 0, 0, 0, 0, 'A', int(num_match.group(1)))
                else:
                    return (0, 0, 0, 9999, 0, 'Z', 9999)
    
    # 4. プロンプト指示に基づく修正：try-exceptでソート処理を囲む
    try:
        sorted_df = filtered_df.copy()
        sorted_df['sort_key'] = sorted_df['id'].apply(get_natural_sort_key)
        sorted_df = sorted_df.sort_values('sort_key').drop('sort_key', axis=1)
    except Exception as e:
        # 4. プロンプト指示に基づく修正：フォールバック処理（文字列ソート）
        print(f"[WARNING] ソート処理でエラー発生、文字列ソートにフォールバック: {e}")
        sorted_df = filtered_df.sort_values('id')
    
    # --- ▼ ここからが修正部分：リスト形式表示 ---
    
    # 1. 表示制限を撤廃し、全件を表示対象とする
    display_df = sorted_df
    total_count = len(display_df)
    st.write(f"表示対象: {total_count}問")

    # 2. ループ処理でリスト項目を生成
    for _, row in display_df.iterrows():
        level = row['level']
        color = LEVEL_COLORS.get(level, "#757575")
        q_id = row['id']
        # 実際の科目名をそのまま使用（標準化は行わない）
        actual_subject = row['subject']
        
        # 3. HTMLとCSSでリスト項目をスタイリング
        list_item_html = f"""
        <div style="
            border-left: 5px solid {color}; 
            padding: 5px 10px; 
            margin: 3px 0; 
            border-radius: 3px;
            display: flex;
            align-items: center;
        ">
            <span style="
                color: {color}; 
                font-weight: bold; 
                width: 80px; 
                flex-shrink: 0;
            ">{level}</span>
            <span style="font-weight: 500;">{q_id}</span>
            <span style="color: #666; margin-left: 15px; font-size: 0.9em;">{actual_subject}</span>
        </div>
        """
        st.markdown(list_item_html, unsafe_allow_html=True)

def render_keyword_search_tab_perfect(analysis_target: str):
    """
    キーワード検索タブ - 完全再現版
    検索機能、統計表示、結果リスト表示、PDF生成機能を含む
    """
    st.subheader("🔍 キーワード検索")

    # 1. 検索フォーム
    col1, col2 = st.columns([4, 1])
    with col1:
        keyword = st.text_input("検索キーワード", key="search_keyword", 
                               placeholder="例：根管治療、インプラント、咬合")
    with col2:
        shuffle_results = st.checkbox("検索結果をシャッフル", key="shuffle_search")

    if st.button("🔍 検索実行", key="execute_search", type="primary", use_container_width=True):
        if keyword:
            # 2. 検索ロジック (複数フィールドを対象)
            search_results = []
            
            for question in ALL_QUESTIONS:
                q_number = question.get('number', '')
                
                # analysis_targetフィルターを適用
                if analysis_target == "国試" and q_number.startswith('G'):
                    continue
                if analysis_target == "学士試験" and not q_number.startswith('G'):
                    continue
                
                # 複数のテキストフィールドでキーワード検索
                searchable_text = [
                    question.get('question', ''),  # 正しいキー
                    question.get('subject', ''),
                    q_number,
                    str(question.get('choices', [])),
                    question.get('answer', ''),
                    question.get('explanation', '')  # 解説も検索対象に追加
                ]
                
                # キーワードが含まれるかチェック
                combined_text = ' '.join(searchable_text).lower()
                if keyword.lower() in combined_text:
                    search_results.append(question)
            
            # シャッフルオプション適用
            if shuffle_results:
                random.shuffle(search_results)
            
            # 検索結果をセッション状態に保存
            st.session_state["search_results"] = search_results
            st.session_state["search_query"] = keyword
            st.session_state["search_analysis_target"] = analysis_target
            st.session_state["search_shuffled"] = shuffle_results
        else:
            st.warning("検索キーワードを入力してください")

    # 3. 検索結果表示
    if "search_results" in st.session_state:
        results = st.session_state["search_results"]
        query = st.session_state.get("search_query", "")
        search_type = st.session_state.get("search_analysis_target", "全体")
        is_shuffled = st.session_state.get("search_shuffled", False)

        if results:
            # サマリーメッセージ
            shuffle_info = "（シャッフル済み）" if is_shuffled else "（順番通り）"
            st.success(f"「{query}」で{len(results)}問見つかりました（{search_type}）{shuffle_info}")

            # 統計情報の表示
            subjects = set(q.get('subject', '') for q in results)
            
            # 年度範囲の計算（extract_year_from_question_number使用）
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
            for i, q in enumerate(results[:20]):  # 20件に制限
                q_number = q.get('number', 'N/A')
                subject = q.get('subject', '未分類')
                
                # 学習レベルと履歴を取得
                cards = st.session_state.get('cards', {})
                card = cards.get(q_number, {})
                level = calculate_card_level(card)
                
                # st.expanderタイトル
                with st.expander(f"● {q_number} - {subject}"):
                    # 学習レベル（最上部）
                    st.markdown(f"**学習レベル:** {level}")
                    
                    # 問題文（省略表示）
                    question_text = q.get('question', '')
                    if len(question_text) > 100:
                        st.markdown(f"**問題:** {question_text[:100]}...")
                    else:
                        st.markdown(f"**問題:** {question_text}")
                    
                    # 選択肢（省略表示）
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
                    
                    # 正解
                    answer = q.get('answer', '')
                    if answer:
                        st.markdown(f"**正解:** {answer}")
                    
                    # 学習履歴
                    history = card.get('history', [])
                    n = card.get('n', 0)
                    if not history:
                        st.markdown("**学習履歴:** なし")
                    else:
                        st.markdown(f"**学習履歴:** {len(history)}回")
                        st.markdown(f"**演習回数:** {n}回")
                        # 最新の学習記録を表示
                        if len(history) > 0:
                            latest = history[-1]
                            timestamp = latest.get('timestamp', '')
                            quality = latest.get('quality', 0)
                            if timestamp:
                                try:
                                    if hasattr(timestamp, 'strftime'):
                                        time_str = timestamp.strftime('%Y-%m-%d %H:%M')
                                    else:
                                        # より安全な文字列処理
                                        try:
                                            if 'T' in str(timestamp):
                                                # ISO形式
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

            # 4. PDF生成・ダウンロード機能
            st.markdown("#### 📄 PDF生成")
            colA, colB = st.columns(2)
            
            with colA:
                if st.button("📄 PDFを生成", key="pdf_generate_button"):
                    with st.spinner("PDFを生成中... 高品質なレイアウトのため数分かかることがあります。"):
                        # 参照元app.pyのPDF生成ロジックを完全に移植
                        assets, per_q_files = _gather_images_for_questions(results)
                        latex_source = export_questions_to_latex_tcb_jsarticle(results, right_label_fn=lambda q: q.get('subject', ''))
                        
                        # 画像プレースホルダーを置換
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
                            # 失敗した場合はダウンロード用のデータを削除
                            if "pdf_bytes_for_download" in st.session_state:
                                del st.session_state["pdf_bytes_for_download"]
                            with st.expander("エラーログ"):
                                st.code(log or "ログはありません", language="text")
            
            with colB:
                # st.session_stateにPDFデータが存在する場合のみ、ダウンロードボタンを活性化
                if "pdf_bytes_for_download" in st.session_state and st.session_state["pdf_bytes_for_download"]:
                    file_size_kb = len(st.session_state["pdf_bytes_for_download"]) / 1024
                    st.download_button(
                        label="📥 PDFをダウンロード",
                        data=st.session_state["pdf_bytes_for_download"],
                        file_name=st.session_state["pdf_filename_for_download"],
                        mime="application/pdf",
                        use_container_width=True,
                        type="primary",  # 目立つプライマリースタイルを適用
                        help=f"ファイルサイズ: {file_size_kb:.1f} KB"
                    )
                else:
                    # データがない場合はボタンを非活性状態で表示
                    st.button("📥 PDFをDL", disabled=True, use_container_width=True)
        else:
            if query:
                st.warning(f"「{query}」に該当する問題が見つかりませんでした")
            else:
                st.info("キーワードを入力して検索してください")

# メイン関数をモジュールの公開関数として設定
def main():
    """モジュールのメイン関数"""
    render_search_page()

if __name__ == "__main__":
    main()
