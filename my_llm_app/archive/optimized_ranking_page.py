"""
最適化されたランキングページモジュール
enhanced_firestore_optimizer と optimized_weekly_ranking を統合

主な改善点:
1. 最適化されたクエリによる高速化
2. キャッシュ機能の活用
3. 統計データベースの利用
4. バッチ処理による効率化
"""

import streamlit as st
import pandas as pd
from typing import Dict, Any, List, Optional
import datetime

from enhanced_firestore_optimizer import get_cached_firestore_optimizer
from optimized_weekly_ranking import OptimizedWeeklyRankingSystem


def _convert_rankings_to_dataframe(rankings: List) -> pd.DataFrame:
    """OptimizedUserRankingリストをDataFrameに変換"""
    if not rankings:
        return pd.DataFrame()
    
    data = []
    for ranking in rankings:
        data.append({
            'uid': ranking.uid,
            'nickname': ranking.nickname,
            'weekly_points': ranking.weekly_points,
            'total_points': ranking.total_points,
            'mastery_rate': ranking.mastery_rate,
            'total_cards': ranking.total_cards,
            'mastered_cards': ranking.mastered_cards,
            'rank': ranking.rank
        })
    
    return pd.DataFrame(data)


def _render_optimized_weekly_ranking(ranking_system: OptimizedWeeklyRankingSystem, user_profile: dict):
    """最適化された週間ランキング表示"""
    st.subheader("🏆 週間アクティブランキング（最適化版）")
    st.caption("統計データベースから高速取得された今週のランキングです。")
    
    try:
        # 最適化されたランキング取得
        rankings = ranking_system.get_current_week_ranking(50)
        
        if not rankings:
            st.info("今週のアクティブユーザーがいません。")
            return
        
        # ユーザー自身の順位を表示
        if user_profile:
            uid = user_profile.get("uid")
            user_ranking = ranking_system.get_user_ranking_position(uid)
            
            if user_ranking:
                st.success(f"""
                **あなたの今週の成績** 📊
                - **順位**: {user_ranking['rank']}位 / {user_ranking['total_participants']}名
                - **週間ポイント**: {user_ranking['weekly_points']:,} pt
                - **習熟度**: {user_ranking['mastery_rate']:.1f}%
                """)
            else:
                st.info("今週はまだ学習していません。問題に挑戦してランキングに参加しましょう！")
        
        # ランキング表示
        df = _convert_rankings_to_dataframe(rankings)
        
        # 週間ポイントが0より大きいユーザーのみ表示
        active_df = df[df['weekly_points'] > 0]
        
        if active_df.empty:
            st.info("今週アクティブなユーザーがいません。")
            return
        
        # プログレスバー付きの表示
        max_points = int(active_df['weekly_points'].max()) if not active_df.empty else 1
        if max_points <= 0:
            max_points = 1
        
        st.dataframe(
            active_df[['rank', 'nickname', 'weekly_points', 'mastery_rate']].head(20),
            column_config={
                "rank": st.column_config.NumberColumn("順位", format="%d位"),
                "nickname": st.column_config.TextColumn("ニックネーム", width="large"),
                "weekly_points": st.column_config.ProgressColumn(
                    "週間ポイント",
                    format="%d pt",
                    min_value=0,
                    max_value=max_points,
                ),
                "mastery_rate": st.column_config.NumberColumn(
                    "習熟度 (%)",
                    format="%.1f%%",
                    min_value=0,
                    max_value=100,
                ),
            },
            use_container_width=True,
            hide_index=True
        )
        
        # 統計情報表示
        st.info(f"""
        📈 **今週の統計**
        - アクティブユーザー: {len(active_df)}名
        - 最高週間ポイント: {max_points:,} pt
        - 平均習熟度: {active_df['mastery_rate'].mean():.1f}%
        """)
        
    except Exception as e:
        st.error(f"週間ランキングの取得でエラーが発生しました: {e}")


