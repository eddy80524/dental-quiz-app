"""
更新されたランキングシステム
最適化後のFirestoreスキーマに対応
"""
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from firestore_db import get_firestore_manager


class UpdatedRankingSystem:
    """更新されたランキングシステム"""
    
    def __init__(self):
        self.db = get_firestore_manager().db
    
    def get_weekly_ranking(self, limit: int = 50) -> List[Dict[str, Any]]:
        """週間ランキングを取得（資格のあるユーザーのみ）"""
        try:
            ranking_ref = self.db.collection("weekly_ranking")
            # 週間ポイント > 0 のユーザーのみ取得
            query = ranking_ref.where("weekly_points", ">", 0).order_by("weekly_points", direction="DESCENDING").limit(limit)
            docs = query.get()
            
            rankings = []
            for doc in docs:
                data = doc.to_dict()
                # 最低演習数要件をチェック（5問以上）
                if data.get("total_problems", 0) >= 5:
                    rankings.append({
                        "uid": data.get("uid"),
                        "nickname": data.get("nickname", f"ユーザー{data.get('uid', '')[:8]}"),
                        "weekly_points": data.get("weekly_points", 0),
                        "total_points": data.get("total_points", 0),
                        "rank": data.get("rank", 0),
                        "accuracy_rate": data.get("accuracy_rate", 0.0),
                        "total_problems": data.get("total_problems", 0)
                    })
            
            return rankings
            
        except Exception as e:
            print(f"週間ランキング取得エラー: {e}")
            return []
    
    def get_total_ranking(self, limit: int = 50) -> List[Dict[str, Any]]:
        """総合ランキングを取得（資格のあるユーザーのみ）"""
        try:
            ranking_ref = self.db.collection("total_ranking")
            # 総合ポイント > 0 のユーザーのみ取得
            query = ranking_ref.where("total_points", ">", 0).order_by("total_points", direction="DESCENDING").limit(limit)
            docs = query.get()
            
            rankings = []
            for doc in docs:
                data = doc.to_dict()
                # 最低演習数要件をチェック（10問以上）
                if data.get("total_problems", 0) >= 10:
                    rankings.append({
                        "uid": data.get("uid"),
                        "nickname": data.get("nickname", f"ユーザー{data.get('uid', '')[:8]}"),
                        "total_points": data.get("total_points", 0),
                        "total_problems": data.get("total_problems", 0),
                        "rank": data.get("rank", 0),
                        "accuracy_rate": data.get("accuracy_rate", 0.0)
                    })
            
            return rankings
            
        except Exception as e:
            print(f"総合ランキング取得エラー: {e}")
            return []
    
    def get_mastery_ranking(self, limit: int = 50) -> List[Dict[str, Any]]:
        """習熟度ランキングを取得（資格のあるユーザーのみ）"""
        try:
            ranking_ref = self.db.collection("mastery_ranking")
            # 習熟度スコア > 0 のユーザーのみ取得
            query = ranking_ref.where("mastery_score", ">", 0).order_by("mastery_score", direction="DESCENDING").limit(limit)
            docs = query.get()
            
            rankings = []
            for doc in docs:
                data = doc.to_dict()
                # 最低演習数要件をチェック（30問以上）
                total_cards = data.get("total_cards", 0)
                if total_cards >= 30:  # 習熟度ランキングは30問以上
                    rankings.append({
                        "uid": data.get("uid"),
                        "nickname": data.get("nickname", f"ユーザー{data.get('uid', '')[:8]}"),
                        "mastery_score": data.get("mastery_score", 0.0),
                        "expert_cards": data.get("expert_cards", 0),
                        "advanced_cards": data.get("advanced_cards", 0),
                        "total_cards": total_cards,
                        "rank": data.get("rank", 0),
                        "avg_ef": data.get("avg_ef", 0.0)
                    })
            
            return rankings
            
        except Exception as e:
            print(f"習熟度ランキング取得エラー: {e}")
            return []
    
    def get_user_position(self, uid: str, ranking_type: str) -> Optional[Dict[str, Any]]:
        """ユーザーの順位を取得"""
        try:
            collection_name = f"{ranking_type}_ranking"
            doc_ref = self.db.collection(collection_name).document(uid)
            doc = doc_ref.get()
            
            if doc.exists:
                return doc.to_dict()
            else:
                return None
                
        except Exception as e:
            print(f"ユーザー順位取得エラー: {e}")
            return None


