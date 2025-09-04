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
    """タイムスタンプから日本時間のdatetimeを安全に取得。
    - str(ISO) / datetime / Firestore Timestamp(seconds/nanoseconds or .timestamp()) に対応
    """
    try:
        if timestamp is None:
            return datetime.datetime.now(JST)
        # 文字列（ISOなど）
        if isinstance(timestamp, str):
            try:
                dt = datetime.datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                return dt.astimezone(JST)
            except Exception:
                pass
            try:
                dt = datetime.datetime.strptime(timestamp[:19], '%Y-%m-%dT%H:%M:%S')
                return JST.localize(dt)
            except Exception:
                try:
                    dt = datetime.datetime.strptime(timestamp[:10], '%Y-%m-%d')
                    return JST.localize(dt)
                except Exception:
                    return datetime.datetime.now(JST)
        # Firestore Timestamp (has .timestamp() or .seconds)
        if hasattr(timestamp, 'timestamp'):
            try:
                ts = float(timestamp.timestamp())
            except Exception:
                ts = float(getattr(timestamp, 'seconds', 0))
            dt_utc = datetime.datetime.fromtimestamp(ts, tz=pytz.UTC)
            return dt_utc.astimezone(JST)
        # Python datetime
        if isinstance(timestamp, datetime.datetime) or hasattr(timestamp, 'replace'):
            if getattr(timestamp, 'tzinfo', None) is None:
                return pytz.UTC.localize(timestamp).astimezone(JST)
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
    
    print(f"[DEBUG] 週間ポイント計算開始 - 今日: {today}, 週開始: {week_start}")
    print(f"[DEBUG] カード数: {len(cards)}, 評価ログ数: {len(evaluation_logs) if evaluation_logs else 0}")
    
    # カードデータから今週の学習を計算
    cards_with_history = 0
    for q_id, card in cards.items():
        if not isinstance(card, dict):
            continue
            
        history = card.get('history', [])
        if history and isinstance(history, list):
            cards_with_history += 1
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
                            if quality >= 4:
                                weekly_points += 3
                            if quality >= 5:
                                weekly_points += 2
                except Exception as e:
                    # デバッグ用
                    print(f"週間ポイント計算エラー (q_id: {q_id}): {e}")
                    continue
        else:
            # フォールバック: 履歴がない最適化カードの場合、performance/updated_at から推定
            performance = card.get('performance', {}) or {}
            total_attempts = int(performance.get('total_attempts', 0) or 0)
            last_quality = int(performance.get('last_quality', 0) or 0)
            updated_at = card.get('updated_at') or card.get('metadata', {}).get('updated_at')
            if total_attempts > 0 and updated_at:
                try:
                    upd_date = get_japan_datetime_from_timestamp(updated_at).date()
                except Exception:
                    upd_date = None
                if upd_date and upd_date >= week_start:
                    # 今週更新されたカードだけ反映
                    weekly_studies += total_attempts
                    # 品質に応じた1回あたり得点の推定
                    if last_quality >= 5:
                        per = 20
                        corr_ratio = 0.9
                    elif last_quality >= 4:
                        per = 18
                        corr_ratio = 0.8
                    elif last_quality >= 3:
                        per = 15
                        corr_ratio = 0.65
                    elif last_quality >= 2:
                        per = 10
                        corr_ratio = 0.3
                    else:
                        per = 10
                        corr_ratio = 0.15
                    weekly_points += per * total_attempts
                    weekly_correct += int(total_attempts * corr_ratio)
    
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
    
    print(f"[DEBUG] 履歴ありカード数: {cards_with_history}")
    print(f"[DEBUG] 週間学習数: {weekly_studies}, 週間正解数: {weekly_correct}, 週間ポイント: {weekly_points}")
    
    return weekly_points

def calculate_total_points(cards: Dict, evaluation_logs: List[Dict] = None) -> tuple[int, int, float]:
    """
    総合ポイントと問題数を計算
    """
    total_points = 0
    total_problems = 0
    total_correct = 0
    
    print(f"[DEBUG] 総合ポイント計算開始 - カード数: {len(cards)}")
    
    cards_with_history = 0
    total_studies = 0
    
    # カードデータから計算
    for q_id, card in cards.items():
        if not isinstance(card, dict):
            continue
            
        history = card.get('history', [])
        if history and isinstance(history, list):
            cards_with_history += 1
            for study in history:
                if not isinstance(study, dict):
                    continue
                total_problems += 1
                total_studies += 1
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
        else:
            # フォールバック: performance から推定
            performance = card.get('performance', {}) or {}
            total_attempts = int(performance.get('total_attempts', 0) or 0)
            last_quality = int(performance.get('last_quality', 0) or 0)
            if total_attempts > 0:
                total_problems += total_attempts
                if last_quality >= 5:
                    per = 20
                    corr_ratio = 0.9
                elif last_quality >= 4:
                    per = 18
                    corr_ratio = 0.8
                elif last_quality >= 3:
                    per = 15
                    corr_ratio = 0.65
                elif last_quality >= 2:
                    per = 10
                    corr_ratio = 0.3
                else:
                    per = 10
                    corr_ratio = 0.15
                total_points += per * total_attempts
                total_correct += int(total_attempts * corr_ratio)
    
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
    
    print(f"[DEBUG] 履歴ありカード数: {cards_with_history}")
    print(f"[DEBUG] 総学習数: {total_studies}, 総問題数: {total_problems}, 総正解数: {total_correct}")
    print(f"[DEBUG] 総ポイント: {total_points}, 正答率: {accuracy_rate:.1f}%")
    
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
            
        history = card.get('history', [])
        if not history or not isinstance(history, list) or len(history) == 0:
            # 学習履歴がない場合はスキップ（演習済みカードのみカウント）
            continue
        
        # 学習済みカードとしてカウント
        total_cards += 1
        
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
        'studied_cards': debug_info['cards_with_history'],  # 実際に演習したカード数
        'avg_ef': avg_ef,
        'last_updated': datetime.datetime.now(JST).isoformat(),
        'debug_info': debug_info  # デバッグ情報を追加
    }
    
    st.session_state['user_ranking_data'] = ranking_data
    
    return ranking_data
