"""
更新されたランキングシステム
最適化後のFirestoreスキーマに対応
"""
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from firestore_db import get_firestore_manager
from modules.search_page import inject_search_page_styles, get_japan_today


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


def _fetch_ranking_status() -> Optional[Dict[str, Any]]:
    try:
        status_doc = get_firestore_manager().db.collection("ranking_status").document("daily").get()
        if status_doc.exists:
            return status_doc.to_dict()
    except Exception:
        return None
    return None


def _format_processing_time(seconds: float) -> str:
    if seconds is None:
        return "--"
    try:
        value = float(seconds)
    except (TypeError, ValueError):
        return "--"
    if value >= 90:
        return f"{value/60:.1f}分"
    return f"{value:.1f}秒"


def render_updated_weekly_ranking(
    user_profile: dict,
    rankings: Optional[List[Dict[str, Any]]] = None,
    ranking_system: Optional[UpdatedRankingSystem] = None
):
    """更新された週間ランキング表示（Cloud Functions連携版）"""
    st.subheader("🏆 週間ランキング")
    st.caption("この一週間で最もアクティブに学習したユーザーのランキングです。")

    ranking_system = ranking_system or UpdatedRankingSystem()
    if rankings is None:
        rankings = ranking_system.get_weekly_ranking(50)
    
    if not rankings:
        st.info("今週のランキングデータがありません。")
        return
    
    # ユーザー自身の順位を直接Firestoreから取得（セッション状態に依存しない）
    current_nickname = user_profile.get("nickname", f"ユーザー{user_profile.get('uid', '')[:8]}") if user_profile else ""
    
    if user_profile:
        uid = user_profile.get("uid")
        user_position = ranking_system.get_user_position(uid, "weekly")
        
        if user_position:
            rank = int(user_position.get("rank", 0))
            points = int(user_position.get("weekly_points", 0))
            st.success(f"**{current_nickname}** の現在の順位: **{rank}位** ({points} pt)")
        else:
            st.info(f"**{current_nickname}** は週間ランキングにまだ登録されていません。")
    
    # ランキングデータフレームの作成
    if rankings:
        df_data = []
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


def render_updated_total_ranking(
    user_profile: dict,
    rankings: Optional[List[Dict[str, Any]]] = None,
    ranking_system: Optional[UpdatedRankingSystem] = None
):
    """更新された総合ランキング表示（Cloud Functions連携版）"""
    st.subheader("🏅 総合ランキング")
    st.caption("累積学習ポイントによる総合ランキングです。")
    
    ranking_system = ranking_system or UpdatedRankingSystem()
    if rankings is None:
        rankings = ranking_system.get_total_ranking(50)
    
    if not rankings:
        st.info("総合ランキングデータがありません。")
        return
    
    # ユーザー自身の順位を直接Firestoreから取得（セッション状態に依存しない）
    current_nickname = user_profile.get("nickname", f"ユーザー{user_profile.get('uid', '')[:8]}") if user_profile else ""
    
    if user_profile:
        uid = user_profile.get("uid")
        user_position = ranking_system.get_user_position(uid, "total")
        
        if user_position:
            rank = int(user_position.get("rank", 0))
            points = int(user_position.get("total_points", 0))
            problems = int(user_position.get("total_problems", 0))
            accuracy = float(user_position.get("accuracy_rate", 0))
            st.success(f"**{current_nickname}** の現在の順位: **{rank}位** ({points} pt, {problems}問, 正答率{accuracy:.1f}%)")
        else:
            st.info(f"**{current_nickname}** は総合ランキングにまだ登録されていません。")
    
    # ランキングデータフレームの作成
    if rankings:
        df_data = []
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


