#!/usr/bin/env python3
"""
Streamlitアプリ経由でユーザーの自己評価ログとカードレベルデータを確認するスクリプト
"""

import sys
import os
import json
from datetime import datetime

# my_llm_appのパスを追加
sys.path.append(os.path.join(os.path.dirname(__file__), 'my_llm_app'))

# Streamlitとfirestoreモジュールをインポート
import streamlit as st
from my_llm_app.firestore_db import get_firestore_manager

def check_user_evaluation_data():
    """ユーザーの自己評価ログとカードレベルを確認する"""
    
    st.title("🔍 ユーザーデータ確認ツール")
    st.markdown("---")
    
    # ユーザーIDの入力
    uid = st.text_input(
        "ユーザーID（UID）を入力してください:",
        value="wLAvgm5MPZRnNwTZgFrl9iydUR33",
        help="Firestoreから取得したいユーザーのUIDを入力"
    )
    
    if st.button("📊 データを確認", type="primary"):
        if not uid:
            st.error("ユーザーIDを入力してください")
            return
        
        try:
            # Firestoreマネージャーを取得
            firestore_manager = get_firestore_manager()
            
            with st.spinner("Firestoreからデータを取得中..."):
                # ユーザーのカードデータを取得
                cards = firestore_manager.get_cards(uid)
            
            if not cards:
                st.error("❌ カードデータが見つかりません")
                st.info("このユーザーはまだ学習を開始していない可能性があります")
                return
            
            st.success(f"✅ 取得したカード数: {len(cards)}")
            
            # 分析実行
            analyze_user_data(uid, cards)
            
        except Exception as e:
            st.error(f"❌ エラーが発生しました: {e}")
            import traceback
            st.code(traceback.format_exc())

