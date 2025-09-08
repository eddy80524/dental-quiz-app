"""
ランキング集計アップデーター

UIは変えずに、ランキングデータをFirestoreに集計・保存するための内部ユーティリティ。
updated_ranking_page から呼び出されることを想定。

集計先コレクション（UIに合わせて統一）:
- weekly_ranking
- total_ranking
- mastery_ranking

更新ステータス:
- ranking_status/daily に JST 日付で最終更新情報を保存
"""

from __future__ import annotations

import datetime
import re
from typing import Dict, Any, List, Tuple

from google.cloud import firestore
from google.cloud.firestore_v1 import Client as FirestoreClient

import pytz

# import safety: work both when importing as top-level `modules.*` and as package
try:
    from firestore_db import get_firestore_manager  # type: ignore
except ImportError:  # pragma: no cover - fallback
    from my_llm_app.firestore_db import get_firestore_manager  # type: ignore

try:
    from modules.ranking_calculator import (  # type: ignore
        calculate_weekly_points,
        calculate_total_points,
        calculate_mastery_score,
    )
except ImportError:  # pragma: no cover - fallback
    from .ranking_calculator import (  # type: ignore
        calculate_weekly_points,
        calculate_total_points,
        calculate_mastery_score,
    )


JST = pytz.timezone("Asia/Tokyo")


def _today_jst_str() -> str:
    return datetime.datetime.now(JST).date().isoformat()


def _effective_date(now_jst: datetime.datetime | None = None) -> datetime.date:
    """3時基準の"日付"を返す（3:00未満は前日扱い）。"""
    if now_jst is None:
        now_jst = datetime.datetime.now(JST)
    return (now_jst - datetime.timedelta(hours=3)).date()