def render_updated_weekly_ranking(user_profile: dict):
    """更新された週間ランキング表示"""
    st.subheader("🏆 週間アクティブランキング")
    st.caption("この一週間で最もアクティブに学習したユーザーのランキングです。")
    
    ranking_system = UpdatedRankingSystem()
    rankings = ranking_system.get_weekly_ranking(50)
    
    if not rankings:
        st.info("今週のランキングデータがありません。")
        return
    
    # ユーザー自身の順位を表示（セッション状態から取得）
    user_ranking_data = st.session_state.get('user_ranking_data', {})
    current_nickname = user_profile.get("nickname", f"ユーザー{user_profile.get('uid', '')[:8]}") if user_profile else ""
    
    if user_ranking_data:
        weekly_points = int(user_ranking_data.get("weekly_points", 0))
        st.success(f"**{current_nickname}** の週間ポイント: **{weekly_points} pt** (リアルタイム更新)")
    elif user_profile:
        uid = user_profile.get("uid")
        user_position = ranking_system.get_user_position(uid, "weekly")
        
        if user_position:
            rank = int(user_position.get("rank", 0))
            points = int(user_position.get("weekly_points", 0))
            st.success(f"**{current_nickname}** の順位: **{rank}位** ({points} pt)")
        else:
            st.info(f"**{current_nickname}** は週間ランキングにまだ登録されていません。")
    
    # ランキングデータフレームの作成
    if rankings:
        df_data = []
        current_nickname = user_profile.get("nickname", f"ユーザー{user_profile.get('uid', '')[:8]}") if user_profile else ""
        current_uid = user_profile.get("uid") if user_profile else ""
        
        for ranking in rankings:
            # 現在のユーザーの場合は最新のニックネームを使用
            display_nickname = str(ranking["nickname"])
            if current_uid and ranking.get("uid") == current_uid:
                display_nickname = current_nickname
                
            df_data.append({
                "ニックネーム": display_nickname,
                "週間ポイント": int(ranking["weekly_points"])
            })
        
        df = pd.DataFrame(df_data)
        
        # プログレスバー付きの表示
        max_points = int(df["週間ポイント"].max()) if not df.empty else 1
        
        st.dataframe(
            df,
            column_config={
                "ニックネーム": st.column_config.TextColumn("ニックネーム", width="medium"),
                "週間ポイント": st.column_config.ProgressColumn(
                    "週間ポイント",
                    format="%d pt",
                    min_value=0,
                    max_value=max_points,
                ),
            },
            hide_index=True,
            height=400
        )


