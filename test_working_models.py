#!/usr/bin/env python3
"""
実際に動作するシンプルなモデルでテスト
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

def test_simple_generation(token):
    """シンプルなテキスト生成モデルでテスト"""
    
    # 確実に存在する小さなモデルでテスト
    simple_models = [
        "gpt2",
        "distilgpt2", 
        "microsoft/DialoGPT-small",
        "EleutherAI/gpt-neo-125M"
    ]
    
    headers = {"Authorization": f"Bearer {token}"}
    
    for model in simple_models:
        print(f"\n🔍 テスト中: {model}")
        api_url = f"https://api-inference.huggingface.co/models/{model}"
        
        payload = {
            "inputs": "Explain dental care:",
            "parameters": {
                "max_length": 50,
                "temperature": 0.7,
                "return_full_text": False
            }
        }
        
        try:
            response = requests.post(api_url, headers=headers, json=payload, timeout=30)
            print(f"   📥 ステータス: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                print(f"   ✅ 成功!")
                print(f"   📄 レスポンス: {result}")
                return model, result
            elif response.status_code == 503:
                print(f"   ⏳ モデルロード中 - しばらく待ってから再試行")
                # 503はモデルがロード中なので、しばらく待って再試行
                import time
                time.sleep(10)
                response2 = requests.post(api_url, headers=headers, json=payload, timeout=30)
                if response2.status_code == 200:
                    result = response2.json()
                    print(f"   ✅ 再試行で成功!")
                    print(f"   📄 レスポンス: {result}")
                    return model, result
            else:
                print(f"   ❌ エラー: {response.status_code}")
                print(f"   📄 詳細: {response.text[:200]}")
                
        except Exception as e:
            print(f"   💥 例外: {e}")
    
    return None, None

def test_without_auth():
    """認証なしでパブリックAPIを試す"""
    print(f"\n🌐 認証なしでのパブリックAPIテスト:")
    
    # 認証不要で使えるモデル
    public_models = [
        "gpt2",
        "distilgpt2"
    ]
    
    for model in public_models:
        print(f"\n🔍 認証なしテスト: {model}")
        api_url = f"https://api-inference.huggingface.co/models/{model}"
        
        payload = {
            "inputs": "Hello world",
            "parameters": {
                "max_length": 30
            }
        }
        
        try:
            # 認証ヘッダーなしでリクエスト
            response = requests.post(api_url, json=payload, timeout=30)
            print(f"   📥 ステータス: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                print(f"   ✅ 認証なしで成功!")
                print(f"   📄 レスポンス: {result}")
                return True
            else:
                print(f"   📄 詳細: {response.text[:100]}")
                
        except Exception as e:
            print(f"   💥 例外: {e}")
    
    return False

def main():
    print("🧪 シンプルモデルテスト")
    print("=" * 40)
    
    # 1. APIトークン取得
    token = extract_hf_token()
    if not token:
        print("❌ APIトークンが見つかりません")
        return
    
    print(f"📡 APIトークン: {token[:4]}***{token[-4:]}")
    
    # 2. 認証なしでのテスト（比較用）
    public_works = test_without_auth()
    
    # 3. 認証ありでのテスト
    working_model, result = test_simple_generation(token)
    
    print(f"\n📋 テスト結果:")
    print(f"   🌐 パブリック API: {'✅' if public_works else '❌'}")
    print(f"   🔐 認証 API: {'✅' if working_model else '❌'}")
    
    if working_model:
        print(f"\n🎉 成功! 動作するモデルが見つかりました:")
        print(f"   🚀 モデル: {working_model}")
        print(f"   💡 このモデルを使ってLLM機能を実装できます")
    elif public_works:
        print(f"\n⚠️  パブリックAPIは動作しますが、認証APIが失敗")
        print(f"   🔑 APIトークンに問題がある可能性があります")
    else:
        print(f"\n🚨 すべてのテストが失敗しました")
        print(f"   🌐 ネットワークまたはHugging Face側の問題の可能性があります")

if __name__ == "__main__":
    main()
