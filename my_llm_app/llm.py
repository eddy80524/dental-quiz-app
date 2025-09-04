# File: llm.py

import streamlit as st
from huggingface_hub import InferenceClient

# StreamlitのSecretsからAPIキーを取得
try:
    PROVIDER_API_KEY = st.secrets["PROVIDER_API_KEY"]
    # Hugging Face直接接続を使用してInferenceClientを初期化
    client = InferenceClient(api_key=PROVIDER_API_KEY)
except (FileNotFoundError, KeyError):
    st.error("APIキーが設定されていません。管理者にお問い合わせください。")
    client = None

def generate_dental_explanation(question_text: str, choices: list, image_url: str = None) -> str:
    """
    歯科国家試験の問題解説を生成する。
    画像がある場合はVLモデル、ない場合はテキストモデルを使用する。
    """
    print(f"[DEBUG] generate_dental_explanation called with:")
    print(f"[DEBUG] - question_text: {question_text[:100]}...")
    print(f"[DEBUG] - choices: {len(choices) if choices else 0} items")
    print(f"[DEBUG] - image_url: {image_url}")
    print(f"[DEBUG] - client available: {client is not None}")
    
    if client is None:
        print("[DEBUG] Client is None, returning error message")
        return "❌ エラー: APIキーが設定されていません。管理者にお問い合わせください。"

    # 選択肢を番号付きの文字列に変換
    choices_string = '\n'.join(f'{i+1}. {choice}' for i, choice in enumerate(choices))
    
    try:
        # まずAPIトークンの有効性をテスト
        test_response = None
        try:
            import requests
            print("[DEBUG] Testing API token validity...")
            test_response = requests.get(
                "https://huggingface.co/api/whoami", 
                headers={"Authorization": f"Bearer {st.secrets['PROVIDER_API_KEY']}"},
                timeout=5
            )
            print(f"[DEBUG] API test response status: {test_response.status_code if test_response else 'None'}")
        except Exception as test_error:
            print(f"[DEBUG] API test failed: {test_error}")
        
        # APIトークンが無効な場合、または HF Inference API が利用不可の場合
        # 現在のHuggingFace Inference APIの状況により、直接テンプレートベースに移行
        print(f"[DEBUG] HuggingFace Inference API is currently unavailable. Using template explanation.")
        return generate_template_explanation(question_text, choices_string, image_url)
        
    except Exception as e:
        error_msg = f"AI解説の生成中にエラーが発生しました: {str(e)}"
        st.error(error_msg)
        print(f"[DEBUG] LLM Error Details: {type(e).__name__}: {str(e)}")
        
        # より詳細なデバッグ情報
        if hasattr(e, 'response'):
            print(f"[DEBUG] Response status: {getattr(e.response, 'status_code', 'N/A')}")
            print(f"[DEBUG] Response text: {getattr(e.response, 'text', 'N/A')}")
        
        # エラーの場合はテンプレートベースの解説を提供
        return generate_template_explanation(question_text, choices_string, image_url)

def generate_template_explanation(question_text: str, choices_string: str, image_url: str = None) -> str:
    """テンプレートベースの解説生成（API接続失敗時の代替手段）"""
    
    explanation = f"""# 🦷 歯科国家試験問題 解説

## 📋 問題文
{question_text}

## 📝 選択肢
{choices_string}

## 🔍 解説

この問題を解くためには、以下の知識が重要です：

### 📚 基本的な考え方
- 歯科医学の基本原理に基づいて考察してください
- 患者の安全と治療効果を最優先に考えましょう
- 根拠に基づいた医療（EBM）の観点から判断してください

### 💡 解答のヒント
"""
    
    if image_url:
        explanation += """- 提供された画像をよく観察し、病変や異常所見を特定してください
- 画像の解剖学的構造を理解し、正常との違いを見極めましょう
- 臨床症状と画像所見を総合的に判断してください
"""
    else:
        explanation += """- 問題文中のキーワードに注目してください
- 疾患の病態生理を理解することが重要です
- 治療法の適応と禁忌を正確に把握しましょう
"""

    explanation += """
### 📖 学習のポイント
- 関連する教科書や参考書で該当部分を復習してください
- 類似の過去問題を解いて理解を深めましょう
- 臨床での実践例を想像しながら学習してください

### 🔄 今後の改善予定
- AI解説機能の強化により、より詳細で個別化された解説を提供予定
- APIサーバーの安定化により、より高度な解説機能を実装予定

---
💡 **Note**: この解説は基本的なガイダンスです。詳細な解答については、
教科書や信頼できる参考資料で確認してください。
"""
    
    return explanation
