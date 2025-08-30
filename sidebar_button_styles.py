"""
サイドバーボタンのスタイリッシュデザイン用CSSコード
"""

def apply_sidebar_button_styles():
    """
    サイドバーのボタンにスタイリッシュなデザインを適用する関数
    """
    import streamlit as st
    
    st.markdown("""
    <style>
    /* サイドバーのプライマリボタンのスタイル */
    .stSidebar .stButton > button[kind="primary"] {
        background-color: #0066cc !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        padding: 0.5rem 1rem !important;
        transition: all 0.3s ease !important;
        box-shadow: 0 2px 4px rgba(0, 102, 204, 0.2) !important;
    }

    /* プライマリボタンのホバー効果 */
    .stSidebar .stButton > button[kind="primary"]:hover {
        background-color: #0052a3 !important;
        color: white !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 8px rgba(0, 82, 163, 0.3) !important;
    }

    /* セカンダリボタンのスタイル */
    .stSidebar .stButton > button[kind="secondary"] {
        background-color: #f8f9fa !important;
        color: #0066cc !important;
        border: 2px solid #0066cc !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        padding: 0.5rem 1rem !important;
        transition: all 0.3s ease !important;
    }

    /* セカンダリボタンのホバー効果 */
    .stSidebar .stButton > button[kind="secondary"]:hover {
        background-color: #0066cc !important;
        color: white !important;
        border-color: #0052a3 !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 8px rgba(0, 102, 204, 0.2) !important;
    }

    /* 通常ボタンのスタイル */
    .stSidebar .stButton > button {
        background-color: #6c757d !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 500 !important;
        padding: 0.5rem 1rem !important;
        transition: all 0.3s ease !important;
        width: 100% !important;
    }

    /* 通常ボタンのホバー効果 */
    .stSidebar .stButton > button:hover {
        background-color: #5a6268 !important;
        color: white !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 8px rgba(108, 117, 125, 0.2) !important;
    }

    /* ボタンのアクティブ状態 */
    .stSidebar .stButton > button:active {
        transform: translateY(0px) !important;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1) !important;
    }

    /* フォーカス時のアウトライン除去 */
    .stSidebar .stButton > button:focus {
        outline: none !important;
        box-shadow: 0 0 0 3px rgba(0, 102, 204, 0.3) !important;
    }

    /* サイドバー全体の調整 */
    .stSidebar {
        background-color: #ffffff !important;
    }

    /* サイドバーのタイトル調整 */
    .stSidebar .sidebar-content {
        padding-top: 1rem !important;
    }
    
    /* アラートボックスの垂直中央配置（左寄せは維持） */
    .stAlert [data-testid="stAlertContainer"] {
        display: flex !important;
        align-items: center !important;
        min-height: 60px !important;
    }
    </style>
    """, unsafe_allow_html=True)


def apply_enhanced_sidebar_styles():
    """
    より高度なサイドバーボタンスタイルを適用する関数
    """
    import streamlit as st
    
    st.markdown("""
    <style>
    /* グラデーション背景のプライマリボタン */
    .stSidebar .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #0066cc 0%, #004499 100%) !important;
        color: white !important;
        border: none !important;
        border-radius: 12px !important;
        font-weight: 600 !important;
        padding: 0.75rem 1.5rem !important;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
        box-shadow: 0 4px 12px rgba(0, 102, 204, 0.3) !important;
        font-size: 0.95rem !important;
        letter-spacing: 0.5px !important;
    }

    /* プライマリボタンのホバー効果（グラデーション） */
    .stSidebar .stButton > button[kind="primary"]:hover {
        background: linear-gradient(135deg, #0052a3 0%, #003366 100%) !important;
        transform: translateY(-2px) !important;
        box-shadow: 0 8px 20px rgba(0, 82, 163, 0.4) !important;
    }

    /* セカンダリボタン（アウトライン風） */
    .stSidebar .stButton > button[kind="secondary"] {
        background: transparent !important;
        color: #0066cc !important;
        border: 2px solid #0066cc !important;
        border-radius: 12px !important;
        font-weight: 600 !important;
        padding: 0.75rem 1.5rem !important;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
        position: relative !important;
        overflow: hidden !important;
    }

    /* セカンダリボタンのホバー効果 */
    .stSidebar .stButton > button[kind="secondary"]:hover {
        background: #0066cc !important;
        color: white !important;
        transform: translateY(-2px) !important;
        box-shadow: 0 8px 20px rgba(0, 102, 204, 0.3) !important;
    }

    /* ボタンにリップル効果を追加 */
    .stSidebar .stButton > button::before {
        content: '' !important;
        position: absolute !important;
        top: 50% !important;
        left: 50% !important;
        width: 0 !important;
        height: 0 !important;
        border-radius: 50% !important;
        background: rgba(255, 255, 255, 0.3) !important;
        transform: translate(-50%, -50%) !important;
        transition: width 0.6s, height 0.6s !important;
    }

    .stSidebar .stButton > button:active::before {
        width: 300px !important;
        height: 300px !important;
    }

    /* ダークテーマ対応 */
    @media (prefers-color-scheme: dark) {
        .stSidebar .stButton > button[kind="secondary"] {
            color: #66b3ff !important;
            border-color: #66b3ff !important;
        }
        
        .stSidebar .stButton > button[kind="secondary"]:hover {
            background: #66b3ff !important;
            color: #001122 !important;
        }
    }
    </style>
    """, unsafe_allow_html=True)


# 使用例
if __name__ == "__main__":
    import streamlit as st
    
    # 基本スタイルを適用
    apply_sidebar_button_styles()
    
    # または、より高度なスタイルを適用
    # apply_enhanced_sidebar_styles()
    
    # サイドバーでボタンをテスト
    with st.sidebar:
        st.title("スタイリッシュボタン")
        
        if st.button("プライマリボタン", type="primary", use_container_width=True):
            st.success("プライマリボタンがクリックされました！")
            
        if st.button("セカンダリボタン", type="secondary", use_container_width=True):
            st.info("セカンダリボタンがクリックされました！")
            
        if st.button("通常ボタン", use_container_width=True):
            st.warning("通常ボタンがクリックされました！")
