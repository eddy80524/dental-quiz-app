"""
Firebase Authentication関連の機能を提供するモジュール

主な変更点:
- ユーザーID管理をFirebase uidに統一
- 認証関連のロジックを単一モジュールに集約
- パフォーマンスの最適化（HTTPセッション再利用、短いタイムアウト）
"""

import streamlit as st
import requests
import datetime
import time
from typing import Optional, Dict, Any

# Cookie関連のインポート（オプショナル）
try:
    from streamlit_cookies_manager import EncryptedCookieManager
    COOKIES_AVAILABLE = True
except ImportError:
    try:
        import streamlit_cookies_manager
        EncryptedCookieManager = streamlit_cookies_manager.EncryptedCookieManager
        COOKIES_AVAILABLE = True
    except (ImportError, AttributeError):
        COOKIES_AVAILABLE = False
        print("Warning: streamlit_cookies_manager not available, login persistence disabled")


class AuthManager:
    """Firebase認証を管理するクラス"""
    
    def __init__(self):
        self.api_key = None
        self.signup_url = None
        self.signin_url = None
        self.refresh_url = None
        self.password_reset_url = None
        
        # Streamlitコンテキストが利用可能な場合のみAPIキーを設定
        try:
            self._initialize_urls()
        except Exception:
            # インポート時はStreamlitコンテキストが利用できない可能性があるため、エラーを無視
            pass
    
    def _initialize_urls(self):
        """URLを初期化"""
        try:
            # Streamlitコンテキストが利用可能かチェック
            if hasattr(st, 'secrets') and hasattr(st, 'session_state'):
                try:
                    self.api_key = st.secrets.get("firebase_api_key")
                    if self.api_key:
                        self.signup_url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={self.api_key}"
                        self.signin_url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={self.api_key}"
                        self.refresh_url = f"https://securetoken.googleapis.com/v1/token?key={self.api_key}"
                        self.password_reset_url = f"https://identitytoolkit.googleapis.com/v1/accounts:sendOobCode?key={self.api_key}"
                except Exception:
                    pass  # secrets にアクセスできない場合は無視
        except Exception as e:
            # インポート時はエラーを無視
            pass
    
    def _ensure_api_key(self):
        """APIキーが設定されているかチェック"""
        if not self.api_key:
            self._initialize_urls()
            if not self.api_key:
                try:
                    # 直接st.secretsから取得を試行
                    if hasattr(st, 'secrets') and st.secrets:
                        self.api_key = st.secrets.get("firebase_api_key")
                        if self.api_key:
                            self._initialize_urls()
                except Exception:
                    pass
                
                if not self.api_key:
                    raise Exception("Firebase API key not available")
    
    def _get_http_session(self) -> requests.Session:
        """HTTPセッションを取得"""
        try:
            if hasattr(st, 'session_state') and hasattr(st.session_state, 'auth_http_session'):
                return st.session_state.auth_http_session
            else:
                session = requests.Session()
                session.headers.update({
                    'User-Agent': 'DentalAI/1.0 (Streamlit)',
                    'Accept': 'application/json',
                    'Accept-Encoding': 'gzip, deflate',
                    'Connection': 'keep-alive'
                })
                if hasattr(st, 'session_state'):
                    st.session_state.auth_http_session = session
                return session
        except Exception:
            # Streamlitコンテキストが利用できない場合は新しいセッションを作成
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'DentalAI/1.0 (Streamlit)',
                'Accept': 'application/json',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive'
            })
            return session
    
    def signup(self, email: str, password: str) -> Dict[str, Any]:
        """Firebase新規登録"""
        self._ensure_api_key()
        payload = {"email": email, "password": password, "returnSecureToken": True}
        try:
            response = self._get_http_session().post(
                self.signup_url, json=payload, timeout=3
            )
            return response.json()
        except requests.exceptions.RequestException as e:
            return {"error": {"message": f"Network error: {str(e)}"}}
    
    def signin(self, email: str, password: str) -> Dict[str, Any]:
        """Firebase認証（uid統一版）"""
        self._ensure_api_key()
        
        # 重複ログイン防止
        try:
            if st.session_state.get("login_in_progress"):
                return {"error": {"message": "Login already in progress"}}
            
            st.session_state["login_in_progress"] = True
        except Exception:
            pass
        
        start = time.time()
        payload = {"email": email, "password": password, "returnSecureToken": True}
        
        try:
            response = self._get_http_session().post(
                self.signin_url, json=payload, timeout=3
            )
            result = response.json()
            
            if "idToken" in result:
                # セッション状態を更新（uidベース）
                try:
                    st.session_state.update({
                        "user_logged_in": True,
                        "uid": result["localId"],
                        "email": email,
                        "name": email.split("@")[0],
                        "id_token": result["idToken"],
                        "refresh_token": result["refreshToken"],
                        "token_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
                    })
                except Exception as e:
                    print(f"Warning: Could not update session state: {e}")
            
            try:
                st.session_state["login_in_progress"] = False
            except Exception:
                pass
            
            return result
            
        except requests.exceptions.RequestException as e:
            try:
                st.session_state["login_in_progress"] = False
            except Exception:
                pass
            return {"error": {"message": f"Network error: {str(e)}"}}
    
    def refresh_token(self, refresh_token: str) -> Optional[Dict[str, Any]]:
        """リフレッシュトークンを使って新しいidTokenを取得"""
        self._ensure_api_key()
        payload = {"grant_type": "refresh_token", "refresh_token": refresh_token}
        try:
            response = self._get_http_session().post(
                self.refresh_url, data=payload, timeout=3
            )
            result = response.json()
            
            if "id_token" in result:
                # トークンを更新
                try:
                    st.session_state.update({
                        "id_token": result["id_token"],
                        "refresh_token": result["refresh_token"],
                        "token_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
                    })
                except Exception:
                    pass
                return result
        except Exception as e:
            pass
        return None
    
    def reset_password(self, email: str) -> Dict[str, Any]:
        """パスワードリセットメール送信"""
        self._ensure_api_key()
        payload = {
            "requestType": "PASSWORD_RESET",
            "email": email
        }
        
        try:
            response = self._get_http_session().post(
                self.password_reset_url, json=payload, timeout=5
            )
            result = response.json()
            
            if response.status_code == 200:
                return {"success": True, "message": "パスワードリセットメールを送信しました"}
            else:
                error_message = result.get("error", {}).get("message", "Unknown error")
                return {"success": False, "message": f"エラー: {error_message}"}
                
        except requests.exceptions.RequestException as e:
            return {"success": False, "message": f"ネットワークエラー: {str(e)}"}
    
    def logout(self):
        """ログアウト"""
        try:
            # セッション状態をクリア
            keys_to_clear = [
                "user_logged_in", "uid", "email", "name", 
                "id_token", "refresh_token", "token_timestamp",
                "cards", "user_data_loaded"
            ]
            for key in keys_to_clear:
                if key in st.session_state:
                    del st.session_state[key]
        except Exception:
            pass

    def ensure_valid_session(self) -> bool:
        """有効なセッションが存在するかチェック"""
        try:
            # ログイン状態をチェック
            if not st.session_state.get("user_logged_in"):
                return False
            
            # UIDが存在するかチェック
            uid = st.session_state.get("uid")
            if not uid:
                return False
            
            # トークンが存在するかチェック
            id_token = st.session_state.get("id_token")
            if not id_token:
                return False
            
            # トークンの有効期限をチェック（1時間）
            token_timestamp = st.session_state.get("token_timestamp")
            if token_timestamp:
                try:
                    token_time = datetime.datetime.fromisoformat(token_timestamp.replace('Z', '+00:00'))
                    current_time = datetime.datetime.now(datetime.timezone.utc)
                    time_diff = (current_time - token_time).total_seconds()
                    
                    # 50分経過していたらリフレッシュを試行
                    if time_diff > 3000:  # 50分
                        refresh_token = st.session_state.get("refresh_token")
                        if refresh_token:
                            result = self.refresh_token(refresh_token)
                            if not result or "id_token" not in result:
                                return False
                        else:
                            return False
                except Exception as e:
                    print(f"Token validation error: {e}")
                    return False
            
            return True
            
        except Exception as e:
            print(f"Session validation error: {e}")
            return False


