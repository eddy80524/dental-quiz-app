#!/usr/bin/env python3
"""
詳細なAPIトークンデバッグ
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

def detailed_token_analysis(token):
    """トークンの詳細分析"""
    print("🔍 APIトークン詳細分析:")
    print(f"   📏 長さ: {len(token)} 文字")
    print(f"   🔤 形式: {token[:4]}{'*' * (len(token) - 8)}{token[-4:]}")
    print(f"   ✅ hf_プレフィックス: {'あり' if token.startswith('hf_') else 'なし'}")
    
    # 不可視文字のチェック
    visible_chars = ''.join(c for c in token if c.isprintable())
    if len(visible_chars) != len(token):
        print(f"   ⚠️  不可視文字が含まれています")
        return False
    
    # スペースのチェック  
    if ' ' in token:
        print(f"   ⚠️  スペースが含まれています")
        return False
        
    print(f"   ✅ 文字形式: 正常")
    return True

def test_different_endpoints(token):
    """異なるエンドポイントでテスト"""
    endpoints = [
        ("whoami", "https://huggingface.co/api/whoami"),
        ("user info", "https://huggingface.co/api/user"),
        ("models", "https://api-inference.huggingface.co/models"),
    ]
    
    headers = {"Authorization": f"Bearer {token}"}
    
    for name, url in endpoints:
        print(f"\n🌐 {name} エンドポイントテスト:")
        print(f"   URL: {url}")
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            print(f"   📥 ステータス: {response.status_code}")
            
            if response.status_code == 200:
                print(f"   ✅ 成功!")
                try:
                    data = response.json()
                    if 'name' in data:
                        print(f"   👤 ユーザー名: {data['name']}")
                    if 'type' in data:
                        print(f"   🏷️  タイプ: {data['type']}")
                except:
                    print(f"   📄 レスポンス: {response.text[:100]}...")
                return True
            else:
                print(f"   ❌ エラー: {response.status_code}")
                print(f"   📄 詳細: {response.text[:100]}...")
                
        except Exception as e:
            print(f"   💥 例外: {e}")
    
    return False

def test_manual_curl_equivalent(token):
    """curlコマンド相当のテスト"""
    print(f"\n🔧 手動curlテスト相当:")
    
    # より詳細なヘッダー設定
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "Python/3.12 requests/2.31.0",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    try:
        print(f"   📤 リクエスト送信中...")
        response = requests.get(
            "https://huggingface.co/api/whoami", 
            headers=headers, 
            timeout=15
        )
        
        print(f"   📥 ステータス: {response.status_code}")
        print(f"   🔗 リクエストURL: {response.url}")
        print(f"   📋 レスポンスヘッダー:")
        for key, value in response.headers.items():
            if key.lower() in ['content-type', 'server', 'date']:
                print(f"      {key}: {value}")
        
        print(f"   📄 レスポンス本文:")
        print(f"      {response.text[:200]}...")
        
        return response.status_code == 200
        
    except Exception as e:
        print(f"   💥 例外: {e}")
        return False

def suggest_curl_command(token):
    """デバッグ用のcurlコマンドを提案"""
    print(f"\n💡 手動テスト用curlコマンド:")
    print(f"curl -H 'Authorization: Bearer {token[:10]}...' \\")
    print(f"     https://huggingface.co/api/whoami")
    print(f"")
    print(f"ターミナルで上記コマンドを実行して、結果を確認してください。")

def main():
    print("🔧 詳細APIトークンデバッグ")
    print("=" * 50)
    
    # 1. トークン取得
    token = extract_hf_token()
    if not token:
        print("❌ APIトークンが見つかりません")
        return
    
    # 2. トークン詳細分析
    token_ok = detailed_token_analysis(token)
    
    if not token_ok:
        print("\n🚨 トークンの形式に問題があります")
        return
    
    # 3. 異なるエンドポイントでテスト
    success = test_different_endpoints(token)
    
    # 4. 詳細なリクエストテスト
    if not success:
        manual_success = test_manual_curl_equivalent(token)
        
        if not manual_success:
            suggest_curl_command(token)
    
    print(f"\n📋 デバッグ結果:")
    print(f"   🔤 トークン形式: {'✅' if token_ok else '❌'}")
    print(f"   🌐 API接続: {'✅' if success else '❌'}")
    
    if not success:
        print(f"\n🔧 次のステップ:")
        print(f"   1. Hugging Face アカウントにログインして確認")
        print(f"   2. APIトークンの権限を確認（read権限が必要）")
        print(f"   3. アカウントが制限されていないか確認")
        print(f"   4. 新しいAPIトークンを作成してテスト")

if __name__ == "__main__":
    main()
