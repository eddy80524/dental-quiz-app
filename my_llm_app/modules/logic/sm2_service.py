import datetime
from typing import Dict, List, Any, Tuple
from utils import get_japan_today
import pytz

# 日本時間用のタイムゾーン
JST = pytz.timezone('Asia/Tokyo')

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
                    # Firestoreのタイムスタンプ文字列をパース
                    dt = datetime.datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S.%f")
                    return JST.localize(dt)
                except ValueError:
                    pass
        # datetime.datetimeオブジェクトの場合
        elif isinstance(timestamp, datetime.datetime):
            if timestamp.tzinfo is None:
                return JST.localize(timestamp)
            return timestamp.astimezone(JST)
        # フォールバック：現在時刻を返す
        return datetime.datetime.now(JST)
    except Exception as e:
        print(f"[ERROR] タイムスタンプ変換エラー: {e}")
        return datetime.datetime.now(JST)

class SM2Service:
    """SM-2アルゴリズムと復習スケジュールを管理するサービスクラス"""

    @staticmethod
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
                previous_level = SM2Service.calculate_card_level({'history': history[:-1]})
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

    @staticmethod
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
            
            if not timestamp:
                continue
                
            # タイムスタンプを日本時間の日付に変換
            last_study_date = None
            try:
                last_study_datetime_jst = get_japan_datetime_from_timestamp(timestamp)
                last_study_date = last_study_datetime_jst.date()
            except (ValueError, TypeError, AttributeError):
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

    @staticmethod
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