def analyze_user_data(uid, cards):
    """ユーザーデータを分析して表示"""
    
    st.markdown("---")
    st.header(f"📊 ユーザー分析結果: {uid}")
    
    # 基本統計
    col1, col2, col3, col4 = st.columns(4)
    
    # 自己評価データの分析
    evaluation_stats = {
        "× もう一度": 0,    # quality = 1
        "△ 難しい": 0,      # quality = 2  
        "○ 普通": 0,        # quality = 3
        "◎ 簡単": 0         # quality = 4
    }
    
    total_evaluations = 0
    cards_with_evaluations = 0
    cards_with_history = 0
    level_distribution = {}
    
    # 詳細分析
    for card_id, card_data in cards.items():
        history = card_data.get("history", [])
        level = card_data.get("level", 0)
        
        # レベル分布
        if level not in level_distribution:
            level_distribution[level] = 0
        level_distribution[level] += 1
        
        if history:
            cards_with_history += 1
            has_evaluation = False
            
            # 履歴をチェック
            for entry in history:
                quality = entry.get("quality")
                
                if quality is not None and 1 <= quality <= 4:
                    total_evaluations += 1
                    has_evaluation = True
                    
                    if quality == 1:
                        evaluation_stats["× もう一度"] += 1
                    elif quality == 2:
                        evaluation_stats["△ 難しい"] += 1
                    elif quality == 3:
                        evaluation_stats["○ 普通"] += 1
                    elif quality == 4:
                        evaluation_stats["◎ 簡単"] += 1
            
            if has_evaluation:
                cards_with_evaluations += 1
    
    # 基本統計表示
    with col1:
        st.metric("総カード数", len(cards))
    with col2:
        st.metric("履歴があるカード", cards_with_history)
    with col3:
        st.metric("自己評価があるカード", cards_with_evaluations)
    with col4:
        st.metric("総自己評価回数", total_evaluations)
    
    # 自己評価分布
    if total_evaluations > 0:
        st.markdown("### 📈 自己評価分布")
        
        eval_data = []
        for category, count in evaluation_stats.items():
            percentage = (count / total_evaluations) * 100
            eval_data.append({
                '評価': category,
                '回数': count,
                '割合(%)': round(percentage, 1)
            })
        
        st.dataframe(eval_data, hide_index=True)
        
        # チャート表示
        import pandas as pd
        df = pd.DataFrame(eval_data)
        st.bar_chart(df.set_index('評価')['回数'])
    else:
        st.warning("自己評価データがありません")
    
    # カードレベル分布
    st.markdown("### 🎯 カードレベル分布")
    
    level_data = []
    for level in sorted(level_distribution.keys()):
        count = level_distribution[level]
        percentage = (count / len(cards)) * 100
        level_data.append({
            'レベル': f"レベル{level}",
            'カード数': count,
            '割合(%)': round(percentage, 1)
        })
    
    st.dataframe(level_data, hide_index=True)
    
    # レベル分布チャート
    import pandas as pd
    df_level = pd.DataFrame(level_data)
    st.bar_chart(df_level.set_index('レベル')['カード数'])
    
    # 学習進捗
    st.markdown("### 📚 学習進捗")
    
    mastered_cards = sum(1 for card_data in cards.values() if card_data.get("level", 0) >= 4)
    learning_cards = sum(1 for card_data in cards.values() if 0 < card_data.get("level", 0) < 4)
    new_cards = sum(1 for card_data in cards.values() if card_data.get("level", 0) == 0)
    
    progress_col1, progress_col2, progress_col3 = st.columns(3)
    with progress_col1:
        st.metric("新規カード", new_cards, f"{(new_cards/len(cards)*100):.1f}%")
    with progress_col2:
        st.metric("学習中カード", learning_cards, f"{(learning_cards/len(cards)*100):.1f}%")
    with progress_col3:
        st.metric("習得済みカード", mastered_cards, f"{(mastered_cards/len(cards)*100):.1f}%")
    
    # サンプルカード詳細
    st.markdown("### 🔍 サンプルカード詳細")
    
    sample_cards = []
    for card_id, card_data in list(cards.items())[:5]:
        history = card_data.get("history", [])
        evaluations = [entry.get('quality') for entry in history if entry.get('quality') is not None]
        
        sample_cards.append({
            'カードID': card_id[:12] + "...",
            'レベル': card_data.get("level", 0),
            '履歴件数': len(history),
            '自己評価': str(evaluations) if evaluations else "なし",
            '最新評価': evaluations[-1] if evaluations else "なし"
        })
    
    if sample_cards:
        st.dataframe(sample_cards, hide_index=True)
    
    # データ整合性チェック
    st.markdown("### 🔧 データ整合性チェック")
    
    high_level_low_eval = 0
    low_level_high_eval = 0
    
    for card_id, card_data in cards.items():
        level = card_data.get("level", 0)
        history = card_data.get("history", [])
        
        if history:
            # 最新の評価を取得
            latest_quality = None
            for entry in reversed(history):
                if entry.get("quality") is not None:
                    latest_quality = entry.get("quality")
                    break
            
            if latest_quality:
                # レベルが高いのに最新評価が低い
                if level >= 3 and latest_quality <= 2:
                    high_level_low_eval += 1
                # レベルが低いのに最新評価が高い
                elif level <= 1 and latest_quality >= 3:
                    low_level_high_eval += 1
    
    check_col1, check_col2 = st.columns(2)
    with check_col1:
        st.metric("高レベル低評価カード", high_level_low_eval, 
                 help="レベル3以上なのに最新評価が2以下のカード")
    with check_col2:
        st.metric("低レベル高評価カード", low_level_high_eval,
                 help="レベル1以下なのに最新評価が3以上のカード")
    
    # SM2アルゴリズム関連データ
    st.markdown("### 🧠 SM2アルゴリズム関連データ")
    
    ease_factors = []
    intervals = []
    
    for card_data in cards.values():
        if 'easiness_factor' in card_data:
            ease_factors.append(card_data['easiness_factor'])
        if 'interval' in card_data:
            intervals.append(card_data['interval'])
    
    sm2_col1, sm2_col2 = st.columns(2)
    
    with sm2_col1:
        if ease_factors:
            avg_ease = sum(ease_factors) / len(ease_factors)
            st.metric("平均難易度係数", f"{avg_ease:.2f}", f"{len(ease_factors)}枚")
        else:
            st.metric("平均難易度係数", "データなし")
    
    with sm2_col2:
        if intervals:
            avg_interval = sum(intervals) / len(intervals)
            st.metric("平均復習間隔", f"{avg_interval:.1f}日", f"{len(intervals)}枚")
        else:
            st.metric("平均復習間隔", "データなし")

if __name__ == "__main__":
    st.set_page_config(
        page_title="ユーザーデータ確認ツール",
        page_icon="🔍",
        layout="wide"
    )
    
    check_user_evaluation_data()
