"""
ランキングスコア計算モジュール
演習データからリアルタイムでランキングスコアを計算
"""
import datetime
import streamlit as st
from typing import Dict, List, Any, Optional
from collections import defaultdict

# 日本時間用のタイムゾーン
import pytz
JST = pytz.timezone('Asia/Tokyo')

def get_japan_today() -> datetime.date:
    """日本時間の今日の日付を取得"""
    return datetime.datetime.now(JST).date()

def get_japan_datetime_from_timestamp(timestamp) -> datetime.datetime:
    """タイムスタンプから日本時間のdatetimeオブジェクトを取得"""
    try:
        if isinstance(timestamp, str):
            try:
                dt = datetime.datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                return dt.astimezone(JST)
            except ValueError:
                try:
                    dt = datetime.datetime.strptime(timestamp[:10], '%Y-%m-%d')
                    return JST.localize(dt)
                except (ValueError, IndexError):
                    return datetime.datetime.now(JST)
        elif hasattr(timestamp, 'replace'):
            if hasattr(timestamp, 'tzinfo') and timestamp.tzinfo is None:
                return pytz.UTC.localize(timestamp).astimezone(JST)
            else:
                return timestamp.astimezone(JST)
        return datetime.datetime.now(JST)
    except Exception:
        return datetime.datetime.now(JST)

def calculate_weekly_points(cards: Dict, evaluation_logs: List[Dict] = None) -> int:
    """
    週間ポイントを計算
    - 今週学習した問題数 × 基本ポイント
    - 正解率ボーナス
    - 連続学習ボーナス
    """
    today = get_japan_today()
    week_start = today - datetime.timedelta(days=today.weekday())  # 今週の月曜日
    
    weekly_points = 0
    weekly_studies = 0
    weekly_correct = 0
    
    # カードデータから今週の学習を計算
    for q_id, card in cards.items():
        if not isinstance(card, dict):
            continue
            
        history = card.get('history', [])
        for study in history:
            if not isinstance(study, dict):
                continue
                
            timestamp = study.get('timestamp')
            if not timestamp:
                continue
                
            try:
                study_datetime_jst = get_japan_datetime_from_timestamp(timestamp)
                study_date = study_datetime_jst.date()
                
                if study_date >= week_start:
                    weekly_studies += 1
                    quality = study.get('quality', 0)
                    
                    # 基本ポイント（学習1回につき10ポイント）
                    weekly_points += 10
                    
                    # 正解ボーナス（quality >= 3で正解とみなす）
                    if quality >= 3:
                        weekly_correct += 1
                        weekly_points += 5  # 正解ボーナス
                        
                        # 高品質ボーナス
                        if quality >= 4:
                            weekly_points += 3
                        if quality >= 5:
                            weekly_points += 2
                            
            except Exception:
                continue
    
    # セッション状態の評価ログも考慮
    if evaluation_logs:
        for log in evaluation_logs:
            try:
                log_timestamp = log.get('timestamp')
                log_datetime_jst = get_japan_datetime_from_timestamp(log_timestamp)
                log_date = log_datetime_jst.date()
                
                if log_date >= week_start:
                    quality = log.get('quality', 0)
                    
                    # 重複チェック（同じ問題IDの場合はスキップ）
                    q_id = log.get('question_id', '')
                    card = cards.get(q_id, {})
                    history = card.get('history', [])
                    
                    # 最新の学習記録と重複していないかチェック
                    is_duplicate = False
                    for study in history:
                        study_timestamp = study.get('timestamp')
                        if study_timestamp:
                            study_datetime_jst = get_japan_datetime_from_timestamp(study_timestamp)
                            if abs((log_datetime_jst - study_datetime_jst).total_seconds()) < 60:  # 1分以内は重複とみなす
                                is_duplicate = True
                                break
                    
                    if not is_duplicate:
                        weekly_studies += 1
                        weekly_points += 10
                        
                        if quality >= 3:
                            weekly_correct += 1
                            weekly_points += 5
                            if quality >= 4:
                                weekly_points += 3
                            if quality >= 5:
                                weekly_points += 2
                                
            except Exception:
                continue
    
    # 正解率ボーナス（80%以上で追加ポイント）
    if weekly_studies > 0:
        accuracy_rate = weekly_correct / weekly_studies
        if accuracy_rate >= 0.8:
            weekly_points += int(weekly_studies * 0.2)  # 20%ボーナス
        elif accuracy_rate >= 0.6:
            weekly_points += int(weekly_studies * 0.1)  # 10%ボーナス
    
    return weekly_points

