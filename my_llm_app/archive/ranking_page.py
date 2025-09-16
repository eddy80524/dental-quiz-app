"""
ランキングページの描画とロジックを管理するモジュール

主な変更点:
- シンプルな3種類のランキング表示
- 週間アクティブ、総合、習熟度の各ランキング
- Streamlitのモダンなウィジェットを活用
"""

import streamlit as st
import pandas as pd
from typing import Dict, Any, List, Optional

from firestore_db import fetch_ranking_data, get_user_profile_for_ranking, get_user_profiles_bulk

def _render_weekly_active_ranking(ranking_data: pd.DataFrame, user_profile: dict):
    st.subheader("🏆 週間ランキング")
    st.caption("この一週間で最もアクティブに学習したユーザーのランキングです。")

    if ranking_data.empty:
        st.info("まだ今週のランキングデータがありません。")
        return

    # ユーザー自身の順位を表示
    if user_profile:
        nickname = user_profile.get("nickname", "あなた")
        user_rank_info = ranking_data[ranking_data['nickname'] == nickname]
        if not user_rank_info.empty:
            rank = user_rank_info.index[0] + 1
            points = int(user_rank_info['weekly_points'].iloc[0])
            st.success(f"あなたの順位: **{rank}位** ({points:,} pt)")
        else:
            st.info("あなたはまだ今週のランキングに登場していません。学習してポイントを獲得しましょう！")

    # ランキングテーブルの表示
    max_weekly_points = int(ranking_data['weekly_points'].max()) if not ranking_data.empty else 1
    # min_value と max_value が同じだとエラーになるので、最低でも1に設定
    if max_weekly_points <= 0:
        max_weekly_points = 1
    
    st.dataframe(
        ranking_data[['nickname', 'weekly_points']].head(20),
        column_config={
            "nickname": st.column_config.TextColumn("ニックネーム", width="large"),
            "weekly_points": st.column_config.ProgressColumn(
                "週間ポイント",
                format="%d pt",
                min_value=0,
                max_value=max_weekly_points,
            ),
        },
        use_container_width=True,
        hide_index=True
    )

def _render_total_points_ranking(ranking_data: pd.DataFrame, user_profile: dict):
    st.subheader("👑 総合ランキング")
    st.caption("サービス開始からの累計ポイントに基づいた総合ランキングです。")

    # total_points列でソート
    sorted_by_total = ranking_data.sort_values(by='total_points', ascending=False).reset_index(drop=True)

    if sorted_by_total.empty:
        st.info("まだランキングデータがありません。")
        return

    if user_profile:
        nickname = user_profile.get("nickname", "あなた")
        user_rank_info = sorted_by_total[sorted_by_total['nickname'] == nickname]
        if not user_rank_info.empty:
            rank = user_rank_info.index[0] + 1
            points = int(user_rank_info['total_points'].iloc[0])
            st.info(f"あなたの総合順位: **{rank}位** ({points:,} pt)")

    st.dataframe(
        sorted_by_total[['nickname', 'total_points']].head(20),
        column_config={
            "nickname": st.column_config.TextColumn("ニックネーム", width="large"),
            "total_points": st.column_config.NumberColumn("総ポイント", format="%d pt"),
        },
        use_container_width=True,
        hide_index=True
    )

def _render_mastery_ranking(ranking_data: pd.DataFrame, user_profile: dict):
    st.subheader("🎯 習熟度ランキング")
    st.caption("学習した問題の知識定着度に基づいたランキングです。")

    # 習熟度で降順ソートし、習熟度が同じ場合は総合ポイントで順位付け
    sorted_by_mastery = ranking_data.sort_values(
        by=['mastery_rate', 'total_points'], 
        ascending=[False, False]
    ).reset_index(drop=True)

    if sorted_by_mastery.empty:
        st.info("まだ習熟度データが計算されたユーザーがいません。")
        return

    if user_profile:
        nickname = user_profile.get("nickname", "あなた")
        user_rank_info = sorted_by_mastery[sorted_by_mastery['nickname'] == nickname]
        if not user_rank_info.empty:
            rank = user_rank_info.index[0] + 1
            score = float(user_rank_info['mastery_rate'].iloc[0])
            st.warning(f"あなたの習熟度順位: **{rank}位** ({score:.1f} %)")
        else:
            st.info("あなたはまだランキングに登場していません。学習を始めてみましょう！")

    # 習熟度スコアを数値表示とプログレスバーの両方で表示
    display_data = sorted_by_mastery[['nickname', 'mastery_rate']].head(20).copy()
    
    st.dataframe(
        display_data,
        column_config={
            "nickname": st.column_config.TextColumn("ニックネーム", width="large"),
            "mastery_rate": st.column_config.NumberColumn(
                "習熟度スコア (%)",
                format="%.2f",
                min_value=0,
                max_value=100,
            ),
        },
        use_container_width=True,
        hide_index=True
    )

def render_ranking_page(auth_manager=None):
    """ランキングページのメイン描画関数"""
    st.title("🏆 ランキング")
    uid = st.session_state.get("uid")
    if not uid:
        st.warning("ランキングを表示するにはログインが必要です。")
        return

    if st.button("🔄 データ更新", use_container_width=True):
        # 全てのキャッシュをクリア
        st.cache_data.clear()
        st.cache_resource.clear()
        st.rerun()

    # データ取得
    with st.spinner("最新のランキングデータを取得中..."):
        ranking_data = fetch_ranking_data()
        user_profile = get_user_profile_for_ranking(uid)

    if not ranking_data:
        st.error("ランキングデータの取得に失敗しました。")
        return

    df = pd.DataFrame(ranking_data)

    # nickname列を動的に追加（N+1問題対策のため一括取得を使用）
    if not df.empty and 'uid' in df.columns:
        # 全ユーザーのプロフィールを一括取得
        unique_uids = df['uid'].unique().tolist()
        profiles = get_user_profiles_bulk(unique_uids)
        
        # ニックネームをマッピング
        df['nickname'] = df['uid'].map(lambda uid: profiles.get(uid, {}).get('nickname', f"学習者{uid[:8]}"))
        
        # デバッグ情報の出力
        
        # ランキング参加は強制（全ユーザーが表示される）
    else:
        st.warning("ランキングデータが空か、表示に必要な'uid'列がありません。")
        return
        
    # 各ランキングで利用するポイント列が存在しない場合に備えて、デフォルト値(0)で作成
    required_cols = ['weekly_points', 'total_points', 'mastery_rate']
    for col in required_cols:
        if col not in df.columns:
            df[col] = 0

    # タブUIで3種類のランキングを表示
    tab1, tab2, tab3 = st.tabs(["🏆 週間アクティブ", "👑 総合", "🎯 習熟度"])

    with tab1:
        _render_weekly_active_ranking(df, user_profile)

    with tab2:
        _render_total_points_ranking(df, user_profile)

    with tab3:
        _render_mastery_ranking(df, user_profile)