# File: llm.py

import requests
import streamlit as st
import json
import time

# StreamlitのSecretsからAPIキーを取得
try:
    HF_API_TOKEN = st.secrets["HF_API_TOKEN"]
except (FileNotFoundError, KeyError):
    # ローカル環境でsecrets.tomlがない場合のためのフォールバック
    HF_API_TOKEN = None
    print("[WARNING] HF_API_TOKEN が見つかりません。LLM機能は無効化されます。")
    print("         secrets.tomlファイルに HF_API_TOKEN = \"your_token_here\" を追加してください。")


def generate_dental_explanation(question_text: str, choices: list, image_url: str = None) -> str:
    """
    歯科国家試験の問題解説を生成する。
    現在はテンプレートベースの解説を提供
    """
    
    # APIトークンが設定されていない場合はエラーメッセージを返す
    if not HF_API_TOKEN:
        return "❌ エラー: Hugging Face APIトークンが設定されていません。\n\n" \
               "管理者にお問い合わせください。または、secrets.tomlファイルに " \
               "HF_API_TOKEN を追加してください。"
    
    try:
        # APIトークンの有効性を確認
        if test_hf_connection():
            st.success("✅ AI解説機能が利用可能です")
        else:
            st.warning("⚠️ AI解説機能は現在利用できません。基本的な解説を表示します。")
        
        # テンプレートベースの解説を生成
        return generate_template_explanation(question_text, choices, image_url)
        
    except Exception as e:
        st.error(f"解説の生成中に予期せぬエラーが発生しました: {e}")
        return generate_template_explanation(question_text, choices, image_url)


def test_hf_connection() -> bool:
    """Hugging Face APIの接続テスト"""
    if not HF_API_TOKEN:
        return False
    
    try:
        headers = {"Authorization": f"Bearer {HF_API_TOKEN}"}
        response = requests.get("https://huggingface.co/api/whoami", headers=headers, timeout=5)
        return response.status_code == 200
    except:
        return False


def generate_template_explanation(question_text: str, choices: list, image_url: str = None) -> str:
    """テンプレートベースの解説生成"""
    
    explanation = f"""# 🦷 歯科国家試験問題 解説

## 📋 問題文
{question_text}

## 📝 選択肢
"""
    
    for i, choice in enumerate(choices, 1):
        explanation += f"{i}. {choice}\n"
    
    explanation += """
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
- 画像解析機能の追加により、視覚的な解説を強化予定

---
💡 **Note**: この解説は基本的なガイダンスです。詳細な解答については、
教科書や信頼できる参考資料で確認してください。
"""
    
    return explanation
