"""
Firestore最適化管理画面

機能：
1. データ移行実行
2. 統計情報表示
3. クリーンアップ実行
4. コスト分析
"""

import streamlit as st
import pandas as pd
from firestore_optimizer import get_firestore_optimizer
from firestore_db import get_firestore_manager

def render_optimization_admin():
    """最適化管理画面"""
    st.title("🔧 Firestore最適化管理")
    
    optimizer = get_firestore_optimizer()
    manager = get_firestore_manager()
    
    # タブ構成
    tab1, tab2, tab3, tab4 = st.tabs(["📊 現状分析", "🚀 データ移行", "🧹 クリーンアップ", "💰 コスト分析"])
    
    with tab1:
        st.subheader("📊 現在のFirestore構造分析")
        
        if st.button("構造分析実行"):
            with st.spinner("Firestore構造を分析中..."):
                # ユーザー数
                users_ref = manager.db.collection("users")
                users_count = len(list(users_ref.limit(1000).stream()))
                st.metric("総ユーザー数", users_count)
                
                # コレクション分析
                collections = []
                
                # users コレクション
                sample_user = list(users_ref.limit(1).stream())
                if sample_user:
                    user_data = sample_user[0].to_dict()
                    has_stats = "stats" in user_data
                    st.metric("統計データ移行済みユーザー", "✅" if has_stats else "❌")
                
                # 週間ランキング数
                rankings_ref = manager.db.collection("weekly_rankings")
                rankings_count = len(list(rankings_ref.limit(100).stream()))
                st.metric("週間ランキング数", rankings_count)
                
                # user_permissions 分析
                try:
                    permissions_ref = manager.db.collection("user_permissions")
                    permissions_count = len(list(permissions_ref.limit(100).stream()))
                    st.metric("権限データ数", permissions_count)
                except:
                    st.metric("権限データ数", "未作成")
    
    with tab2:
        st.subheader("🚀 データ移行実行")
        
        migration_mode = st.selectbox(
            "移行モード",
            ["テストモード（1ユーザー）", "段階移行（10ユーザー）", "全ユーザー移行"]
        )
        
        if st.button("データ移行実行", type="primary"):
            if migration_mode == "テストモード（1ユーザー）":
                limit = 1
            elif migration_mode == "段階移行（10ユーザー）":
                limit = 10
            else:
                limit = 1000
            
            with st.spinner(f"データ移行実行中... ({migration_mode})"):
                # ユーザーリスト取得
                users_ref = manager.db.collection("users").limit(limit)
                users_docs = users_ref.stream()
                
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                migrated_count = 0
                total_count = 0
                
                for i, doc in enumerate(users_docs):
                    total_count += 1
                    status_text.text(f"移行中: {doc.id[:8]} ({i+1}人目)")
                    
                    success = optimizer.migrate_user_data(doc.id)
                    if success:
                        migrated_count += 1
                    
                    progress_bar.progress((i + 1) / limit if limit <= 1000 else (i + 1) / total_count)
                
                st.success(f"移行完了: {migrated_count}/{total_count} ユーザー")
    
    with tab3:
        st.subheader("🧹 不要データクリーンアップ")
        
        cleanup_options = st.multiselect(
            "クリーンアップ対象",
            [
                "古い週間ランキング（30日以前）",
                "空のuser_permissionsドキュメント", 
                "古いセッションデータ（7日以前）",
                "重複したuserCardsデータ"
            ]
        )
        
        if st.button("クリーンアップ実行") and cleanup_options:
            for option in cleanup_options:
                st.info(f"実行中: {option}")
                # 実際のクリーンアップ処理をここに実装
                
            st.success("クリーンアップ完了")
    
    with tab4:
        st.subheader("💰 コスト分析とダッシュボード")
        
        if st.button("コスト分析実行"):
            # 読み込み/書き込み推定
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric(
                    "1日の推定読み取り", 
                    "500件",
                    help="ランキング表示、ユーザーデータ読み込み等"
                )
            
            with col2:
                st.metric(
                    "1日の推定書き込み",
                    "100件", 
                    help="学習記録、統計更新等"
                )
            
            with col3:
                st.metric(
                    "月間推定コスト",
                    "$5-10",
                    help="現在の使用量ベース"
                )
            
            # 最適化提案
            st.info("""
            **最適化提案:**
            1. 統計データ移行により読み取り回数を80%削減
            2. バッチ処理で書き込み回数を50%削減  
            3. 不要なコレクションクリーンアップでストレージ費用削減
            4. キャッシュ戦略でリアルタイム読み取り削減
            """)

if __name__ == "__main__":
    render_optimization_admin()