def calculate_total_points(cards: Dict, evaluation_logs: List[Dict] = None) -> tuple:
    """
    総合ポイントと問題数を計算
    """
    total_points = 0
    total_problems = 0
    total_correct = 0
    
    # カードデータから計算
    for q_id, card in cards.items():
        if not isinstance(card, dict):
            continue
            
        history = card.get('history', [])
        for study in history:
            if not isinstance(study, dict):
                continue
                
            total_problems += 1
            quality = study.get('quality', 0)
            
            # 基本ポイント
            total_points += 10
            
            # 正解ポイント
            if quality >= 3:
                total_correct += 1
                total_points += 5
                if quality >= 4:
                    total_points += 3
                if quality >= 5:
                    total_points += 2
    
    # セッション状態の評価ログも考慮
    if evaluation_logs:
        for log in evaluation_logs:
            quality = log.get('quality', 0)
            
            # 重複チェック（簡易版）
            q_id = log.get('question_id', '')
            if q_id in cards:
                continue  # カードデータに既に存在する場合はスキップ
            
            total_problems += 1
            total_points += 10
            
            if quality >= 3:
                total_correct += 1
                total_points += 5
                if quality >= 4:
                    total_points += 3
                if quality >= 5:
                    total_points += 2
    
    accuracy_rate = (total_correct / total_problems * 100) if total_problems > 0 else 0
    
    return total_points, total_problems, accuracy_rate

def calculate_mastery_score(cards: Dict) -> tuple:
    """
    習熟度スコアを計算
    SM2アルゴリズムのEFとインターバルを考慮
    学習済みのカードのみをカウント（学習履歴があるもの）
    """
    total_cards = 0
    expert_cards = 0  # EF >= 2.8 かつ interval >= 30
    advanced_cards = 0  # EF >= 2.6 かつ interval >= 7
    total_ef = 0
    mastery_score = 0
    
    # カードデータが空の場合の処理
    if not cards or not isinstance(cards, dict):
        return 0.0, 0, 0, 0, 2.5
    
    for q_id, card in cards.items():
        if not isinstance(card, dict):
            continue
            
        # カードが存在すること自体がある程度の学習を意味する
        # 学習履歴の有無に関わらずカウント
        total_cards += 1
        
        history = card.get('history', [])
        if not history:
            # 学習履歴がない場合は初期値を使用
            ef = 2.5  # 初期EF値
            interval = 0  # 初期間隔
            quality = 0  # 初期品質
            
            total_ef += ef
            card_score = (ef * 30) + (min(interval, 365) * 0.1) + (quality * 10)
            mastery_score += card_score
            # 初期状態はエキスパート・上級にはカウントしない
            continue
        
        # 最新の学習データを取得
        latest = history[-1] if isinstance(history, list) else {}
        ef = latest.get('EF', 2.5)
        interval = latest.get('interval', 0)
        quality = latest.get('quality', 0)
        
        total_ef += ef
        
        # 習熟度スコア計算（EF + interval + quality の重み付け平均）
        card_score = (ef * 30) + (min(interval, 365) * 0.1) + (quality * 10)
        mastery_score += card_score
        
        # カテゴリ分類（学習履歴があるもののみ）
        if ef >= 2.8 and interval >= 30:
            expert_cards += 1
        elif ef >= 2.6 and interval >= 7:
            advanced_cards += 1
    
    avg_ef = total_ef / total_cards if total_cards > 0 else 2.5
    avg_mastery_score = mastery_score / total_cards if total_cards > 0 else 0
    
    return avg_mastery_score, expert_cards, advanced_cards, total_cards, avg_ef

def update_user_ranking_scores(uid: str, cards: Dict, evaluation_logs: List[Dict] = None, nickname: str = None):
    """
    ユーザーのランキングスコアをセッション状態に更新
    """
    if not uid or uid == "guest":
        return
    
    # デバッグ情報を収集
    debug_info = {
        'cards_count': len(cards),
        'cards_with_history': 0,
        'cards_without_history': 0,
        'evaluation_logs_count': len(evaluation_logs) if evaluation_logs else 0
    }
    
    # カードデータの詳細分析
    for q_id, card in cards.items():
        if isinstance(card, dict):
            history = card.get('history', [])
            if history:
                debug_info['cards_with_history'] += 1
            else:
                debug_info['cards_without_history'] += 1
    
    # 週間ポイント計算
    weekly_points = calculate_weekly_points(cards, evaluation_logs)
    
    # 総合ポイント計算
    total_points, total_problems, accuracy_rate = calculate_total_points(cards, evaluation_logs)
    
    # 習熟度スコア計算
    mastery_score, expert_cards, advanced_cards, total_cards, avg_ef = calculate_mastery_score(cards)
    
    # ニックネーム設定
    if not nickname:
        nickname = f"ユーザー{uid[:8]}"
    
    # セッション状態に保存
    ranking_data = {
        'uid': uid,
        'nickname': nickname,
        'weekly_points': weekly_points,
        'total_points': total_points,
        'total_problems': total_problems,
        'accuracy_rate': accuracy_rate,
        'mastery_score': mastery_score,
        'expert_cards': expert_cards,
        'advanced_cards': advanced_cards,
        'total_cards': total_cards,
        'avg_ef': avg_ef,
        'last_updated': datetime.datetime.now(JST).isoformat(),
        'debug_info': debug_info  # デバッグ情報を追加
    }
    
    st.session_state['user_ranking_data'] = ranking_data
    
    return ranking_data