def render_updated_total_ranking(user_profile: dict):
    """更新された総合ランキング表示"""
    st.subheader("🏅 総合ランキング")
    st.caption("累積学習ポイントによる総合ランキングです。")
    
    ranking_system = UpdatedRankingSystem()
    rankings = ranking_system.get_total_ranking(50)
    
    if not rankings:
        st.info("総合ランキングデータがありません。")
        return
    
    # ユーザー自身の順位を表示（セッション状態から取得）
    user_ranking_data = st.session_state.get('user_ranking_data', {})
    current_nickname = user_profile.get("nickname", f"ユーザー{user_profile.get('uid', '')[:8]}") if user_profile else ""
    
    if user_ranking_data:
        total_points = int(user_ranking_data.get("total_points", 0))
        total_problems = int(user_ranking_data.get("total_problems", 0))
        accuracy = float(user_ranking_data.get("accuracy_rate", 0))
        st.success(f"**{current_nickname}** の総合スコア: **{total_points} pt** ({total_problems}問, 正答率{accuracy:.1f}%) (リアルタイム更新)")
    elif user_profile:
        uid = user_profile.get("uid")
        user_position = ranking_system.get_user_position(uid, "total")
        
        if user_position:
            rank = int(user_position.get("rank", 0))
            points = int(user_position.get("total_points", 0))
            problems = int(user_position.get("total_problems", 0))
            accuracy = float(user_position.get("accuracy_rate", 0))
            st.success(f"**{current_nickname}** の順位: **{rank}位** ({points} pt, {problems}問, 正答率{accuracy:.1f}%)")
        else:
            st.info(f"**{current_nickname}** は総合ランキングにまだ登録されていません。")
    
    # ランキングデータフレームの作成
    if rankings:
        df_data = []
        current_nickname = user_profile.get("nickname", f"ユーザー{user_profile.get('uid', '')[:8]}") if user_profile else ""
        current_uid = user_profile.get("uid") if user_profile else ""
        
        for ranking in rankings:
            # 現在のユーザーの場合は最新のニックネームを使用
            display_nickname = str(ranking["nickname"])
            if current_uid and ranking.get("uid") == current_uid:
                display_nickname = current_nickname
                
            df_data.append({
                "ニックネーム": display_nickname,
                "総ポイント": int(ranking["total_points"]),
                "問題数": int(ranking["total_problems"]),
                "正答率": f"{float(ranking['accuracy_rate']):.1f}%"
            })
        
        df = pd.DataFrame(df_data)
        
        st.dataframe(
            df,
            column_config={
                "ニックネーム": st.column_config.TextColumn("ニックネーム", width="medium"),
                "総ポイント": st.column_config.NumberColumn("総ポイント", format="%d pt"),
                "問題数": st.column_config.NumberColumn("問題数", format="%d問"),
                "正答率": st.column_config.TextColumn("正答率", width="small"),
            },
            hide_index=True,
            height=400
        )


def render_updated_mastery_ranking(user_profile: dict):
    """更新された習熟度ランキング表示"""
    st.subheader("🎓 習熟度ランキング")
    st.caption("SM2アルゴリズムによる習熟度スコアランキングです。")
    
    ranking_system = UpdatedRankingSystem()
    rankings = ranking_system.get_mastery_ranking(50)
    
    if not rankings:
        st.info("習熟度ランキングデータがありません。")
        return
    
    # ユーザー自身の順位を表示（セッション状態から取得）
    user_ranking_data = st.session_state.get('user_ranking_data', {})
    current_nickname = user_profile.get("nickname", f"ユーザー{user_profile.get('uid', '')[:8]}") if user_profile else ""
    
    if user_ranking_data:
        mastery_score = float(user_ranking_data.get("mastery_score", 0))
        expert_cards = int(user_ranking_data.get("expert_cards", 0))
        advanced_cards = int(user_ranking_data.get("advanced_cards", 0))
        total_cards = int(user_ranking_data.get("total_cards", 0))
        last_updated = user_ranking_data.get("last_updated", "")
        
        st.success(f"**{current_nickname}** の習熟度スコア: **{mastery_score:.1f}** (エキスパート: {expert_cards}, 上級: {advanced_cards}, 総カード: {total_cards}) (リアルタイム更新)")
            
    elif user_profile:
        uid = user_profile.get("uid")
        user_position = ranking_system.get_user_position(uid, "mastery")
        
        if user_position:
            rank = int(user_position.get("rank", 0))
            score = float(user_position.get("mastery_score", 0))
            expert_cards = int(user_position.get("expert_cards", 0))
            st.success(f"**{current_nickname}** の順位: **{rank}位** (習熟度スコア: {score:.1f}, エキスパートカード: {expert_cards})")
        else:
            st.info(f"**{current_nickname}** は習熟度ランキングにまだ登録されていません。")
    
    # ランキングデータフレームの作成
    if rankings:
        df_data = []
        current_nickname = user_profile.get("nickname", f"ユーザー{user_profile.get('uid', '')[:8]}") if user_profile else ""
        current_uid = user_profile.get("uid") if user_profile else ""
        
        for ranking in rankings:
            # 現在のユーザーの場合は最新のニックネームを使用
            display_nickname = str(ranking["nickname"])
            if current_uid and ranking.get("uid") == current_uid:
                display_nickname = current_nickname
                
            df_data.append({
                "ニックネーム": display_nickname,
                "習熟度スコア": float(ranking["mastery_score"]),
                "エキスパート": int(ranking["expert_cards"]),
                "上級": int(ranking["advanced_cards"]),
                "総カード数": int(ranking["total_cards"])
            })
        
        df = pd.DataFrame(df_data)
        
        st.dataframe(
            df,
            column_config={
                "ニックネーム": st.column_config.TextColumn("ニックネーム", width="medium"),
                "習熟度スコア": st.column_config.NumberColumn("習熟度スコア", format="%.1f"),
                "エキスパート": st.column_config.NumberColumn("エキスパート", format="%d枚"),
                "上級": st.column_config.NumberColumn("上級", format="%d枚"),
                "総カード数": st.column_config.NumberColumn("総カード数", format="%d枚"),
            },
            hide_index=True,
            height=400
        )