def _render_optimized_total_ranking(ranking_system: OptimizedWeeklyRankingSystem, user_profile: dict):
    """最適化された総合ランキング表示"""
    st.subheader("👑 総合ランキング（最適化版）")
    st.caption("サービス開始からの累計ポイントランキングです。")
    
    try:
        # 全ランキングを取得（総ポイント順）
        rankings = ranking_system.get_current_week_ranking(100)
        
        if not rankings:
            st.info("ランキングデータがありません。")
            return
        
        # 総ポイントでソート
        df = _convert_rankings_to_dataframe(rankings)
        sorted_df = df.sort_values('total_points', ascending=False).reset_index(drop=True)
        sorted_df['total_rank'] = range(1, len(sorted_df) + 1)
        
        # ユーザー順位表示
        if user_profile:
            uid = user_profile.get("uid")
            user_row = sorted_df[sorted_df['uid'] == uid]
            
            if not user_row.empty:
                rank = int(user_row['total_rank'].iloc[0])
                points = int(user_row['total_points'].iloc[0])
                mastery = float(user_row['mastery_rate'].iloc[0])
                
                st.success(f"""
                **あなたの総合成績** 🏆
                - **総合順位**: {rank}位 / {len(sorted_df)}名
                - **総ポイント**: {points:,} pt
                - **習熟度**: {mastery:.1f}%
                """)
        
        # ランキング表示
        st.dataframe(
            sorted_df[['total_rank', 'nickname', 'total_points', 'total_cards', 'mastered_cards']].head(20),
            column_config={
                "total_rank": st.column_config.NumberColumn("順位", format="%d位"),
                "nickname": st.column_config.TextColumn("ニックネーム", width="large"),
                "total_points": st.column_config.NumberColumn("総ポイント", format="%d pt"),
                "total_cards": st.column_config.NumberColumn("学習カード数"),
                "mastered_cards": st.column_config.NumberColumn("習得済みカード数"),
            },
            use_container_width=True,
            hide_index=True
        )
        
        # 統計情報
        st.info(f"""
        📊 **全体統計**
        - 登録ユーザー: {len(sorted_df)}名
        - 最高総ポイント: {sorted_df['total_points'].max():,} pt
        - 平均学習カード数: {sorted_df['total_cards'].mean():.1f}枚
        """)
        
    except Exception as e:
        st.error(f"総合ランキングの取得でエラーが発生しました: {e}")


def _render_optimized_mastery_ranking(ranking_system: OptimizedWeeklyRankingSystem, user_profile: dict):
    """最適化された習熟度ランキング表示"""
    st.subheader("🎯 習熟度ランキング（最適化版）")
    st.caption("学習した問題の知識定着度ランキングです。")
    
    try:
        rankings = ranking_system.get_current_week_ranking(100)
        
        if not rankings:
            st.info("習熟度データがありません。")
            return
        
        # 習熟度でソート（学習カード数が10枚以上のユーザーのみ）
        df = _convert_rankings_to_dataframe(rankings)
        qualified_df = df[df['total_cards'] >= 10]  # 最低10枚学習したユーザーのみ
        sorted_df = qualified_df.sort_values(['mastery_rate', 'total_points'], ascending=[False, False]).reset_index(drop=True)
        sorted_df['mastery_rank'] = range(1, len(sorted_df) + 1)
        
        if sorted_df.empty:
            st.info("習熟度を計算するには10枚以上の問題学習が必要です。")
            return
        
        # ユーザー順位表示
        if user_profile:
            uid = user_profile.get("uid")
            user_row = sorted_df[sorted_df['uid'] == uid]
            
            if not user_row.empty:
                rank = int(user_row['mastery_rank'].iloc[0])
                mastery = float(user_row['mastery_rate'].iloc[0])
                cards = int(user_row['total_cards'].iloc[0])
                mastered = int(user_row['mastered_cards'].iloc[0])
                
                st.success(f"""
                **あなたの習熟度成績** 🎯
                - **習熟度順位**: {rank}位 / {len(sorted_df)}名
                - **習熟度スコア**: {mastery:.1f}%
                - **学習カード**: {cards}枚 (習得済み: {mastered}枚)
                """)
            else:
                st.info("習熟度ランキングに参加するには、10枚以上の問題を学習してください。")
        
        # ランキング表示
        st.dataframe(
            sorted_df[['mastery_rank', 'nickname', 'mastery_rate', 'total_cards', 'mastered_cards']].head(20),
            column_config={
                "mastery_rank": st.column_config.NumberColumn("順位", format="%d位"),
                "nickname": st.column_config.TextColumn("ニックネーム", width="large"),
                "mastery_rate": st.column_config.ProgressColumn(
                    "習熟度スコア",
                    format="%.1f%%",
                    min_value=0,
                    max_value=100,
                ),
                "total_cards": st.column_config.NumberColumn("学習カード数"),
                "mastered_cards": st.column_config.NumberColumn("習得済み"),
            },
            use_container_width=True,
            hide_index=True
        )
        
        # 統計情報
        st.info(f"""
        🧠 **習熟度統計**
        - 参加者: {len(sorted_df)}名 (10枚以上学習)
        - 最高習熟度: {sorted_df['mastery_rate'].max():.1f}%
        - 平均習熟度: {sorted_df['mastery_rate'].mean():.1f}%
        """)
        
    except Exception as e:
        st.error(f"習熟度ランキングの取得でエラーが発生しました: {e}")


