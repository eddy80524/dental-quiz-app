#!/usr/bin/env python3
"""
Streamlitでの正しい状態管理とローディング表示のベストプラクティス

問題：ボタンを押すと処理は実行されるが、「None」が画面に表示される
解決：条件分岐でUIの表示を完全に分ける
"""

import streamlit as st
import time

# --- セッションステートの初期化 ---
if 'is_loading' not in st.session_state:
    st.session_state.is_loading = False
if 'my_data' not in st.session_state:
    st.session_state.my_data = None

# --- データ処理関数 ---
def fetch_heavy_data():
    """重い処理のシミュレーション"""
    time.sleep(3)
    return ["データ1", "データ2", "データ3"]

# --- UIの定義 ---
st.title("学習アプリ - ローディング表示ベストプラクティス")

# ボタン処理
if st.button("今日の学習を開始する", key="start_button"):
    st.session_state.is_loading = True
    st.session_state.my_data = None  # 処理開始時にデータをリセット
    st.rerun()  # 画面を再描画してローディング状態を表示

# --- 修正版：UIの表示分けロジック ---
# ✅ 正解パターン：条件分岐で完全に分ける
if st.session_state.is_loading:
    # ローディング中：メッセージのみ表示
    st.info("🔄 セッションを準備中...")
    
    # バックグラウンドで処理実行
    try:
        # 重い処理を実行
        data = fetch_heavy_data()
        
        # 処理完了：結果を保存してフラグを更新
        st.session_state.my_data = data
        st.session_state.is_loading = False
        
        # 処理完了後に画面を再描画
        st.rerun()
        
    except Exception as e:
        # エラー処理
        st.session_state.is_loading = False
        st.error(f"処理中にエラーが発生しました: {str(e)}")
        st.rerun()

elif st.session_state.my_data is not None:
    # データ取得完了：結果を表示
    st.success("✅ データ取得完了!")
    st.write("取得したデータ:")
    
    # データを安全に表示
    for i, item in enumerate(st.session_state.my_data, 1):
        st.write(f"{i}. {item}")
        
    # リセットボタン
    if st.button("リセット", key="reset_button"):
        st.session_state.my_data = None
        st.session_state.is_loading = False
        st.rerun()

else:
    # 初期状態：説明とボタンを表示
    st.info("上のボタンを押して学習を開始してください。")
    
    # デバッグ情報（本番では削除）
    st.write("--- デバッグ情報 ---")
    st.write(f"is_loading: {st.session_state.is_loading}")
    st.write(f"my_data: {st.session_state.my_data}")

# --- ❌ 問題のあるパターン（参考：やってはいけない例） ---
st.markdown("---")
st.markdown("### ❌ 悪い例（Noneが表示される）")

# この書き方だとNoneが表示される
# st.write(st.session_state.my_data)  # ← これが問題

# データが存在しない場合の安全な表示方法
if st.session_state.my_data is None:
    st.write("データが読み込まれていません")
else:
    st.write("データ:", st.session_state.my_data)

# --- 📚 ベストプラクティス集 ---
st.markdown("---")
st.markdown("### 📚 Streamlit状態管理のベストプラクティス")

with st.expander("1. 条件分岐による完全なUI分離"):
    st.code('''
# ✅ 正解：if-elif-else で完全に分ける
if st.session_state.is_loading:
    st.info("処理中...")
    # ローディング中の処理
elif data_ready:
    st.success("完了!")
    # 結果表示
else:
    st.info("ボタンを押してください")
    # 初期状態
''')

with st.expander("2. Noneチェックの重要性"):
    st.code('''
# ❌ ダメ：Noneがそのまま表示される
st.write(st.session_state.my_data)

# ✅ 正解：事前にチェック
if st.session_state.my_data is not None:
    st.write(st.session_state.my_data)
else:
    st.write("データなし")
''')

with st.expander("3. st.rerun()の適切な使用"):
    st.code('''
# フラグ更新後は必ずst.rerun()で画面更新
if st.button("開始"):
    st.session_state.is_loading = True
    st.rerun()  # ← 重要：即座に画面を更新
''')

with st.expander("4. エラーハンドリング"):
    st.code('''
try:
    # 重い処理
    result = heavy_function()
    st.session_state.data = result
    st.session_state.is_loading = False
except Exception as e:
    st.session_state.is_loading = False
    st.error(f"エラー: {e}")
finally:
    st.rerun()
''')
