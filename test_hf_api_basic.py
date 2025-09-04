#!/usr/bin/env python3
"""
Hugging Face API基本接続テスト
"""

import requests
import json
import os

def extract_hf_token():
    """secrets.tomlからHF_API_TOKENを抽出"""
    secrets_path = os.path.join(os.path.dirname(__file__), 'my_llm_app', '.streamlit', 'secrets.toml')
    try:
        with open(secrets_path, 'r') as f:
            content = f.read()
            for line in content.split('\n'):
                line = line.strip()
                if line.startswith('HF_API_TOKEN') and '=' in line:
                    _, value = line.split('=', 1)
                    return value.strip().strip('"\'')
    except Exception as e:
        print(f"❌ APIトークン読み込みエラー: {e}")
    return None

def test_token_validity(token):
    """APIトークンの有効性をテスト"""
    print("🔐 APIトークンの有効性テスト...")
    
    # Hugging Face APIのuser情報を取得してトークンの有効性を確認
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        # Hugging Face APIのuserエンドポイントでトークンをテスト
        response = requests.get("https://huggingface.co/api/whoami", headers=headers, timeout=10)
        print(f"📥 whoami APIステータス: {response.status_code}")
        
        if response.status_code == 200:
            user_info = response.json()
            print(f"✅ APIトークンは有効です")
            print(f"👤 ユーザー: {user_info.get('name', 'N/A')}")
            print(f"📧 メール: {user_info.get('email', 'N/A')[:10]}...")
            return True
        else:
            print(f"❌ APIトークンが無効です: {response.status_code}")
            print(f"📄 エラー詳細: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ APIトークンテストエラー: {e}")
        return False

def test_simple_models(token):
    """シンプルな既知のモデルでテスト"""
    print("\n🧪 簡単なモデルでテスト...")
    
    # より確実に存在すると思われるシンプルなモデル
    simple_models = [
        "gpt2",
        "distilbert-base-uncased",
        "bert-base-uncased", 
        "t5-small",
        "facebook/bart-large-mnli"
    ]
    
    headers = {"Authorization": f"Bearer {token}"}
    
    for model in simple_models:
        print(f"\n🔍 テスト中: {model}")
        api_url = f"https://api-inference.huggingface.co/models/{model}"
        
        # シンプルなテキスト生成リクエスト
        payload = {"inputs": "Hello, world!"}
        
        try:
            response = requests.post(api_url, headers=headers, json=payload, timeout=15)
            print(f"   📥 ステータス: {response.status_code}")
            
            if response.status_code == 200:
                print(f"   ✅ 成功!")
                result = response.json()
                print(f"   📄 レスポンス形式: {type(result)}")
                if isinstance(result, list) and result:
                    print(f"   📝 結果サンプル: {str(result[0])[:100]}...")
                return model  # 最初に成功したモデルを返す
            elif response.status_code == 503:
                print(f"   ⏳ モデルがロード中です (すぐに利用可能になります)")
                return model
            else:
                print(f"   ❌ エラー: {response.text[:100]}")
                
        except Exception as e:
            print(f"   💥 例外: {e}")
    
    return None

def test_inference_api_availability():
    """Inference API全体の稼働状況をテスト"""
    print("\n🌐 Hugging Face Inference API稼働状況テスト...")
    
    try:
        # Hugging Face APIのステータスページまたはヘルスチェック
        response = requests.get("https://api-inference.huggingface.co/", timeout=10)
        print(f"📥 Inference APIステータス: {response.status_code}")
        
        if response.status_code == 200:
            print(f"✅ Inference APIは稼働中です")
            return True
        else:
            print(f"⚠️ Inference APIに問題がある可能性があります")
            print(f"📄 詳細: {response.text[:100]}")
            return False
            
    except Exception as e:
        print(f"❌ Inference API接続エラー: {e}")
        return False

def main():
    print("🔧 Hugging Face API総合診断")
    print("=" * 40)
    
    # 1. APIトークン取得
    token = extract_hf_token()
    if not token:
        print("❌ APIトークンが見つかりません")
        return
    
    print(f"📡 APIトークン取得: ✅ ({token[:4]}***{token[-4:]})")
    
    # 2. Inference API稼働状況確認
    api_available = test_inference_api_availability()
    
    # 3. APIトークン有効性確認
    token_valid = test_token_validity(token)
    
    # 4. シンプルなモデルでテスト
    working_model = None
    if token_valid and api_available:
        working_model = test_simple_models(token)
    
    # 結果サマリー
    print(f"\n📋 診断結果:")
    print(f"   🔗 Inference API稼働: {'✅' if api_available else '❌'}")
    print(f"   🔐 APIトークン有効: {'✅' if token_valid else '❌'}")
    print(f"   🧪 モデルテスト: {'✅' if working_model else '❌'}")
    
    if working_model:
        print(f"\n🎉 成功! 利用可能なモデルが見つかりました:")
        print(f"   🚀 推奨モデル: {working_model}")
        print(f"\n💡 解決方法:")
        print(f"   llm.pyファイルのモデル名を以下に変更してください:")
        print(f"   TEXT_API_URL = \"https://api-inference.huggingface.co/models/{working_model}\"")
    else:
        print(f"\n🚨 問題が検出されました:")
        if not api_available:
            print(f"   • Hugging Face Inference APIに接続できません")
        if not token_valid:
            print(f"   • APIトークンが無効です")
            print(f"   • 新しいAPIトークンを取得してください: https://huggingface.co/settings/tokens")
        if api_available and token_valid:
            print(f"   • モデルへのアクセスに問題があります")
            print(f"   • しばらく時間をおいて再試行してください")

if __name__ == "__main__":
    main()
