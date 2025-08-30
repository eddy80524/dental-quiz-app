#!/usr/bin/env python3
"""
Google Analytics セットアップガイド
実際のGoogle Analytics測定IDの取得と設定方法
"""

import streamlit as st

def show_google_analytics_setup():
    """Google Analyticsセットアップガイドを表示"""
    
    st.title("🔧 Google Analytics セットアップガイド")
    
    st.markdown("""
    ## 📊 Google Analytics 4 の設定方法
    
    現在、アプリはプレースホルダーのIDを使用しています。実際のGoogle Analyticsと連携するには以下の手順を実行してください。
    """)
    
    # 現在の設定状況
    st.subheader("🔍 現在の設定状況")
    
    try:
        from enhanced_analytics import enhanced_ga
        current_id = enhanced_ga.ga_measurement_id
        
        if current_id == 'G-XXXXXXXXXX':
            st.error(f"❌ Google Analytics ID: {current_id} (プレースホルダー)")
            st.warning("⚠️ 実際の測定IDの設定が必要です")
        else:
            st.success(f"✅ Google Analytics ID: {current_id}")
            st.info("📊 正常に設定されています")
            
    except Exception as e:
        st.error(f"設定確認エラー: {e}")
    
    # セットアップ手順
    st.subheader("⚙️ セットアップ手順")
    
    st.markdown("""
    ### 1. Google Analytics 4 プロパティの作成
    
    1. [Google Analytics](https://analytics.google.com/) にアクセス
    2. 「管理」→「プロパティを作成」をクリック
    3. プロパティ名: `歯科国試アプリ` 
    4. 国/地域: `日本`
    5. 通貨: `日本円 (JPY)`
    6. 「次へ」をクリック
    
    ### 2. データストリームの設定
    
    1. 「ウェブ」を選択
    2. ウェブサイトのURL: `https://your-app-domain.com`
    3. ストリーム名: `歯科国試ウェブアプリ`
    4. 「ストリームを作成」をクリック
    
    ### 3. 測定IDの取得
    
    1. 作成されたデータストリームをクリック
    2. **測定ID** (G-XXXXXXXXXX形式) をコピー
    """)
    
    # 設定方法
    st.subheader("🛠️ アプリへの設定方法")
    
    # タブで設定方法を分ける
    tab1, tab2, tab3 = st.tabs(["Streamlit Secrets", "環境変数", "直接編集"])
    
    with tab1:
        st.markdown("""
        ### Streamlit Secrets (推奨)
        
        1. `.streamlit/secrets.toml` ファイルを編集:
        
        ```toml
        [secrets]
        google_analytics_id = "G-YOUR-ACTUAL-MEASUREMENT-ID"
        ```
        
        2. アプリを再起動
        """)
        
        # 現在のsecrets.tomlの確認
        st.code("""
# 現在の設定例
google_analytics_id = "G-XXXXXXXXXX"  # ← 実際のIDに置き換え
        """, language="toml")
    
    with tab2:
        st.markdown("""
        ### 環境変数
        
        ターミナルで以下を実行:
        
        ```bash
        export GOOGLE_ANALYTICS_ID="G-YOUR-ACTUAL-MEASUREMENT-ID"
        ```
        
        または `.env` ファイルに追加:
        
        ```env
        GOOGLE_ANALYTICS_ID=G-YOUR-ACTUAL-MEASUREMENT-ID
        ```
        """)
    
    with tab3:
        st.markdown("""
        ### ファイル直接編集
        
        `enhanced_analytics.py` の `_get_ga_measurement_id` メソッドを編集:
        
        ```python
        def _get_ga_measurement_id(self) -> str:
            # 実際のIDを直接指定
            return 'G-YOUR-ACTUAL-MEASUREMENT-ID'
        ```
        
        ⚠️ **注意**: この方法はコードにIDが露出するため推奨しません。
        """)
    
    # 測定ID入力フォーム
    st.subheader("🔧 測定ID設定ツール")
    
    with st.form("ga_setup_form"):
        st.markdown("取得した測定IDを入力してテストできます:")
        
        measurement_id = st.text_input(
            "Google Analytics 測定ID",
            placeholder="G-XXXXXXXXXX",
            help="Google Analytics で取得した測定IDを入力してください"
        )
        
        submitted = st.form_submit_button("設定をテスト")
        
        if submitted and measurement_id:
            if measurement_id.startswith('G-') and len(measurement_id) >= 12:
                st.success(f"✅ 有効な測定ID形式: {measurement_id}")
                
                # テスト用の分析コード生成
                test_script = f"""
                <!-- テスト用Google Analytics -->
                <script async src="https://www.googletagmanager.com/gtag/js?id={measurement_id}"></script>
                <script>
                  window.dataLayer = window.dataLayer || [];
                  function gtag(){{dataLayer.push(arguments);}}
                  gtag('js', new Date());
                  gtag('config', '{measurement_id}');
                  
                  // テストイベント送信
                  gtag('event', 'setup_test', {{
                    'app_name': 'dental_exam_app',
                    'setup_timestamp': new Date().toISOString()
                  }});
                </script>
                """
                
                st.code(test_script, language="html")
                st.info("💡 このコードをブラウザの開発者ツールで実行してテストできます")
                
            else:
                st.error("❌ 無効な測定ID形式です。G-から始まる形式で入力してください。")
    
    # 分析機能プレビュー
    st.subheader("📈 利用可能な分析機能")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        **👤 ユーザー行動分析**
        - ページ遷移追跡
        - 学習セッション分析
        - 機能使用状況
        - エンゲージメント測定
        """)
    
    with col2:
        st.markdown("""
        **📊 学習効果分析**
        - 問題回答パターン
        - 学習進捗追跡
        - 正答率分析
        - セッション時間測定
        """)
    
    # 注意事項
    st.subheader("⚠️ 重要な注意事項")
    
    st.warning("""
    **プライバシーとコンプライアンス**
    
    - ユーザーの個人情報は匿名化されて送信されます
    - 実際の氏名やメールアドレスは追跡されません
    - 学習データは統計的分析のみに使用されます
    - GDPR および日本の個人情報保護法に準拠した実装となっています
    """)
    
    st.info("""
    **分析データの活用**
    
    収集されたデータは以下の目的で使用されます:
    - アプリのユーザビリティ向上
    - 学習効果の最適化
    - 機能改善の優先順位決定
    - パフォーマンス問題の特定
    """)

if __name__ == "__main__":
    show_google_analytics_setup()