def render_updated_ranking_page():
    """更新されたランキングページ"""
    st.title("📊 学習ランキング")
    st.markdown("---")
    
    # ユーザープロフィール取得
    user_profile = st.session_state.get("user_profile", {})
    
    # サイドバーでランキング表示設定
    with st.sidebar:
        st.subheader("🎭 ランキング表示設定")
        
        if user_profile:
            current_nickname = user_profile.get("nickname", f"ユーザー{user_profile.get('uid', '')[:8]}")
            
            # ニックネーム変更
            new_nickname = st.text_input(
                "ランキング表示名",
                value=current_nickname,
                help="ランキングで表示される名前を変更できます",
                key="ranking_nickname_input"
            )
            
            # ニックネーム更新ボタン
            if st.button("💾 表示名を更新", type="secondary"):
                if new_nickname and new_nickname != current_nickname:
                    try:
                        # Firestoreのユーザープロフィールを更新
                        uid = user_profile.get("uid")
                        db = get_firestore_manager().db
                        db.collection("users").document(uid).update({
                            "nickname": new_nickname
                        })
                        
                        # セッション状態も更新
                        st.session_state["user_profile"]["nickname"] = new_nickname
                        
                        # ランキングキャッシュをクリア（即座にUI反映のため）
                        if hasattr(st.session_state, '_cache'):
                            st.session_state._cache.clear()
                        
                        st.success(f"✅ 表示名を「{new_nickname}」に更新しました！")
                        st.info("📌 全体ランキングへの反映は毎朝3時の定期更新で行われます。")
                        
                        # ページをリロードして即座に反映
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"❌ 表示名の更新に失敗しました: {e}")
                elif new_nickname == current_nickname:
                    st.info("表示名に変更はありません。")
                else:
                    st.warning("表示名を入力してください。")
        else:
            st.info("ログインすると表示名を設定できます。")
        
        st.markdown("---")
    
    # 初回ランキングデータ計算（セッション状態にない場合）
    if not st.session_state.get('user_ranking_data') and user_profile:
        try:
            from modules.ranking_calculator import update_user_ranking_scores
            uid = user_profile.get("uid")
            cards = st.session_state.get("cards", {})
            evaluation_logs = st.session_state.get('evaluation_logs', [])
            nickname = user_profile.get('nickname', f"ユーザー{uid[:8]}")
            update_user_ranking_scores(uid, cards, evaluation_logs, nickname)
        except ImportError:
            pass
        except Exception as e:
            pass
    
    # タブで切り替え
    tab1, tab2, tab3 = st.tabs(["📈 週間ランキング", "🏅 総合ランキング", "🎓 習熟度ランキング"])
    
    with tab1:
        render_updated_weekly_ranking(user_profile)
    
    with tab2:
        render_updated_total_ranking(user_profile)
    
    with tab3:
        render_updated_mastery_ranking(user_profile)
    
    # ランキング更新情報
    st.markdown("---")
    st.info("📅 **ランキング更新スケジュール**: 毎朝3時（JST）に全ユーザーのランキングが自動更新されます。")
    
    # 最終更新ステータス
    try:
        db = get_firestore_manager().db
        status_doc = db.collection("ranking_status").document("daily").get()
        if status_doc.exists:
            status_data = status_doc.to_dict()
            last_updated = status_data.get("updated_at", "未更新")
            st.caption(f"最終更新: {last_updated}")
        else:
            st.caption("更新ステータス: 未初期化")
    except Exception:
        st.caption("更新ステータス: 取得エラー")