class CookieManager:
    """Cookie管理クラス"""
    
    def __init__(self):
        self.cookies = None
        self._initialize_cookies()
    
    def _initialize_cookies(self):
        """クッキーマネージャーを初期化"""
        if COOKIES_AVAILABLE:
            try:
                self.cookies = EncryptedCookieManager(
                    prefix="dental_app_",
                    password="dental_secret_2024!"  # 本番環境では環境変数から取得
                )
                if not self.cookies.ready():
                    st.stop()
            except Exception as e:
                print(f"Cookie manager initialization failed: {e}")
                self.cookies = None
    
    def save_login_cookies(self, data: Dict[str, str]):
        """ログイン情報をクッキーに保存"""
        if not self.cookies:
            return
        
        try:
            self.cookies["uid"] = data.get("uid", "")
            self.cookies["email"] = data.get("email", "")
            self.cookies["refresh_token"] = data.get("refresh_token", "")
            self.cookies.save()
        except Exception as e:
            print(f"Failed to save cookies: {e}")
    
    def try_auto_login(self) -> bool:
        """クッキーから自動ログインを試行"""
        if not self.cookies:
            return False
        
        try:
            uid = self.cookies.get("uid")
            email = self.cookies.get("email")
            refresh_token = self.cookies.get("refresh_token")
            
            if uid and email and refresh_token:
                auth_manager = AuthManager()
                result = auth_manager.refresh_token(refresh_token)
                
                if result and "id_token" in result:
                    st.session_state.update({
                        "user_logged_in": True,
                        "uid": uid,
                        "email": email,
                        "name": email.split("@")[0],
                        "id_token": result["id_token"],
                        "refresh_token": result["refresh_token"],
                        "token_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
                    })
                    return True
        except Exception as e:
            print(f"Auto-login failed: {e}")
        
        return False
    
    def clear_cookies(self):
        """クッキーをクリア"""
        if not self.cookies:
            return
        
        try:
            self.cookies["uid"] = ""
            self.cookies["email"] = ""
            self.cookies["refresh_token"] = ""
            self.cookies.save()
        except Exception as e:
            print(f"Failed to clear cookies: {e}")


