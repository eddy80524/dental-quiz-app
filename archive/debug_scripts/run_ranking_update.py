#!/usr/bin/env python3
"""
週間ランキング更新用スタンドアローンスクリプト
Streamlitに依存せずに動作
"""
import os
import sys
import json
import tempfile
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials, firestore
from collections import defaultdict, Counter

class StandaloneRankingUpdater:
    def __init__(self):
        self.db = None
        self._initialize_firebase()
    
    def _initialize_firebase(self):
        """Firebase初期化（Streamlit非依存）"""
        if firebase_admin._apps:
            # 既に初期化済みの場合
            self.db = firestore.client()
            return
        
        try:
            # 環境変数からクレデンシャルを取得
            creds_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
            if creds_path and os.path.exists(creds_path):
                cred = credentials.Certificate(creds_path)
                firebase_admin.initialize_app(cred)
            else:
                # デフォルトクレデンシャルを使用（Application Default Credentials）
                firebase_admin.initialize_app()
            
            self.db = firestore.client()
            print("✅ Firebase接続完了")
            
        except Exception as e:
            print(f"Firebase初期化エラー: {e}")
            # 最後の手段として、プロジェクトIDのみで初期化を試行
            try:
                firebase_admin.initialize_app(options={'projectId': 'dent-ai-4d8d8'})
                self.db = firestore.client()
                print("✅ Firebase接続完了（プロジェクトID指定）")
            except Exception as e2:
                raise Exception(f"Firebase初期化に失敗しました: {e2}")
    
    def calculate_user_weekly_points(self, uid: str) -> int:
        """ユーザーの週間ポイントを計算"""
        try:
            # 今週の開始日を計算（UTC）
            from datetime import timezone
            today = datetime.now(timezone.utc)
            days_since_monday = today.weekday()  # 0=月曜日
            week_start = today - timedelta(days=days_since_monday)
            week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
            
            # study_cardsコレクションから直接ユーザーのカードデータを取得
            study_cards_ref = self.db.collection("study_cards")
            user_cards_query = study_cards_ref.where("uid", "==", uid)
            user_cards_docs = user_cards_query.get()
            
            weekly_points = 0
            processed_cards = 0
            weekly_activities = 0
            
            for doc in user_cards_docs:
                card_data = doc.to_dict()
                history = card_data.get("history", [])
                
                for entry in history:
                    # タイムスタンプの解析（UTC統一）
                    entry_time = None
                    timestamp = entry.get("timestamp")
                    
                    if isinstance(timestamp, str):
                        try:
                            # ISO形式の文字列を解析
                            if 'T' in timestamp:
                                if timestamp.endswith('Z'):
                                    timestamp = timestamp[:-1] + '+00:00'
                                elif '+' not in timestamp and '-' not in timestamp[-6:]:
                                    timestamp = timestamp + '+00:00'
                                entry_time = datetime.fromisoformat(timestamp)
                            else:
                                # シンプルな日時文字列の場合、UTCと仮定
                                entry_time = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
                                entry_time = entry_time.replace(tzinfo=timezone.utc)
                        except Exception as parse_error:
                            print(f"タイムスタンプ解析エラー: {timestamp}, エラー: {parse_error}")
                            continue
                    elif hasattr(timestamp, 'timestamp'):
                        # Firestore Timestamp
                        entry_time = datetime.fromtimestamp(timestamp.timestamp(), tz=timezone.utc)
                    elif hasattr(timestamp, 'seconds'):
                        # Firestore Timestamp (古い形式)
                        entry_time = datetime.fromtimestamp(timestamp.seconds, tz=timezone.utc)
                    
                    if entry_time and entry_time >= week_start:
                        quality = entry.get("quality", 0)
                        # 正答の場合はquality値をそのまま、不正答の場合は減点
                        is_correct = quality >= 3
                        if is_correct:
                            weekly_points += quality
                        else:
                            weekly_points += max(1, quality - 2)
                        weekly_activities += 1
                
                processed_cards += 1
            
            print(f"ユーザー{uid}: 処理カード数{processed_cards}, 週間活動{weekly_activities}回, 週間ポイント{weekly_points}")
            return weekly_points
            
        except Exception as e:
            print(f"ユーザー{uid}のポイント計算エラー: {e}")
            return 0
    
    def calculate_user_study_stats(self, uid: str) -> dict:
        """ユーザーの学習統計を計算"""
        try:
            # study_cardsコレクションから直接ユーザーデータを取得
            study_cards_ref = self.db.collection("study_cards")
            user_cards_query = study_cards_ref.where("uid", "==", uid)
            user_cards_docs = user_cards_query.get()
            
            total_problems = 0
            correct_answers = 0
            total_points = 0
            
            for doc in user_cards_docs:
                card_data = doc.to_dict()
                
                # パフォーマンスデータから統計を取得
                performance = card_data.get("performance", {})
                total_attempts = performance.get("total_attempts", 0)
                correct_attempts = performance.get("correct_attempts", 0)
                
                # 履歴データからポイントを計算
                history = card_data.get("history", [])
                for entry in history:
                    quality = entry.get("quality", 0)
                    is_correct = quality >= 3
                    if is_correct:
                        total_points += quality
                    else:
                        total_points += max(1, quality - 2)
                
                total_problems += total_attempts
                correct_answers += correct_attempts
            
            accuracy_rate = (correct_answers / total_problems * 100) if total_problems > 0 else 0
            
            return {
                "total_problems": total_problems,
                "correct_answers": correct_answers,
                "accuracy_rate": accuracy_rate,
                "total_points": total_points
            }
            
        except Exception as e:
            print(f"ユーザー{uid}の統計計算エラー: {e}")
            return {
                "total_problems": 0,
                "correct_answers": 0, 
                "accuracy_rate": 0,
                "total_points": 0
            }
    
    def update_total_ranking(self):
        """総合ランキングを更新"""
        print("=== 総合ランキング更新開始 ===")
        
        try:
            # 全ユーザーを取得
            users_ref = self.db.collection("users")
            users_docs = users_ref.get()
            
            ranking_data = []
            
            for user_doc in users_docs:
                uid = user_doc.id
                user_data = user_doc.to_dict()
                
                # 学習統計計算  
                stats = self.calculate_user_study_stats(uid)
                
                ranking_entry = {
                    "uid": uid,
                    "nickname": user_data.get("nickname", f"ユーザー{uid[:8]}"),
                    "total_points": stats["total_points"],
                    "total_problems": stats["total_problems"],
                    "accuracy_rate": stats["accuracy_rate"],
                    "last_updated": datetime.now()
                }
                
                ranking_data.append(ranking_entry)
            
            # 総合ポイントでソート
            ranking_data.sort(key=lambda x: x["total_points"], reverse=True)
            
            # Firestoreに保存
            batch = self.db.batch()
            
            for i, entry in enumerate(ranking_data[:100]):  # 上位100位まで
                entry["rank"] = i + 1
                
                # total_rankingコレクションに保存
                doc_ref = self.db.collection("total_ranking").document(entry["uid"])
                batch.set(doc_ref, entry)
            
            batch.commit()
            
            print(f"=== 総合ランキング更新完了: {len(ranking_data)}ユーザー処理 ===")
            
            # 上位5位を表示
            print("\n🏆 総合ランキング Top 5:")
            for i, entry in enumerate(ranking_data[:5]):
                print(f"{i+1}位: {entry['nickname']} - 総ポイント: {entry['total_points']}, 問題数: {entry['total_problems']}")
            
            return True
            
        except Exception as e:
            print(f"総合ランキング更新エラー: {e}")
            return False

    def calculate_mastery_level(self, uid: str) -> dict:
        """習熟度レベルを計算"""
        try:
            # study_cardsコレクションから直接ユーザーデータを取得
            study_cards_ref = self.db.collection("study_cards")
            user_cards_query = study_cards_ref.where("uid", "==", uid)
            user_cards_docs = user_cards_query.get()
            
            mastery_stats = {
                "beginner": 0,      # n <= 1
                "intermediate": 0,  # 2 <= n <= 4
                "advanced": 0,      # 5 <= n <= 9
                "expert": 0,        # n >= 10
                "total_cards": 0,
                "avg_ef": 0.0,
                "avg_interval": 0.0
            }
            
            total_ef = 0
            total_interval = 0
            card_count = 0
            
            for doc in user_cards_docs:
                card_data = doc.to_dict()
                
                # 実際に演習したカードのみを対象とする（historyが存在するか確認）
                history = card_data.get("history", [])
                if not history:  # 演習履歴がないカードはスキップ
                    continue
                
                sm2_data = card_data.get("sm2_data", {})
                
                n = sm2_data.get("n", 0)
                ef = sm2_data.get("ef", 2.5)
                interval = sm2_data.get("interval", 1)
                
                # レベル分類
                if n <= 1:
                    mastery_stats["beginner"] += 1
                elif 2 <= n <= 4:
                    mastery_stats["intermediate"] += 1
                elif 5 <= n <= 9:
                    mastery_stats["advanced"] += 1
                else:
                    mastery_stats["expert"] += 1
                
                total_ef += ef
                total_interval += interval
                card_count += 1
            
            mastery_stats["total_cards"] = card_count
            if card_count > 0:
                mastery_stats["avg_ef"] = total_ef / card_count
                mastery_stats["avg_interval"] = total_interval / card_count
            
            # 習熟度スコア計算（高レベルカードの比率とEF値を考慮）
            if card_count > 0:
                expert_ratio = mastery_stats["expert"] / card_count
                advanced_ratio = mastery_stats["advanced"] / card_count
                mastery_score = (expert_ratio * 100 + advanced_ratio * 50) * mastery_stats["avg_ef"]
            else:
                mastery_score = 0
            
            mastery_stats["mastery_score"] = mastery_score
            
            return mastery_stats
            
        except Exception as e:
            print(f"ユーザー{uid}の習熟度計算エラー: {e}")
            return {
                "beginner": 0, "intermediate": 0, "advanced": 0, "expert": 0,
                "total_cards": 0, "avg_ef": 0.0, "avg_interval": 0.0, "mastery_score": 0
            }

    def update_mastery_ranking(self):
        """習熟度ランキングを更新"""
        print("=== 習熟度ランキング更新開始 ===")
        
        try:
            # 全ユーザーを取得
            users_ref = self.db.collection("users")
            users_docs = users_ref.get()
            
            ranking_data = []
            
            for user_doc in users_docs:
                uid = user_doc.id
                user_data = user_doc.to_dict()
                
                # 習熟度計算
                mastery_stats = self.calculate_mastery_level(uid)
                
                ranking_entry = {
                    "uid": uid,
                    "nickname": user_data.get("nickname", f"ユーザー{uid[:8]}"),
                    "mastery_score": mastery_stats["mastery_score"],
                    "expert_cards": mastery_stats["expert"],
                    "advanced_cards": mastery_stats["advanced"],
                    "total_cards": mastery_stats["total_cards"],
                    "avg_ef": mastery_stats["avg_ef"],
                    "last_updated": datetime.now()
                }
                
                ranking_data.append(ranking_entry)
            
            # 習熟度スコアでソート
            ranking_data.sort(key=lambda x: x["mastery_score"], reverse=True)
            
            # Firestoreに保存
            batch = self.db.batch()
            
            for i, entry in enumerate(ranking_data[:100]):  # 上位100位まで
                entry["rank"] = i + 1
                
                # mastery_rankingコレクションに保存
                doc_ref = self.db.collection("mastery_ranking").document(entry["uid"])
                batch.set(doc_ref, entry)
            
            batch.commit()
            
            print(f"=== 習熟度ランキング更新完了: {len(ranking_data)}ユーザー処理 ===")
            
            # 上位5位を表示
            print("\n🏆 習熟度ランキング Top 5:")
            for i, entry in enumerate(ranking_data[:5]):
                print(f"{i+1}位: {entry['nickname']} - 習熟度スコア: {entry['mastery_score']:.1f}, エキスパートカード: {entry['expert_cards']}")
            
            return True
            
        except Exception as e:
            print(f"習熟度ランキング更新エラー: {e}")
            return False
    def update_weekly_ranking(self):
        """週間ランキングを更新"""
        print("=== 週間ランキング更新開始 ===")
        
        try:
            # 全ユーザーを取得
            users_ref = self.db.collection("users")
            users_docs = users_ref.get()
            
            ranking_data = []
            
            for user_doc in users_docs:
                uid = user_doc.id
                user_data = user_doc.to_dict()
                
                # 週間ポイント計算
                weekly_points = self.calculate_user_weekly_points(uid)
                
                # 学習統計計算  
                stats = self.calculate_user_study_stats(uid)
                
                ranking_entry = {
                    "uid": uid,
                    "nickname": user_data.get("nickname", f"ユーザー{uid[:8]}"),
                    "weekly_points": weekly_points,
                    "total_points": stats["total_points"],
                    "total_problems": stats["total_problems"],
                    "accuracy_rate": stats["accuracy_rate"],
                    "last_updated": datetime.now()
                }
                
                ranking_data.append(ranking_entry)
                print(f"処理完了: {ranking_entry['nickname']} - 週間: {weekly_points}pt, 総合: {stats['total_points']}pt")
            
            # 週間ポイントでソート
            ranking_data.sort(key=lambda x: x["weekly_points"], reverse=True)
            
            # Firestoreに保存
            batch = self.db.batch()
            
            for i, entry in enumerate(ranking_data[:100]):  # 上位100位まで
                entry["rank"] = i + 1
                
                # weekly_rankingコレクションに保存
                doc_ref = self.db.collection("weekly_ranking").document(entry["uid"])
                batch.set(doc_ref, entry)
            
            batch.commit()
            
            print(f"=== 週間ランキング更新完了: {len(ranking_data)}ユーザー処理 ===")
            
            # 上位5位を表示
            print("\n🏆 週間ランキング Top 5:")
            for i, entry in enumerate(ranking_data[:5]):
                print(f"{i+1}位: {entry['nickname']} - 週間ポイント: {entry['weekly_points']}, 総ポイント: {entry['total_points']}")
            
            return True
            
        except Exception as e:
            print(f"週間ランキング更新エラー: {e}")
            return False

def main():
    """メイン実行関数"""
    try:
        updater = StandaloneRankingUpdater()
        
        # 全ランキングを更新
        weekly_success = updater.update_weekly_ranking()
        total_success = updater.update_total_ranking()
        mastery_success = updater.update_mastery_ranking()
        
        if weekly_success and total_success and mastery_success:
            print("\n✅ 全ランキング更新が正常に完了しました")
            print("- 週間ランキング: ✅")
            print("- 総合ランキング: ✅") 
            print("- 習熟度ランキング: ✅")
            return 0
        else:
            print("\n❌ 一部のランキング更新に失敗しました")
            print(f"- 週間ランキング: {'✅' if weekly_success else '❌'}")
            print(f"- 総合ランキング: {'✅' if total_success else '❌'}")
            print(f"- 習熟度ランキング: {'✅' if mastery_success else '❌'}")
            return 1
            
    except Exception as e:
        print(f"実行エラー: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
