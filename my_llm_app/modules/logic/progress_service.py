import datetime
import pandas as pd
import streamlit as st
from typing import Dict, List, Any
from utils import get_japan_today, get_japan_datetime_from_timestamp, JST, ALL_QUESTIONS, HISSHU_Q_NUMBERS_SET, GAKUSHI_HISSHU_Q_NUMBERS_SET, KOKUSHI_GENERAL_Q_NUMBERS_SET, KOKUSHI_CLINICAL_Q_NUMBERS_SET, GAKUSHI_GENERAL_Q_NUMBERS_SET, GAKUSHI_CLINICAL_Q_NUMBERS_SET
from modules.logic.sm2_service import SM2Service

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

class ProgressService:
    """進捗計算とデータ準備を行うサービスクラス"""

    @staticmethod
    @st.cache_data(ttl=600, show_spinner=False)
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

    @staticmethod
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
            level = SM2Service.calculate_card_level(card)
            
            # 必修問題判定
            if analysis_target == "学士試験":
                is_hisshu = q_number in GAKUSHI_HISSHU_Q_NUMBERS_SET
                is_general = q_number in GAKUSHI_GENERAL_Q_NUMBERS_SET
                is_clinical = q_number in GAKUSHI_CLINICAL_Q_NUMBERS_SET
            else:
                is_hisshu = q_number in HISSHU_Q_NUMBERS_SET
                is_general = q_number in KOKUSHI_GENERAL_Q_NUMBERS_SET
                is_clinical = q_number in KOKUSHI_CLINICAL_Q_NUMBERS_SET
            
            # データ行の作成
            row_data = {
                'id': q_number,
                'level': level,
                'subject': question.get('subject', '未分類'),
                'is_hisshu': is_hisshu,
                'is_general': is_general,
                'is_clinical': is_clinical,
                'card_data': card,
                'history': card.get('history', []) if isinstance(card, dict) else []
            }
            
            all_data.append(row_data)
        
        return pd.DataFrame(all_data)

    @staticmethod
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
        total_kokushi, total_gakushi = ProgressService.calculate_total_questions()
        
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
            level = SM2Service.calculate_card_level(card)
            
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