def call_cloud_function(function_name: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Cloud Function呼び出し用のヘルパー関数（Firebase v2 Functions対応）"""
    try:
        firebase_project_id = st.secrets.get("firebase_project_id", "dent-ai-4d8d8")
        
        # Firebase v2 Cloud Functions用のURL
        # リージョンが指定されている場合のURL形式
        region = "asia-northeast1"
        url = f"https://{region}-{firebase_project_id}.cloudfunctions.net/{function_name}"
        
        headers = {"Content-Type": "application/json"}
        
        # 認証トークンがある場合は追加
        if "id_token" in st.session_state:
            headers["Authorization"] = f"Bearer {st.session_state['id_token']}"
        
        
        response = requests.post(url, json=data, headers=headers, timeout=15)
        
        
        # レスポンスステータスの確認
        if response.status_code != 200:
            print(f"Cloud Function error: Status {response.status_code}, Content: {response.text[:500]}")
            return None
        
        # レスポンスが空でないことを確認
        if not response.text.strip():
            print("Cloud Function error: Empty response")
            return None
            
        # JSONパースを試行
        try:
            result = response.json()
            return result
        except ValueError as json_error:
            print(f"Cloud Function JSON parse error: {json_error}, Content: {response.text[:500]}")
            return None
        
    except Exception as e:
        print(f"Cloud Function call error: {e}")
        return None