def _get_user_profiles(db: FirestoreClient) -> List[Dict[str, Any]]:
    """全ユーザーのプロフィールを取得し、重複を除去"""
    profiles = []
    
    print("[DEBUG] ユーザープロフィール取得開始")
    
    # usersコレクションとstudy_cardsコレクションの両方から取得
    try:
        users_docs = db.collection("users").stream()
        for doc in users_docs:
            data = doc.to_dict() or {}
            email = data.get("email", "")
            nickname = data.get("nickname", "")
            
            # None値の処理
            if email is None:
                email = ""
            if nickname is None:
                nickname = ""
                
            email = email.strip().lower() if email else ""
            nickname = nickname.strip() if nickname else ""
            
            profile = {
                "uid": doc.id,
                "email": email,
                "nickname": nickname,
                "source": "users"
            }
            profiles.append(profile)
            print(f"[DEBUG] users からプロフィール取得: {doc.id[:8]} - {nickname or email or f'ユーザー{doc.id[:8]}'}")
    except Exception as e:
        print(f"[ERROR] users コレクション読み込みエラー: {e}")
    
    # study_cardsからユニークユーザーを取得（効率化）
    try:
        # distinctクエリでUIDのみ取得
        cards_query = db.collection("study_cards").select(["uid"])
        cards_docs = cards_query.stream()
        uids_from_cards = set()
        
        for doc in cards_docs:
            data = doc.to_dict() or {}
            uid = data.get("uid")
            if uid and uid not in uids_from_cards:
                uids_from_cards.add(uid)
                
                # usersにない場合は追加
                existing = next((p for p in profiles if p["uid"] == uid), None)
                if not existing:
                    profile = {
                        "uid": uid,
                        "email": "",
                        "nickname": f"ユーザー{uid[:8]}",
                        "source": "study_cards"
                    }
                    profiles.append(profile)
                    print(f"[DEBUG] study_cards からプロフィール取得: {uid[:8]}")
                    
        print(f"[DEBUG] study_cards から {len(uids_from_cards)} 人のユーザーを検出")
    except Exception as e:
        print(f"[ERROR] study_cards コレクション読み込みエラー: {e}")
    
    print(f"[DEBUG] 重複除去前ユーザー数: {len(profiles)}")
    
    # 重複除去処理
    by_uid = {}
    for profile in profiles:
        uid = profile["uid"]
        email = profile["email"]
        nickname = profile["nickname"]
        
        # 正規化処理
        email_norm = email.strip().lower() if email else "none"
        nickname_norm = nickname.strip() if nickname else None
        
        # 重複チェック
        duplicate_found = False
        merge_target_uid = None
        
        for existing_uid, existing_profile in list(by_uid.items()):
            existing_email = existing_profile["email"] or ""
            existing_nickname = existing_profile["nickname"] or ""
            
            if _is_similar_user(uid, email_norm, nickname_norm, 
                              existing_uid, existing_email, existing_nickname):
                if uid != existing_uid:  # 同一UIDは除外
                    print(f"[DEBUG] 重複ユーザー検出: {nickname} (uid:{uid[:8]}, email:{email_norm}) vs {existing_nickname} (uid:{existing_uid[:8]}, email:{existing_email})")
                    
                    # より完全な情報を持つユーザーを判定
                    current_score = _get_profile_completeness_score(
                        {"email": email_norm, "nickname": nickname}, nickname
                    )
                    existing_score = _get_profile_completeness_score(
                        {"email": existing_email, "nickname": existing_nickname}, existing_nickname
                    )
                    
                    if current_score > existing_score:
                        # 現在のユーザーの方が完全 - 既存を置き換え
                        print(f"[DEBUG] より完全なプロフィール: {nickname} (score:{current_score}) > {existing_nickname} (score:{existing_score})")
                        merge_target_uid = existing_uid
                        duplicate_found = False  # 現在のユーザーを保持するため
                        break
                    else:
                        # 既存のユーザーの方が完全 - 現在をスキップ
                        print(f"[DEBUG] 既存ユーザーを保持: {existing_nickname} (score:{existing_score}) >= {nickname} (score:{current_score})")
                        duplicate_found = True
                        break
        
        # マージ対象がある場合は既存を削除
        if merge_target_uid:
            del by_uid[merge_target_uid]
            print(f"[DEBUG] 既存ユーザー削除: {merge_target_uid[:8]}")
        
        if duplicate_found:
            print(f"[DEBUG] 重複ユーザーをスキップ: {nickname}")
            continue
            
        # 重複でない、または優先度の高いユーザーを追加
        print(f"[DEBUG] 新規ユーザー追加: {uid[:8]} - {nickname}")
        by_uid[uid] = profile
    
    print(f"[DEBUG] 最終ユーザー数: {len(by_uid)}")
    return list(by_uid.values())


