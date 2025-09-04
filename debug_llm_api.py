#!/usr/bin/env python3
"""
LLM API接続デバッグスクリプト
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'my_llm_app'))

import requests
import json

# secrets.tomlファイルを直接読み込んでテスト
def read_secrets_toml():
    """secrets.tomlファイルを直接読み込む"""
    secrets_path = os.path.join(os.path.dirname(__file__), 'my_llm_app', '.streamlit', 'secrets.toml')
    try:
        with open(secrets_path, 'r') as f:
            content = f.read()
            print(f"✅ secrets.tomlファイルが見つかりました: {secrets_path}")
            print(f"📄 ファイル内容（部分）:")
            for line in content.split('\n')[:5]:  # 最初の5行だけ表示
                if 'HF_API_TOKEN' in line:
                    # APIトークンの最初と最後の数文字だけ表示（セキュリティのため）
                    if '=' in line:
                        key, value = line.split('=', 1)
                        value = value.strip().strip('"\'')
                        if len(value) > 10:
                            masked_value = value[:4] + '*' * (len(value) - 8) + value[-4:]
                            print(f"   {key.strip()} = {masked_value}")
                        else:
                            print(f"   {key.strip()} = {'*' * len(value)}")
                else:
                    print(f"   {line}")
            return content
    except FileNotFoundError:
        print(f"❌ secrets.tomlファイルが見つかりません: {secrets_path}")
        return None
    except Exception as e:
        print(f"❌ secrets.tomlファイルの読み込みエラー: {e}")
        return None

def extract_hf_token(content):
    """secrets.tomlからHF_API_TOKENを抽出"""
    for line in content.split('\n'):
        line = line.strip()
        if line.startswith('HF_API_TOKEN') and '=' in line:
            _, value = line.split('=', 1)
            return value.strip().strip('"\'')
    return None

def test_hf_api(token):
    """Hugging Face APIへの接続テスト"""
    if not token:
        print("❌ APIトークンが見つかりません")
        return False
    
    print(f"\n🔍 Hugging Face API接続テスト開始...")
    print(f"📡 APIトークン（部分表示）: {token[:4]}***{token[-4:] if len(token) > 8 else '***'}")
    
    # テスト用のシンプルなAPI呼び出し
    api_url = "https://api-inference.huggingface.co/models/Qwen/Qwen2.5-7B-Instruct"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "inputs": "Hello, how are you?",
        "parameters": {
            "max_new_tokens": 50,
            "return_full_text": False,
        }
    }
    
    try:
        print(f"📤 API呼び出し中: {api_url}")
        response = requests.post(api_url, headers=headers, json=payload, timeout=30)
        print(f"📥 HTTPステータスコード: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ API接続成功!")
            print(f"📄 レスポンス形式: {type(result)}")
            if isinstance(result, list) and result:
                print(f"📝 生成テキスト（部分）: {result[0].get('generated_text', 'N/A')[:100]}...")
            elif isinstance(result, dict):
                print(f"📝 生成テキスト（部分）: {result.get('generated_text', 'N/A')[:100]}...")
            return True
        else:
            print(f"❌ APIエラー: {response.status_code}")
            print(f"📄 エラー内容: {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        print("❌ タイムアウトエラー: APIサーバーの応答が遅すぎます")
        return False
    except requests.exceptions.ConnectionError:
        print("❌ 接続エラー: ネットワークまたはAPIサーバーに問題があります")
        return False
    except requests.exceptions.RequestException as e:
        print(f"❌ リクエストエラー: {e}")
        return False
    except Exception as e:
        print(f"❌ 予期しないエラー: {e}")
        return False

def main():
    print("🔧 LLM API接続診断ツール")
    print("=" * 40)
    
    # 1. secrets.tomlファイルの確認
    content = read_secrets_toml()
    if not content:
        print("\n💡 解決方法:")
        print("   1. my_llm_app/.streamlit/secrets.toml ファイルを確認してください")
        print("   2. HF_API_TOKEN = \"your_token_here\" の行があることを確認してください")
        return
    
    # 2. APIトークンの抽出
    token = extract_hf_token(content)
    if not token:
        print("❌ HF_API_TOKENがsecrets.tomlに見つかりません")
        print("\n💡 解決方法:")
        print("   secrets.tomlに以下の行を追加してください:")
        print("   HF_API_TOKEN = \"your_hugging_face_token_here\"")
        return
    
    # 3. API接続テスト
    success = test_hf_api(token)
    
    print(f"\n📋 診断結果:")
    print(f"   ファイル読み込み: {'✅' if content else '❌'}")
    print(f"   トークン抽出: {'✅' if token else '❌'}")
    print(f"   API接続: {'✅' if success else '❌'}")
    
    if success:
        print(f"\n🎉 すべてのテストが成功しました！")
        print(f"   LLM機能は正常に動作するはずです。")
    else:
        print(f"\n🚨 問題が検出されました。")
        print(f"   上記のエラーメッセージを確認し、対処してください。")

if __name__ == "__main__":
    main()
