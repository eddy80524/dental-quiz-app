"""
ランキングデータのデバッグ用スクリプト
習熟度とランキングデータの詳細を確認する
"""

import sys
import os
sys.path.append('/Users/utsueito/kokushi-dx-poc/dental-DX-PoC/my_llm_app')

from firestore_db import fetch_ranking_data, get_user_profiles_bulk
import pandas as pd

def debug_ranking_data():
    print("=== ランキングデータのデバッグ ===")
    
    # ランキングデータ取得
    ranking_data = fetch_ranking_data()
    print(f"ランキングデータ件数: {len(ranking_data)}")
    
    if not ranking_data:
        print("ランキングデータが空です")
        return
    
    # データフレーム作成
    df = pd.DataFrame(ranking_data)
    print(f"データフレーム列: {df.columns.tolist()}")
    
    # ユーザープロフィール取得
    if 'uid' in df.columns:
        unique_uids = df['uid'].unique().tolist()
        profiles = get_user_profiles_bulk(unique_uids)
        df['nickname'] = df['uid'].map(lambda uid: profiles.get(uid, {}).get('nickname', f"学習者{uid[:8]}"))
        
        print(f"ユーザープロフィール取得数: {len(profiles)}")
        print("ニックネーム一覧:")
        for uid, nickname in zip(df['uid'], df['nickname']):
            print(f"  {uid[:8]}: {nickname}")
    
    # 習熟度データの詳細確認
    print("\n=== 習熟度データの詳細 ===")
    for i, row in df.iterrows():
        mastery = row.get('mastery_rate', 0)
        weekly = row.get('weekly_points', 0)
        total = row.get('total_points', 0)
        nickname = row.get('nickname', 'Unknown')
        print(f"{nickname}: 習熟度={mastery:.6f}%, 週間={weekly}pt, 総合={total}pt")
    
    # 統計情報
    print(f"\n=== 統計情報 ===")
    print(f"習熟度 > 0 のユーザー数: {len(df[df['mastery_rate'] > 0])}")
    print(f"習熟度 = 0 のユーザー数: {len(df[df['mastery_rate'] == 0])}")
    print(f"習熟度最大値: {df['mastery_rate'].max():.6f}")
    print(f"習熟度最小値: {df['mastery_rate'].min():.6f}")

if __name__ == "__main__":
    debug_ranking_data()
