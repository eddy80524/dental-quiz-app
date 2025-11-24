import streamlit as st
import random
from typing import List, Dict, Optional
from utils import get_secure_image_url

# 高画質画像表示用のCSS
def inject_image_quality_css():
    """画像表示品質向上のためのCSSを追加"""
    st.markdown("""
    <style>
    /* 画像のレスポンシブ表示設定 */
    .stImage > img {
        image-rendering: -webkit-optimize-contrast;
        image-rendering: crisp-edges;
        max-width: 100% !important;
        width: auto !important;
        height: auto;
        border-radius: 8px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        transition: transform 0.2s ease;
        object-fit: contain;
    }
    
    /* 画像のホバー効果 */
    .stImage > img:hover {
        transform: scale(1.02);
        box-shadow: 0 4px 16px rgba(0,0,0,0.15);
    }
    
    /* エクスパンダー内の画像調整 */
    .streamlit-expanderContent .stImage {
        margin: 10px 0;
        width: 100%;
    }
    
    /* 画像コンテナのレスポンシブ対応 */
    .stImage {
        width: 100%;
        max-width: 100%;
        overflow: hidden;
    }
    
    /* 画像キャプションのスタイル改善 */
    .stImage > div {
        text-align: center;
        font-size: 14px;
        color: #666;
        margin-top: 8px;
    }
    </style>
    """, unsafe_allow_html=True)


class QuestionComponent:
    """問題表示コンポーネント（Reactライクな設計）"""
    
    @staticmethod
    def format_chemical_formula(text: str) -> str:
        """化学式をLaTeX形式に変換"""
        if not text:
            return text
        
        # よく使われる化学式パターンの変換
        replacements = {
            'Ca2+': r'$\mathrm{Ca^{2+}}$',
            'Mg2+': r'$\mathrm{Mg^{2+}}$',
            'H2O': r'$\mathrm{H_2O}$',
            'CO2': r'$\mathrm{CO_2}$',
            'OH-': r'$\mathrm{OH^-}$',
            'HCO3-': r'$\mathrm{HCO_3^-}$',
            'PO4-': r'$\mathrm{PO_4^-}$'
        }
        
        for pattern, replacement in replacements.items():
            text = text.replace(pattern, replacement)
        
        return text
    
    @staticmethod
    def get_image_source(question_data: Dict) -> Optional[str]:
        """
        問題データから画像ソースを取得する
        
        Args:
            question_data (Dict): 問題データの辞書
            
        Returns:
            Optional[str]: 画像URL/パス、または None
        """
        # まず image_urls をチェック
        image_urls = question_data.get('image_urls')
        if image_urls and len(image_urls) > 0:
            return image_urls[0]
        
        # 次に image_paths をチェック
        image_paths = question_data.get('image_paths')
        if image_paths and len(image_paths) > 0:
            return image_paths[0]
        
        # 両方とも空またはNoneの場合はNoneを返す
        return None
    
    @staticmethod
    def render_question_display(questions: List[Dict], case_data: Dict = None):
        """問題表示コンポーネント"""
        # CSSで余白を削除
        st.markdown("""
        <style>
        .st-emotion-cache-r44huj {
            margin-bottom: 0 !important;
            padding-bottom: 0 !important;
        }
        div[style*="background-color: rgb(250, 250, 250)"] {
            margin-top: 0 !important;
            padding-top: 12px !important;
        }
        [data-testid="stElementContainer"] {
            margin-top: 0 !important;
            margin-bottom: 0.25rem !important;
        }
        </style>
        """, unsafe_allow_html=True)
        
        # 症例情報エリア（連問の場合）
        if case_data and case_data.get('scenario_text'):
            with st.container():
                st.markdown(
                    f"""
                    <div style="
                        background-color: #e3f2fd; 
                        padding: 12px 16px; 
                        border-radius: 8px; 
                        border-left: 4px solid #2196f3; 
                        margin-bottom: 16px;
                    ">
                        📋 <strong>症例:</strong> {case_data['scenario_text']}
                    </div>
                    """, 
                    unsafe_allow_html=True
                )
            st.markdown("---")
        
        # 問題表示エリア
        for i, question in enumerate(questions):
            with st.container():
                # 問題ID
                question_number = question.get('number', '')
                if question_number:
                    st.markdown(f"#### {question_number}")
                
                # 問題文（化学式対応）
                question_text = QuestionComponent.format_chemical_formula(
                    question.get('question', '')
                )
                st.markdown(question_text)
                
                # 画像表示（問題文の後）
                image_urls = question.get('image_urls', []) or []
                image_paths = question.get('image_paths', []) or []
                all_images = image_urls + image_paths  # 両方のキーから画像を取得
                
                if all_images:
                    # 高画質表示用CSSを適用
                    inject_image_quality_css()
                    
                    for img_index, img_url in enumerate(all_images):
                        try:
                            # Firebase Storageのパスを署名付きURLに変換
                            secure_url = get_secure_image_url(img_url)
                            
                            if secure_url:
                                # 画像を高品質で表示（レスポンシブ対応）
                                with st.expander(f"📸 問題 {question_number} の図 {img_index + 1}", expanded=True):
                                    st.image(
                                        secure_url, 
                                        caption=f"問題 {question_number} の図 {img_index + 1}",
                                        use_container_width=True  # コンテナ幅に合わせてレスポンシブ表示
                                    )
                            else:
                                st.warning(f"画像URLの生成に失敗しました: {img_url}")

                        except Exception as e:
                            st.warning(f"画像を読み込めませんでした: {img_url}")
                            st.exception(e)
                
                # 問題間の区切り
                if i < len(questions) - 1:
                    st.markdown("---")
    
    @staticmethod
    def shuffle_choices_with_mapping(choices: List[str]) -> tuple[List[str], dict]:
        """選択肢をシャッフルし、元のインデックスとの対応マップを返す"""
        if not choices:
            return [], {}
        
        # 元のインデックスとのマッピングを作成
        indexed_choices = [(i, choice) for i, choice in enumerate(choices)]
        random.shuffle(indexed_choices)
        
        shuffled_choices = [choice for _, choice in indexed_choices]
        # 新しいラベル → 元のラベルのマッピング
        label_mapping = {}
        for new_index, (original_index, _) in enumerate(indexed_choices):
            new_label = chr(ord('A') + new_index)
            original_label = chr(ord('A') + original_index)
            label_mapping[new_label] = original_label
        
        return shuffled_choices, label_mapping
    
    @staticmethod
    def get_choice_label(index: int) -> str:
        """選択肢のラベル生成 (A, B, C...)"""
        return chr(65 + index)