def render_updated_mastery_ranking(
    user_profile: dict,
    rankings: Optional[List[Dict[str, Any]]] = None,
    ranking_system: Optional[UpdatedRankingSystem] = None
):
    """更新された習熟度ランキング表示（Cloud Functions連携版）"""
    st.subheader("🎓 習熟度ランキング")
    st.caption("SM2アルゴリズムによる習熟度スコアランキングです。")
    
    ranking_system = ranking_system or UpdatedRankingSystem()
    if rankings is None:
        rankings = ranking_system.get_mastery_ranking(50)
    
    if not rankings:
        st.info("習熟度ランキングデータがありません。")
        return
    
    # ユーザー自身の順位を直接Firestoreから取得（セッション状態に依存しない）
    current_nickname = user_profile.get("nickname", f"ユーザー{user_profile.get('uid', '')[:8]}") if user_profile else ""
    
    if user_profile:
        uid = user_profile.get("uid")
        user_position = ranking_system.get_user_position(uid, "mastery")
        
        if user_position:
            rank = int(user_position.get("rank", 0))
            score = float(user_position.get("mastery_score", 0))
            expert_cards = int(user_position.get("expert_cards", 0))
            advanced_cards = int(user_position.get("advanced_cards", 0))
            total_cards = int(user_position.get("total_cards", 0))
            st.success(f"**{current_nickname}** の現在の順位: **{rank}位** (習熟度スコア: {score:.1f}, エキスパート: {expert_cards}, 上級: {advanced_cards}, 総カード: {total_cards})")
        else:
            st.info(f"**{current_nickname}** は習熟度ランキングにまだ登録されていません。")
    
    # ランキングデータフレームの作成
    if rankings:
        df_data = []
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
    """更新されたランキングページ（Cloud Functions連携版）"""
    inject_search_page_styles()

    today_label = get_japan_today().strftime("%Y/%m/%d (%a)")
    user_profile = st.session_state.get("user_profile", {})

    ranking_system = UpdatedRankingSystem()
    weekly_rankings = ranking_system.get_weekly_ranking(50)
    total_rankings = ranking_system.get_total_ranking(50)
    mastery_rankings = ranking_system.get_mastery_ranking(50)
    status_data = _fetch_ranking_status()

    chips: List[str] = []
    if status_data:
        last_updated = status_data.get("updated_at_jst", "未更新")
        total_users = status_data.get("total_users")
        processing_time = _format_processing_time(status_data.get("processing_time_seconds"))
        chips.append(f"<span class='ios-chip'>最終更新 {last_updated}</span>")
        if total_users:
            chips.append(f"<span class='ios-chip'>対象 {int(total_users)}人</span>")
        chips.append(f"<span class='ios-chip'>処理 {processing_time}</span>")
    else:
        chips.append("<span class='ios-chip'>更新ステータス取得不可</span>")

    chips.append(f"<span class='ios-chip'>週間参加 {len(weekly_rankings)}人</span>")

    st.markdown(
        f"""
        <div class="ios-hero">
            <span class="ios-hero__badge">ランキング</span>
            <div class="ios-hero__title">学習ランキングハイライト</div>
            <div class="ios-hero__subtitle">Cloud Functionsで毎朝更新されるランキングから、最新の学習アクティビティを素早く確認できます。今日 ({today_label}) の順位チェックとモチベーションづくりに活用してください。</div>
            <div class="ios-hero__chips">{''.join(chips)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    participant_counts = {
        "weekly": len(weekly_rankings),
        "total": len(total_rankings),
        "mastery": len(mastery_rankings),
    }

    top_weekly = weekly_rankings[0]["weekly_points"] if weekly_rankings else 0
    top_total = total_rankings[0]["total_points"] if total_rankings else 0
    top_mastery = mastery_rankings[0]["mastery_score"] if mastery_rankings else 0.0

    col1, col2, col3 = st.columns(3)
    with col1:
        delta_text = f"トップ {top_weekly} pt" if weekly_rankings else "データなし"
        st.metric("週間参加人数", f"{participant_counts['weekly']} 人", delta=delta_text)
    with col2:
        delta_text = f"トップ {top_total} pt" if total_rankings else "データなし"
        st.metric("総合参加人数", f"{participant_counts['total']} 人", delta=delta_text)
    with col3:
        delta_text = f"トップ {top_mastery:.1f}" if mastery_rankings else "データなし"
        st.metric("習熟度参加人数", f"{participant_counts['mastery']} 人", delta=delta_text)

    st.markdown("---")

    tab1, tab2, tab3 = st.tabs(["📈 週間ランキング", "🏅 総合ランキング", "🎓 習熟度ランキング"])

    with tab1:
        render_updated_weekly_ranking(user_profile, weekly_rankings, ranking_system)

    with tab2:
        render_updated_total_ranking(user_profile, total_rankings, ranking_system)

    with tab3:
        render_updated_mastery_ranking(user_profile, mastery_rankings, ranking_system)

    st.markdown("---")
    st.info("📅 **ランキング更新スケジュール**: 毎朝3時（JST）にCloud Functionsで全ユーザーのランキングが自動更新されます。")

    if status_data:
        last_updated = status_data.get("updated_at_jst", "未更新")
        total_users = status_data.get("total_users", 0)
        processing_time = _format_processing_time(status_data.get("processing_time_seconds"))
        st.caption(f"最終更新: {last_updated} | 対象ユーザー: {int(total_users)}人 | 処理時間: {processing_time}")
    else:
        st.caption("更新ステータス: 取得エラー")