def render_optimized_ranking_page(auth_manager=None):
    """最適化されたランキングページのメイン描画関数"""
    st.title("🏆 ランキング（最適化版）")
    
    uid = st.session_state.get("uid")
    if not uid:
        st.warning("ランキングを表示するにはログインが必要です。")
        return
    
    # 最適化されたシステムを初期化
    try:
        ranking_system = OptimizedWeeklyRankingSystem()
        optimizer = get_cached_firestore_optimizer()
        
        # ユーザープロフィール取得
        user_profile = {"uid": uid}
        if auth_manager:
            user_data = auth_manager.get_user_data(uid)
            if user_data:
                user_profile.update(user_data)
        
    except Exception as e:
        st.error(f"最適化システムの初期化でエラーが発生しました: {e}")
        return
    
    # コントロールパネル
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("🔄 統計更新", use_container_width=True, help="全ユーザーの統計データを更新"):
            with st.spinner("統計データを更新中..."):
                success = ranking_system.update_all_user_statistics()
                if success:
                    st.success("統計データを更新しました！")
                    st.rerun()
                else:
                    st.error("統計データの更新に失敗しました。")
    
    with col2:
        if st.button("📸 スナップショット保存", use_container_width=True, help="現在のランキングを保存"):
            with st.spinner("ランキングスナップショットを保存中..."):
                success = ranking_system.save_weekly_ranking_snapshot()
                if success:
                    st.success("ランキングスナップショットを保存しました！")
                else:
                    st.error("スナップショット保存に失敗しました。")
    
    with col3:
        if st.button("🧹 キャッシュクリア", use_container_width=True, help="キャッシュをクリア"):
            st.cache_data.clear()
            st.cache_resource.clear()
            optimizer.clear_cache()
            st.success("キャッシュをクリアしました！")
            st.rerun()
    
    # パフォーマンス情報表示
    with st.expander("📊 システム情報", expanded=False):
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric("キャッシュサイズ", f"{optimizer.get_cache_size()}件")
            
        with col2:
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            st.metric("最終更新", current_time)
    
    # ランキングタブ
    tab1, tab2, tab3 = st.tabs(["🏆 週間アクティブ", "👑 総合", "🎯 習熟度"])
    
    with tab1:
        _render_optimized_weekly_ranking(ranking_system, user_profile)
    
    with tab2:
        _render_optimized_total_ranking(ranking_system, user_profile)
    
    with tab3:
        _render_optimized_mastery_ranking(ranking_system, user_profile)
    
    # フッター情報
    st.markdown("---")
    st.caption("🚀 最適化エンジン使用 - 高速クエリ＆統計データベース活用")


# === 移行テスト用の関数 ===

def test_ranking_optimization():
    """ランキング最適化のテスト"""
    st.title("🧪 ランキング最適化テスト")
    
    try:
        ranking_system = OptimizedWeeklyRankingSystem()
        
        # テスト1: 現在のランキング取得
        st.subheader("テスト1: 最適化ランキング取得")
        with st.spinner("ランキング取得中..."):
            rankings = ranking_system.get_current_week_ranking(10)
            st.success(f"取得成功: {len(rankings)}件")
            
            if rankings:
                for i, ranking in enumerate(rankings[:5], 1):
                    st.write(f"{i}位: {ranking.nickname} - {ranking.weekly_points}pt")
        
        # テスト2: 統計更新
        st.subheader("テスト2: 統計データ更新")
        if st.button("統計更新テスト"):
            with st.spinner("統計更新中..."):
                success = ranking_system.update_all_user_statistics()
                if success:
                    st.success("統計更新成功！")
                else:
                    st.error("統計更新失敗")
        
        # テスト3: スナップショット
        st.subheader("テスト3: スナップショット保存")
        if st.button("スナップショット保存テスト"):
            with st.spinner("スナップショット保存中..."):
                success = ranking_system.save_weekly_ranking_snapshot()
                if success:
                    st.success("スナップショット保存成功！")
                else:
                    st.error("スナップショット保存失敗")
        
    except Exception as e:
        st.error(f"テスト中にエラーが発生しました: {e}")
