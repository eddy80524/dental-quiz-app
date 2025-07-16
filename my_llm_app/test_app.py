import streamlit as st
import firebase_admin
from firebase_admin import credentials
import streamlit_authenticator as stauth # 相互作用をテストするため追加

st.set_page_config(layout="wide")
st.title("Firebase 最小構成テスト")

st.info("このテストは、Firebaseとstreamlit-authenticatorの初期化が単独で成功するかを確認します。")

try:
    # secrets.tomlから認証情報を読み込む
    creds = credentials.Certificate(st.secrets["firebase_credentials"])
    st.write("1. `credentials.Certificate()` の実行に成功しました。")

    # Firebaseを初期化する
    if not firebase_admin._apps:
        firebase_admin.initialize_app(creds)

    st.success("✅ Firebase Admin SDKの初期化に成功しました！")

    # streamlit-authenticatorのダミー設定
    # このライブラリとの相互作用をチェック
    dummy_credentials = {"usernames": {"test": {"name": "Test", "password": "xyz"}}}
    authenticator = stauth.Authenticate(dummy_credentials, "c", "k", 30)

    st.success("✅ streamlit-authenticatorの初期化にも成功しました！")
    st.balloons()
    st.header("結論：初期化プロセスは正常です。問題は`app.py`の他のロジックにあります。")


except Exception as e:
    st.error("❌ 初期化中にエラーが発生しました。")
    st.exception(e) # 詳細なエラーを画面に表示