def _load_user_cards(uid: str) -> Dict[str, Any]:
    """最適化済みのカードローディング（複数のデータソースから読み込み）"""
    fm = get_firestore_manager()
    db = fm.db
    cards = {}
    
    print(f"[DEBUG] カードデータ読み込み開始 - UID: {uid}")
    
    # 1. 従来の userCards コレクションから読み込み
    try:
        cards = fm.load_user_cards(uid)
        print(f"[DEBUG] userCards コレクションから: {len(cards)}件")
        
        # カードが見つかった場合のサンプル情報
        if cards:
            sample_key = list(cards.keys())[0]
            sample_card = cards[sample_key]
            history_count = len(sample_card.get('history', []))
            print(f"[DEBUG] userCards サンプル: {sample_key}, 履歴数: {history_count}")
    except Exception as e:
        print(f"[DEBUG] userCards読み込みエラー: {e}")
        cards = {}
    
    # 2. userCards が空の場合、study_cards コレクションから読み込み
    if not cards:
        try:
            print(f"[DEBUG] study_cards コレクションを検索中...")
            study_cards_ref = db.collection("study_cards")
            user_cards_query = study_cards_ref.where("uid", "==", uid)
            user_cards_docs = user_cards_query.get()
            
            print(f"[DEBUG] study_cards コレクションから: {len(user_cards_docs)}件")
            
            # サンプルドキュメントIDを確認
            if user_cards_docs:
                sample_doc = user_cards_docs[0]
                print(f"[DEBUG] study_cards サンプルID: {sample_doc.id}")
                sample_data = sample_doc.to_dict()
                print(f"[DEBUG] study_cards サンプルデータ: uid={sample_data.get('uid')}, history={len(sample_data.get('history', []))}")
            
            # カードデータを変換（既存の形式に合わせる）
            for doc in user_cards_docs:
                try:
                    card_data = doc.to_dict()
                    question_id = doc.id.split('_')[-1] if '_' in doc.id else doc.id
                    
                    # 既存の形式に変換
                    card = {
                        "q_id": question_id,
                        "uid": card_data.get("uid", uid),
                        "history": card_data.get("history", []),
                        "sm2_data": card_data.get("sm2_data", {}),
                        "performance": card_data.get("performance", {}),
                        "metadata": card_data.get("metadata", {})
                    }
                    
                    # SM2データから既存の形式に変換
                    sm2_data = card_data.get("sm2_data", {})
                    if sm2_data:
                        card.update({
                            "n": sm2_data.get("n", 0),
                            "EF": sm2_data.get("ef", 2.5),
                            "interval": sm2_data.get("interval", 1),
                            "next_review": sm2_data.get("next_review"),
                            "last_review": sm2_data.get("last_review")
                        })
                    
                    cards[question_id] = card
                    
                except Exception as card_error:
                    print(f"[WARNING] カードデータ処理エラー ({doc.id}): {card_error}")
                    continue
                    
        except Exception as e:
            print(f"[ERROR] study_cards読み込みエラー: {e}")
    
    # 3. まだ空の場合、他の可能性のあるコレクションも確認
    if not cards:
        potential_collections = ["cards", "user_cards", "userCards", "learningCards", "learning_data"]
        for collection_name in potential_collections:
            try:
                print(f"[DEBUG] {collection_name} コレクションを検索中...")
                collection_ref = db.collection(collection_name)
                docs = collection_ref.where("uid", "==", uid).limit(5).get()
                if docs:
                    print(f"[DEBUG] {collection_name} コレクションに {len(docs)}件のデータが見つかりました")
                    # 最初の1つでブレイク（データ構造確認用）
                    sample_doc = docs[0]
                    sample_data = sample_doc.to_dict()
                    print(f"[DEBUG] {collection_name} サンプルデータ: {list(sample_data.keys())}")
                    break
                else:
                    print(f"[DEBUG] {collection_name} コレクションにデータなし")
            except Exception as e:
                print(f"[DEBUG] {collection_name} 検索エラー: {e}")
    
    # デバッグ情報
    cards_with_history = 0
    total_history_count = 0
    for q_id, card in cards.items():
        if isinstance(card, dict):
            history = card.get('history', [])
            if history:
                cards_with_history += 1
                total_history_count += len(history)
    
    print(f"[DEBUG] ユーザー {uid[:8]}: 総カード数={len(cards)}, 履歴ありカード数={cards_with_history}, 総履歴数={total_history_count}")
    
    return cards


