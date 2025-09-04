#!/usr/bin/env python3
"""
Hugging Face利用可能モデル確認スクリプト
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

def test_model_availability(token, model_name):
    """指定されたモデルが利用可能かテスト"""
    api_url = f"https://api-inference.huggingface.co/models/{model_name}"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "inputs": "Test",
        "parameters": {
            "max_new_tokens": 10,
            "return_full_text": False,
        }
    }
    
    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=15)
        return response.status_code, response.text[:200]
    except Exception as e:
        return None, str(e)

def main():
    print("🔍 Hugging Face モデル可用性チェック")
    print("=" * 50)
    
    token = extract_hf_token()
    if not token:
        print("❌ APIトークンが見つかりません")
        return
    
    # テストするモデルのリスト
    models_to_test = [
        "Qwen/Qwen2.5-7B-Instruct",
        "Qwen/Qwen2.5-VL-7B-Instruct", 
        "Qwen/Qwen2-VL-7B-Instruct",
        "Qwen/Qwen2-7B-Instruct",
        "microsoft/DialoGPT-medium",
        "microsoft/DialoGPT-large",
        "google/flan-t5-large",
        "facebook/blenderbot-400M-distill",
        "mistralai/Mixtral-8x7B-Instruct-v0.1",
        "mistralai/Mistral-7B-Instruct-v0.1",
        "meta-llama/Llama-2-7b-chat-hf",
    ]
    
    print(f"📡 APIトークン: {token[:4]}***{token[-4:]}")
    print(f"🧪 {len(models_to_test)}個のモデルをテスト中...\n")
    
    available_models = []
    unavailable_models = []
    
    for model in models_to_test:
        print(f"🔍 テスト中: {model}")
        status_code, response = test_model_availability(token, model)
        
        if status_code == 200:
            print(f"   ✅ 利用可能 (200)")
            available_models.append(model)
        elif status_code == 404:
            print(f"   ❌ モデルが見つかりません (404)")
            unavailable_models.append((model, "404 - Not Found"))
        elif status_code == 503:
            print(f"   ⏳ モデルがロード中です (503)")
            available_models.append(model)  # 503はモデルがロード中なので実際は利用可能
        elif status_code == 401:
            print(f"   🔐 認証エラー (401) - APIトークンを確認してください")
            unavailable_models.append((model, "401 - Unauthorized"))
        elif status_code:
            print(f"   ⚠️  その他のエラー ({status_code}): {response[:100]}")
            unavailable_models.append((model, f"{status_code} - {response[:50]}"))
        else:
            print(f"   💥 接続エラー: {response[:100]}")
            unavailable_models.append((model, f"Connection Error - {response[:50]}"))
        
        print()
    
    print("=" * 50)
    print("📊 結果サマリー:")
    print(f"✅ 利用可能なモデル数: {len(available_models)}")
    print(f"❌ 利用不可能なモデル数: {len(unavailable_models)}")
    
    if available_models:
        print(f"\n🎉 利用可能なモデル:")
        for model in available_models:
            print(f"   • {model}")
    
    if unavailable_models:
        print(f"\n❌ 利用不可能なモデル:")
        for model, reason in unavailable_models:
            print(f"   • {model} ({reason})")
    
    # 推奨事項
    print(f"\n💡 推奨事項:")
    if available_models:
        print(f"   最初に利用可能だったモデルを使用することを推奨します:")
        print(f"   🚀 {available_models[0]}")
    else:
        print(f"   利用可能なモデルが見つかりませんでした。")
        print(f"   以下を確認してください:")
        print(f"   1. APIトークンが有効か")
        print(f"   2. インターネット接続")
        print(f"   3. Hugging Faceのサービス状況")

if __name__ == "__main__":
    main()
