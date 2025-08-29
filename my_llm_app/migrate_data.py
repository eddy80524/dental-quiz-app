"""
データ移行スクリプト - UID統一のための一度限りの実行用スクリプト

このスクリプトは以下の処理を行います:
1. Firestore上の全ユーザーをスキャンし、同じemailを持つ重複アカウントを特定
2. 重複アカウントの学習データを一つの正規uidに統合
3. 統合後の古いデータは削除または別コレクションに移動

使用方法:
python migrate_data.py --dry-run  # 事前確認（実際の変更は行わない）
python migrate_data.py --execute  # 実際にデータ移行を実行
"""

import argparse
import json
import datetime
import time
from collections import defaultdict
from typing import Dict, List, Any, Optional

import firebase_admin
from firebase_admin import credentials, firestore
import streamlit as st


class DataMigrator:
    """データ移行を管理するクラス"""
    
    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        self.db = self._initialize_firestore()
        self.migration_log = []
        self.backup_collection = "migration_backups"
        
    def _initialize_firestore(self):
        """Firestore初期化"""
        try:
            # Streamlit secretsを使用してFirebaseを初期化
            cred_dict = dict(st.secrets["firebase_credentials"])
            cred = credentials.Certificate(cred_dict)
            
            try:
                app = firebase_admin.get_app()
            except ValueError:
                app = firebase_admin.initialize_app(cred)
            
            return firestore.client(app=app)
        except Exception as e:
            print(f"[ERROR] Firebase初期化エラー: {e}")
            raise
    
    def scan_duplicate_accounts(self) -> Dict[str, List[str]]:
        """重複アカウントをスキャン"""
        print("[INFO] 重複アカウントのスキャンを開始...")
        
        # すべてのユーザーを取得
        users_ref = self.db.collection("users")
        users_docs = users_ref.stream()
        
        email_to_uids = defaultdict(list)
        
        for doc in users_docs:
            user_data = doc.to_dict()
            email = user_data.get("email", "").strip().lower()
            
            if email:
                email_to_uids[email].append(doc.id)
        
        # 重複があるemailのみを抽出
        duplicates = {email: uids for email, uids in email_to_uids.items() if len(uids) > 1}
        
        print(f"[INFO] スキャン完了: {len(duplicates)}個の重複メールアドレスを検出")
        for email, uids in duplicates.items():
            print(f"  - {email}: {len(uids)}個のアカウント ({', '.join(uids)})")
        
        return duplicates
    
    def create_backup(self, uid: str, email: str) -> str:
        """データのバックアップを作成"""
        backup_id = f"{uid}_{int(time.time())}"
        backup_data = {
            "original_uid": uid,
            "email": email,
            "backup_timestamp": datetime.datetime.utcnow().isoformat(),
            "user_data": {},
            "user_cards": [],
            "learning_logs": [],
            "session_state": {}
        }
        
        try:
            # ユーザーデータをバックアップ
            user_ref = self.db.collection("users").document(uid)
            user_doc = user_ref.get()
            if user_doc.exists:
                backup_data["user_data"] = user_doc.to_dict()
            
            # ユーザーカードをバックアップ
            cards_ref = self.db.collection("users").document(uid).collection("userCards")
            cards_docs = cards_ref.stream()
            for card_doc in cards_docs:
                card_data = card_doc.to_dict()
                card_data["_doc_id"] = card_doc.id
                backup_data["user_cards"].append(card_data)
            
            # 学習ログをバックアップ
            logs_ref = self.db.collection("learningLogs").where("userId", "==", uid)
            logs_docs = logs_ref.get()
            for log_doc in logs_docs:
                log_data = log_doc.to_dict()
                log_data["_doc_id"] = log_doc.id
                backup_data["learning_logs"].append(log_data)
            
            # セッション状態をバックアップ
            session_ref = self.db.collection("users").document(uid).collection("sessionState").document("current")
            session_doc = session_ref.get()
            if session_doc.exists:
                backup_data["session_state"] = session_doc.to_dict()
            
            if not self.dry_run:
                # バックアップを保存
                backup_ref = self.db.collection(self.backup_collection).document(backup_id)
                backup_ref.set(backup_data)
            
            print(f"[INFO] バックアップ作成: {backup_id} (userCards: {len(backup_data['user_cards'])}, learningLogs: {len(backup_data['learning_logs'])})")
            return backup_id
            
        except Exception as e:
            print(f"[ERROR] バックアップ作成エラー ({uid}): {e}")
            return ""
    
    def merge_user_data(self, primary_uid: str, secondary_uids: List[str], email: str) -> bool:
        """ユーザーデータを統合"""
        print(f"[INFO] データ統合開始: {primary_uid} <- {secondary_uids}")
        
        try:
            # 各UIDのデータをバックアップ
            backup_ids = []
            for uid in [primary_uid] + secondary_uids:
                backup_id = self.create_backup(uid, email)
                if backup_id:
                    backup_ids.append(backup_id)
            
            # プライマリアカウントの現在のカードを取得
            primary_cards = {}
            cards_ref = self.db.collection("users").document(primary_uid).collection("userCards")
            cards_docs = cards_ref.stream()
            for card_doc in cards_docs:
                primary_cards[card_doc.id] = card_doc.to_dict()
            
            # セカンダリアカウントのデータを統合
            total_merged_cards = 0
            total_merged_logs = 0
            
            for secondary_uid in secondary_uids:
                # セカンダリアカウントのカードを取得
                secondary_cards_ref = self.db.collection("users").document(secondary_uid).collection("userCards")
                secondary_cards_docs = secondary_cards_ref.stream()
                
                for card_doc in secondary_cards_docs:
                    card_id = card_doc.id
                    secondary_card = card_doc.to_dict()
                    
                    if card_id in primary_cards:
                        # カードが既に存在する場合は統合
                        primary_card = primary_cards[card_id]
                        merged_card = self._merge_card_data(primary_card, secondary_card)
                        primary_cards[card_id] = merged_card
                    else:
                        # 新しいカードの場合はそのまま追加
                        primary_cards[card_id] = secondary_card
                    
                    total_merged_cards += 1
                
                # 学習ログを統合（プライマリアカウントのuserCardsに既に統合されているため削除）
                logs_ref = self.db.collection("learningLogs").where("userId", "==", secondary_uid)
                logs_docs = logs_ref.get()
                
                for log_doc in logs_docs:
                    if not self.dry_run:
                        log_doc.reference.delete()
                    total_merged_logs += 1
                
                # セカンダリアカウントのユーザーデータを削除
                if not self.dry_run:
                    self.db.collection("users").document(secondary_uid).delete()
            
            # 統合されたカードをプライマリアカウントに保存
            if not self.dry_run:
                batch = self.db.batch()
                for card_id, card_data in primary_cards.items():
                    card_ref = self.db.collection("users").document(primary_uid).collection("userCards").document(card_id)
                    batch.set(card_ref, card_data, merge=True)
                batch.commit()
                
                # 統合完了フラグを設定
                user_ref = self.db.collection("users").document(primary_uid)
                user_ref.update({
                    "data_migration_completed": True,
                    "migration_timestamp": datetime.datetime.utcnow().isoformat(),
                    "merged_uids": secondary_uids,
                    "backup_ids": backup_ids
                })
            
            self.migration_log.append({
                "email": email,
                "primary_uid": primary_uid,
                "merged_uids": secondary_uids,
                "merged_cards": total_merged_cards,
                "merged_logs": total_merged_logs,
                "backup_ids": backup_ids,
                "status": "success" if not self.dry_run else "dry_run"
            })
            
            print(f"[SUCCESS] 統合完了: {total_merged_cards}カード, {total_merged_logs}ログ")
            return True
            
        except Exception as e:
            print(f"[ERROR] データ統合エラー: {e}")
            self.migration_log.append({
                "email": email,
                "primary_uid": primary_uid,
                "merged_uids": secondary_uids,
                "status": "error",
                "error": str(e)
            })
            return False
    
    def _merge_card_data(self, primary_card: Dict[str, Any], secondary_card: Dict[str, Any]) -> Dict[str, Any]:
        """2つのカードデータを統合"""
        # より進んでいる方のカードデータを優先
        primary_n = primary_card.get("n", 0)
        secondary_n = secondary_card.get("n", 0)
        
        if secondary_n > primary_n:
            # セカンダリの方が進んでいる場合
            result = secondary_card.copy()
            # 履歴は両方を統合
            primary_history = primary_card.get("history", [])
            secondary_history = secondary_card.get("history", [])
            all_history = primary_history + secondary_history
            # タイムスタンプでソート
            all_history.sort(key=lambda x: x.get("timestamp", ""))
            result["history"] = all_history
        else:
            # プライマリの方が進んでいるか同じ場合
            result = primary_card.copy()
            # 履歴は両方を統合
            primary_history = primary_card.get("history", [])
            secondary_history = secondary_card.get("history", [])
            all_history = primary_history + secondary_history
            # タイムスタンプでソート
            all_history.sort(key=lambda x: x.get("timestamp", ""))
            result["history"] = all_history
        
        return result
    
    def run_migration(self) -> bool:
        """データ移行の実行"""
        print(f"[INFO] データ移行開始 (DRY_RUN: {self.dry_run})")
        
        # 重複アカウントをスキャン
        duplicates = self.scan_duplicate_accounts()
        
        if not duplicates:
            print("[INFO] 重複アカウントが見つかりませんでした。移行は不要です。")
            return True
        
        # 各重複グループを処理
        for email, uids in duplicates.items():
            print(f"\\n[INFO] 処理中: {email} ({len(uids)}個のアカウント)")
            
            # プライマリアカウントを選択（最新のものまたは最もデータが多いもの）
            primary_uid = self._select_primary_uid(uids)
            secondary_uids = [uid for uid in uids if uid != primary_uid]
            
            print(f"[INFO] プライマリUID: {primary_uid}")
            print(f"[INFO] 統合対象UID: {secondary_uids}")
            
            # データを統合
            success = self.merge_user_data(primary_uid, secondary_uids, email)
            
            if not success:
                print(f"[ERROR] {email} の統合に失敗しました")
                continue
        
        # 移行ログを出力
        self._save_migration_log()
        
        if self.dry_run:
            print("\\n[INFO] DRY RUN完了。実際の変更は行われていません。")
            print("[INFO] 実際に移行を実行するには --execute オプションを使用してください。")
        else:
            print("\\n[SUCCESS] データ移行が完了しました。")
        
        return True
    
    def _select_primary_uid(self, uids: List[str]) -> str:
        """プライマリUIDを選択"""
        # 各UIDのデータ量と最終更新日時を確認
        uid_scores = {}
        
        for uid in uids:
            score = 0
            
            try:
                # ユーザーカード数を確認
                cards_ref = self.db.collection("users").document(uid).collection("userCards")
                cards_count = len(list(cards_ref.stream()))
                score += cards_count * 10  # カード数に重みを付ける
                
                # 最終更新日時を確認
                user_ref = self.db.collection("users").document(uid)
                user_doc = user_ref.get()
                if user_doc.exists:
                    user_data = user_doc.to_dict()
                    last_updated = user_data.get("lastUpdated", "")
                    if last_updated:
                        try:
                            update_time = datetime.datetime.fromisoformat(last_updated)
                            # より新しいアカウントにボーナス
                            days_ago = (datetime.datetime.utcnow() - update_time).days
                            score += max(0, 100 - days_ago)
                        except ValueError:
                            pass
                
                uid_scores[uid] = score
                print(f"  - {uid}: スコア {score} (カード: {cards_count})")
                
            except Exception as e:
                print(f"  - {uid}: エラー {e}")
                uid_scores[uid] = 0
        
        # 最高スコアのUIDを選択
        primary_uid = max(uid_scores, key=uid_scores.get)
        return primary_uid
    
    def _save_migration_log(self):
        """移行ログを保存"""
        log_data = {
            "migration_timestamp": datetime.datetime.utcnow().isoformat(),
            "dry_run": self.dry_run,
            "total_emails_processed": len(self.migration_log),
            "migrations": self.migration_log
        }
        
        # ファイルに保存
        log_filename = f"migration_log_{int(time.time())}.json"
        with open(log_filename, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, indent=2, ensure_ascii=False)
        
        print(f"[INFO] 移行ログを保存しました: {log_filename}")
        
        # Firestoreにも保存（実行時のみ）
        if not self.dry_run:
            try:
                log_ref = self.db.collection("migration_logs").document(f"migration_{int(time.time())}")
                log_ref.set(log_data)
                print(f"[INFO] 移行ログをFirestoreに保存しました")
            except Exception as e:
                print(f"[WARNING] Firestoreへの移行ログ保存に失敗: {e}")


def main():
    parser = argparse.ArgumentParser(description="データ移行スクリプト - UID統一")
    parser.add_argument("--dry-run", action="store_true", help="事前確認モード（実際の変更は行わない）")
    parser.add_argument("--execute", action="store_true", help="実際にデータ移行を実行")
    
    args = parser.parse_args()
    
    if not args.dry_run and not args.execute:
        print("エラー: --dry-run または --execute オプションを指定してください")
        parser.print_help()
        return
    
    if args.execute and args.dry_run:
        print("エラー: --dry-run と --execute は同時に指定できません")
        return
    
    # 実行確認
    if args.execute:
        print("⚠️  警告: 実際にデータ移行を実行します。")
        print("⚠️  この操作は元に戻せません。事前に --dry-run で確認することを強く推奨します。")
        confirmation = input("本当に実行しますか？ (yes/no): ")
        if confirmation.lower() != "yes":
            print("移行をキャンセルしました。")
            return
    
    # データ移行実行
    migrator = DataMigrator(dry_run=args.dry_run)
    success = migrator.run_migration()
    
    if success:
        print("\\n✅ 移行処理が正常に完了しました。")
    else:
        print("\\n❌ 移行処理中にエラーが発生しました。")


if __name__ == "__main__":
    main()