def _compute_user_metrics(uid: str, nickname: str, cards: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """1ユーザー分の各ランキング用メトリクスを算出。
    returns: (weekly_doc, total_doc, mastery_doc)
    
    改善されたランキングシステム:
    - 最低演習数要件の導入
    - 0ptユーザーの除外
    - 習熟度計算の調整
    """
    print(f"[DEBUG] ユーザー {uid[:8]} ({nickname}) のメトリクス計算開始")
    
    # セッション外集計では evaluation_logs は扱わない（カード履歴ベースで十分）
    weekly_points = calculate_weekly_points(cards, evaluation_logs=None)
    total_points, total_problems, accuracy_rate = calculate_total_points(cards, evaluation_logs=None)
    mastery_score, expert_cards, advanced_cards, total_cards, avg_ef = calculate_mastery_score(cards)

    print(f"[DEBUG] ユーザー {uid[:8]} 基本結果: 週間={weekly_points}pt, 総合={total_points}pt, 問題数={total_problems}")
    
    # ===== ランキング参加資格の判定 =====
    
    # 最低演習数要件
    MIN_PROBLEMS_FOR_RANKING = 10  # 最低10問演習が必要
    MIN_PROBLEMS_FOR_MASTERY = 30  # 習熟度ランキングは30問以上
    MIN_WEEKLY_PROBLEMS = 5        # 週間ランキングは5問以上
    
    # 週間ランキング資格判定
    weekly_eligible = weekly_points > 0 and total_problems >= MIN_WEEKLY_PROBLEMS
    if not weekly_eligible:
        weekly_points = 0  # 資格なしの場合は0に設定
        print(f"[DEBUG] 週間ランキング資格なし: 問題数{total_problems} < {MIN_WEEKLY_PROBLEMS} または週間ポイント=0")
    
    # 総合ランキング資格判定
    total_eligible = total_points > 0 and total_problems >= MIN_PROBLEMS_FOR_RANKING
    if not total_eligible:
        total_points = 0  # 資格なしの場合は0に設定
        print(f"[DEBUG] 総合ランキング資格なし: 問題数{total_problems} < {MIN_PROBLEMS_FOR_RANKING} または総合ポイント=0")
    
    # 習熟度ランキング資格判定と調整
    mastery_eligible = total_problems >= MIN_PROBLEMS_FOR_MASTERY and total_cards > 0
    if not mastery_eligible:
        mastery_score = 0.0  # 資格なしの場合は0に設定
        print(f"[DEBUG] 習熟度ランキング資格なし: 問題数{total_problems} < {MIN_PROBLEMS_FOR_MASTERY}")
    else:
        # 習熟度スコアを演習量で調整（より多く演習したユーザーを優遇）
        volume_bonus = min(total_problems / 100.0, 1.0)  # 最大100%のボーナス
        adjusted_mastery_score = mastery_score * (0.7 + 0.3 * volume_bonus)  # 基本70% + 演習量ボーナス30%
        
        print(f"[DEBUG] 習熟度調整: 元スコア={mastery_score:.2f}, 演習量ボーナス={volume_bonus:.2f}, 調整後={adjusted_mastery_score:.2f}")
        mastery_score = adjusted_mastery_score

    print(f"[DEBUG] ユーザー {uid[:8]} 最終結果: 週間={weekly_points}pt, 総合={total_points}pt, 習熟度={mastery_score:.2f}")

    weekly_doc = {
        "uid": uid,
        "nickname": nickname,
        "weekly_points": int(weekly_points),
        "total_points": int(total_points),
        "accuracy_rate": float(accuracy_rate),
        "total_problems": int(total_problems),
        "eligible": weekly_eligible,  # 資格情報を追加
        "updated_at": datetime.datetime.now(JST).isoformat(),
    }

    total_doc = {
        "uid": uid,
        "nickname": nickname,
        "total_points": int(total_points),
        "total_problems": int(total_problems),
        "accuracy_rate": float(accuracy_rate),
        "eligible": total_eligible,  # 資格情報を追加
        "updated_at": datetime.datetime.now(JST).isoformat(),
    }

    mastery_doc = {
        "uid": uid,
        "nickname": nickname,
        "mastery_score": float(mastery_score),
        "expert_cards": int(expert_cards),
        "advanced_cards": int(advanced_cards),
        "total_cards": int(total_cards),
        "avg_ef": float(avg_ef),
        "eligible": mastery_eligible,  # 資格情報を追加
        "updated_at": datetime.datetime.now(JST).isoformat(),
    }

    return weekly_doc, total_doc, mastery_doc


def update_all_rankings() -> Dict[str, Any]:
    """全ユーザーのランキングを再集計して保存。

    - users を走査
    - 各ユーザーの study_cards を読み出してメトリクス計算
    - 3つのランキングコレクションへ upsert
    - ranking_status/daily に JST 日付で最終更新を記録

    Returns: summary dict
    """
    fm = get_firestore_manager()
    db = fm.db

    profiles = _get_user_profiles(db)
    processed = 0
    errors = 0

    for p in profiles:
        uid = p.get("uid")
        nickname = p.get("nickname", f"ユーザー{uid[:8]}")
        try:
            cards = _load_user_cards(uid)
            weekly_doc, total_doc, mastery_doc = _compute_user_metrics(uid, nickname, cards)

            # 書き込み（ドキュメントIDは uid）
            db.collection("weekly_ranking").document(uid).set(weekly_doc, merge=True)
            db.collection("total_ranking").document(uid).set(total_doc, merge=True)
            db.collection("mastery_ranking").document(uid).set(mastery_doc, merge=True)
            processed += 1
        except Exception:
            errors += 1

    # 既存の重複ドキュメントをクリーンアップ（uid単位で1件に統一）
    def _cleanup_duplicates(col_name: str):
        try:
            docs = list(db.collection(col_name).stream())
            by_uid: dict[str, Any] = {}
            to_delete: List[str] = []
            for d in docs:
                data = d.to_dict() or {}
                uid = str(data.get("uid") or d.id)
                if uid not in by_uid:
                    by_uid[uid] = d
                else:
                    # 既存が doc.id == uid ならそれを優先。それ以外は新旧で1件に
                    keep = by_uid[uid]
                    if keep.id != uid and d.id == uid:
                        # 新しい方（正規ID）を残し、旧 keep を削除対象に
                        to_delete.append(keep.id)
                        by_uid[uid] = d
                    else:
                        to_delete.append(d.id)
            # 削除実行
            for doc_id in to_delete:
                try:
                    db.collection(col_name).document(doc_id).delete()
                except Exception:
                    pass
        except Exception:
            pass

    _cleanup_duplicates("weekly_ranking")
    _cleanup_duplicates("total_ranking")
    _cleanup_duplicates("mastery_ranking")

    # 順位フィールドを付与（クライアントソートでもよいが、利便性のため保存）
    try:
        # weekly
        weekly_docs = db.collection("weekly_ranking").order_by("weekly_points", direction="DESCENDING").stream()
        rank = 1
        for doc in weekly_docs:
            db.collection("weekly_ranking").document(doc.id).update({"rank": rank})
            rank += 1
    except Exception:
        pass

    try:
        # total
        total_docs = db.collection("total_ranking").order_by("total_points", direction="DESCENDING").stream()
        rank = 1
        for doc in total_docs:
            db.collection("total_ranking").document(doc.id).update({"rank": rank})
            rank += 1
    except Exception:
        pass

    try:
        # mastery
        mastery_docs = db.collection("mastery_ranking").order_by("mastery_score", direction="DESCENDING").stream()
        rank = 1
        for doc in mastery_docs:
            db.collection("mastery_ranking").document(doc.id).update({"rank": rank})
            rank += 1
    except Exception:
        pass

    # 更新メタデータ（3時基準の日付で記録）
    try:
        now = datetime.datetime.now(JST)
        status_doc = {
            "last_updated_jst_date": _today_jst_str(),
            "last_effective_date": _effective_date(now).isoformat(),
            "updated_at": now.isoformat(),
        }
        db.collection("ranking_status").document("daily").set(status_doc, merge=True)
    except Exception:
        pass

    return {"processed": processed, "errors": errors, "profiles": len(profiles)}


def should_update_today() -> bool:
    """3時JSTを境に1日1回だけ更新する。
    - 現在時刻が3時未満なら更新しない（前日扱い）
    - 現在時刻が3時以降で、ranking_status/daily.last_effective_date != 現在の有効日付 なら更新
    """
    fm = get_firestore_manager()
    db = fm.db
    try:
        now = datetime.datetime.now(JST)
        # 3時未満は更新対象外
        if now.hour < 3:
            return False
        effective = _effective_date(now).isoformat()
        doc = db.collection("ranking_status").document("daily").get()
        if doc.exists:
            d = doc.to_dict() or {}
            last_effective = d.get("last_effective_date")
            return last_effective != effective
    except Exception:
        # 読み出し失敗時は更新を試みる
        return True
    return True


def update_all_rankings_debug():
    """全ユーザーのランキングスコアを更新（デバッグ用・重複除去対応）"""
    print("\n=== 全ランキング更新開始（デバッグ版・重複除去対応） ===")
    
    try:
        fm = get_firestore_manager()
        db = fm.db
        
        # ユーザープロフィールを取得（重複除去済み）
        profiles = _get_user_profiles(db)
        if not profiles:
            print("ユーザープロフィールが見つかりません")
            return "処理: 0件, エラー: 0件"
        
        print(f"対象ユーザー数: {len(profiles)}")
        
        # プロフィール辞書を作成（UIDをキーとする）
        profile_dict = {profile["uid"]: profile for profile in profiles}
        
        # カード数による重複チェック用辞書
        user_card_counts = {}
        
        # 1回目のパス: 全ユーザーのカード数を取得
        for profile in profiles:
            uid = profile["uid"]
            nickname = profile["nickname"]
            
            try:
                cards = _load_user_cards(uid)
                card_count = len(cards)
                user_card_counts[uid] = {
                    "card_count": card_count,
                    "nickname": nickname,
                    "cards": cards
                }
            except Exception as e:
                print(f"[ERROR] ユーザー {uid[:8]} のカード読み込みエラー: {e}")
                user_card_counts[uid] = {
                    "card_count": 0,
                    "nickname": nickname,
                    "cards": {}
                }
        
        # 2回目のパス: カード数による重複除去
        print("\n--- カード数による重複チェック ---")
        processed_users = set()
        duplicate_users = set()
        
        for uid1, data1 in user_card_counts.items():
            if uid1 in duplicate_users:
                continue
                
            for uid2, data2 in user_card_counts.items():
                if uid1 >= uid2 or uid2 in duplicate_users:
                    continue
                
                # 重複ユーザー検出（拡張版）
                profile1 = profile_dict.get(uid1, {})
                profile2 = profile_dict.get(uid2, {})
                
                is_duplicate = _is_similar_user(
                    nickname1=data1["nickname"],
                    nickname2=data2["nickname"],
                    email1=profile1.get("email", ""),
                    email2=profile2.get("email", ""),
                    uid1=uid1,
                    uid2=uid2
                )
                
                # 重複と判定された場合（カード数が同じか、片方が0の場合）
                duplicate_condition = (
                    is_duplicate and (
                        (data1["card_count"] == data2["card_count"] and data1["card_count"] > 0) or
                        (data1["card_count"] == 0 or data2["card_count"] == 0)
                    )
                )
                
                if duplicate_condition:
                    print(f"[DUPLICATE] 重複ユーザー検出:")
                    print(f"  ユーザー1: {uid1[:8]} - {data1['nickname']} - {profile1.get('email', 'none')} ({data1['card_count']}カード)")
                    print(f"  ユーザー2: {uid2[:8]} - {data2['nickname']} - {profile2.get('email', 'none')} ({data2['card_count']}カード)")
                    
                    # より完全なプロフィールを持つ方を保持
                    profile1_score = _get_profile_completeness_score(profile1, data1["nickname"])
                    profile2_score = _get_profile_completeness_score(profile2, data2["nickname"])
                    
                    if profile1_score >= profile2_score:
                        duplicate_users.add(uid2)
                        print(f"  -> {data1['nickname']} を保持（完全性スコア: {profile1_score} vs {profile2_score}）")
                    else:
                        duplicate_users.add(uid1)
                        print(f"  -> {data2['nickname']} を保持（完全性スコア: {profile2_score} vs {profile1_score}）")
        
        print(f"\n重複除去後の対象ユーザー数: {len(user_card_counts) - len(duplicate_users)}")
        
        # 3回目のパス: 実際のランキング計算
        updated_count = 0
        error_count = 0
        total_cards = 0
        
        for uid, data in user_card_counts.items():
            if uid in duplicate_users:
                print(f"[SKIP] 重複ユーザーをスキップ: {uid[:8]} - {data['nickname']}")
                continue
            
            nickname = data["nickname"]
            cards = data["cards"]
            
            print(f"\n--- ユーザー: {nickname} ({uid[:8]}) ---")
            print(f"  カード数: {len(cards)}")
            
            try:
                # メトリクス計算
                weekly_doc, total_doc, mastery_doc = _compute_user_metrics(uid, nickname, cards)
                
                print(f"  週間ポイント: {weekly_doc.get('weekly_points', 0)}")
                print(f"  総合ポイント: {total_doc.get('total_points', 0)}")
                print(f"  マスタリースコア: {mastery_doc.get('mastery_score', 0):.1f}")
                print(f"  ✓ 計算成功")
                
                updated_count += 1
                total_cards += len(cards)
                
            except Exception as e:
                error_count += 1
                print(f"  ✗ エラー: {e}")
                import traceback
                traceback.print_exc()
        
        summary = f"処理: {updated_count}件, エラー: {error_count}件, 重複除去: {len(duplicate_users)}件, 総カード数: {total_cards}件"
        print(f"\n=== 計算完了: {summary} ===")
        return summary
        
    except Exception as e:
        print(f"全体計算エラー: {e}")
        import traceback
        traceback.print_exc()
        raise


def _get_profile_completeness_score(profile: dict, nickname: str) -> int:
    """プロフィールの完全性をスコア化（高いほど完全）"""
    score = 0
    
    # メールアドレスがある
    if profile.get("email") and profile["email"] != "none":
        score += 10
    
    # ニックネームがある（自動生成でない）
    if nickname and not nickname.startswith("ユーザー") and nickname != "none":
        score += 5
    
    # その他の属性
    if profile.get("created_at"):
        score += 1
    if profile.get("last_login"):
        score += 1
    
    return score


def _is_similar_user(nickname1: str, nickname2: str, email1: str = "", email2: str = "", uid1: str = "", uid2: str = "") -> bool:
    """2つのユーザーが同じユーザーを示しているかを判定（拡張版）"""
    
    # 完全一致チェック：メールアドレス
    if email1 and email2 and email1.lower() == email2.lower() and email1 != "none":
        return True
    
    # UIDがメールアドレスの場合のチェック
    if "@" in uid1 and email2 and uid1.lower() == email2.lower():
        return True
    if "@" in uid2 and email1 and uid2.lower() == email1.lower():
        return True
    if "@" in uid1 and "@" in uid2 and uid1.lower() == uid2.lower():
        return True
    
    # メールアドレスのベース部分比較
    def get_email_base(email_or_uid):
        if "@" in email_or_uid:
            return email_or_uid.split("@")[0].lower()
        return ""
    
    base1 = get_email_base(email1) or get_email_base(uid1)
    base2 = get_email_base(email2) or get_email_base(uid2)
    
    if base1 and base2 and base1 == base2 and len(base1) > 3:
        return True
    
    # ニックネーム正規化
    def normalize_nickname(nick):
        if not nick:
            return ""
        return nick.lower().replace("ユーザー", "").replace("user", "").strip()
    
    norm1 = normalize_nickname(nickname1)
    norm2 = normalize_nickname(nickname2)
    
    # 完全一致
    if norm1 and norm2 and norm1 == norm2 and len(norm1) > 2:
        return True
    
    # 部分文字列マッチング（5文字以上の場合のみ）
    if len(norm1) >= 5 and len(norm2) >= 5:
        if norm1 in norm2 or norm2 in norm1:
            return True
    
    # メールアドレス形式のニックネームの場合
    if "@" in nickname1 or "@" in nickname2:
        base_nick1 = get_email_base(nickname1) or norm1
        base_nick2 = get_email_base(nickname2) or norm2
        
        if base_nick1 and base_nick2 and base_nick1 == base_nick2 and len(base_nick1) > 3:
            return True
    
    # 数字サフィックスを除去しての比較（tkenta05 vs tkenta0522など）
    import re
    clean1 = re.sub(r'\d+$', '', norm1)
    clean2 = re.sub(r'\d+$', '', norm2)
    
    if clean1 and clean2 and len(clean1) > 3 and clean1 == clean2:
        return True
    
    # 共通の文字列パターンをチェック（eddy8052 vs えいとくんなど）
    if base1 and norm2:
        if base1 in norm2 or norm2 in base1:
            return True
    if base2 and norm1:
        if base2 in norm1 or norm1 in base2:
            return True
    
    return False
