import streamlit as st
import json
import os
import random
import datetime
import re
from collections import Counter
import firebase_admin
from firebase_admin import credentials, firestore, storage, performance
import requests
import tempfile
import collections.abc
import pandas as pd
import glob
from streamlit_cookies_manager import EncryptedCookieManager

# plotlyインポート（未インストール時の案内付き）
try:
    import plotly.express as px
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

st.set_page_config(layout="wide")

# ライトモード固定設定
st.markdown("""
<style>
/* ライトモードのみで固定 */
.stApp {
    background-color: #ffffff;
    color: #000000;
}

.stSidebar {
    background-color: #f0f2f6;
}

/* サイドバーのボタン色を統一（メイン画面と同じ青色に） */
.stSidebar .stButton > button[kind="primary"] {
    background-color: #0066cc !important;
    color: white !important;
    border: none !important;
}

.stSidebar .stButton > button[kind="primary"]:hover {
    background-color: #0052a3 !important;
    color: white !important;
}

.stSidebar .stButton > button[kind="primary"]:focus {
    background-color: #0066cc !important;
    color: white !important;
    box-shadow: 0 0 0 0.2rem rgba(0, 102, 204, 0.25) !important;
}
</style>""", unsafe_allow_html=True)

# Secrets存在チェック（早期エラー検出）
if "firebase_credentials" not in st.secrets or "firebase_api_key" not in st.secrets:
    st.error("Firebase の secrets が設定されていません。")
    st.stop()

# --- Firebase初期化 ---
#【重要】Firebaseセキュリティルールを設定してください。
# Firestore: ユーザーが自分のデータのみにアクセスできるように制限します。
#   例: match /user_progress/{userId} { allow read, write: if request.auth.token.email == userId; }
# Storage: 認証済みユーザーのみがアップロードできるようにし、必要に応じて読み取りを制限します。

def to_dict(obj):
    if isinstance(obj, collections.abc.Mapping):
        return {k: to_dict(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [to_dict(i) for i in obj]
    else:
        return obj

# 追加: バケット名を正規化するユーティリティ
def _resolve_storage_bucket(firebase_creds):
    # 優先: secrets > creds の順
    raw = st.secrets.get("firebase_storage_bucket") \
          or firebase_creds.get("storage_bucket") \
          or firebase_creds.get("storageBucket")

    # project_id からのフォールバック
    if not raw:
        pid = firebase_creds.get("project_id") or firebase_creds.get("projectId") or "dent-ai-4d8d8"
        raw = f"{pid}.firebasestorage.app"  # 正しいFirebasestorageドメインを使用

    b = str(raw).strip()

    # 余計なプロトコル/gs:// を除去して純粋なバケット名に
    b = b.replace("gs://", "").split("/")[0]
    return b

@st.cache_resource
def initialize_firebase():
    firebase_creds = to_dict(st.secrets["firebase_credentials"])
    # 一時ファイルは後で必ず削除
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            json.dump(firebase_creds, f)
            temp_path = f.name
        creds = credentials.Certificate(temp_path)

        storage_bucket = _resolve_storage_bucket(firebase_creds)

        try:
            app = firebase_admin.get_app()
        except ValueError:
            app = firebase_admin.initialize_app(
                creds,
                {"storageBucket": storage_bucket}
            )
        print(f"Firebase initialized with bucket: {storage_bucket}")

        db = firestore.client(app=app)
        bucket = storage.bucket(app=app)  # ここで既定バケットが正しく紐づく
        return db, bucket
    finally:
        # サービスアカウントの一時ファイルを確実に削除（セキュリティ&掃除）
        if temp_path:
            try:
                os.unlink(temp_path)
            except Exception:
                pass

# Firebase初期化（遅延読み込み・キャッシュ最適化）
@st.cache_resource
def get_firebase_clients():
    """Firebase DB/Bucketを遅延初期化でキャッシュ"""
    return initialize_firebase()

def get_db():
    """FirestoreDBを安全に取得"""
    try:
        db, _ = get_firebase_clients()
        return db
    except Exception as e:
        print(f"[ERROR] Firebase DB取得エラー: {e}")
        return None

def get_bucket():
    """Firebase Storageバケットを安全に取得"""
    try:
        _, bucket = get_firebase_clients()
        return bucket
    except Exception as e:
        print(f"[ERROR] Firebase Storage取得エラー: {e}")
        return None

# --- Cookies（自動ログイン用・セッション状態キャッシュ） ---
def get_cookie_manager():
    """Cookie Managerをセッション状態でキャッシュ（ウィジェット警告回避）"""
    # セッション状態にキャッシュ（ウィジェット使用のため@st.cache_resourceは使用不可）
    if "cookie_manager" not in st.session_state:
        try:
            cookie_password = st.secrets.get("cookie_password", "default_insecure_password_change_in_production")
            print(f"[DEBUG] Cookie manager初期化開始")
            cookie_manager = EncryptedCookieManager(
                prefix="dentai_",
                password=cookie_password
            )
            print(f"[DEBUG] Cookie manager作成完了")
            
            # 初期化直後は準備完了まで待機
            if hasattr(cookie_manager, '_ready'):
                if not cookie_manager._ready:
                    print(f"[DEBUG] Cookie manager created but not ready, waiting...")
                    st.session_state.cookie_manager = cookie_manager
                    return cookie_manager
            
            # 簡単なテストでアクセス可能性を確認
            try:
                test_value = cookie_manager.get("init_test", "default")
                print(f"[DEBUG] Cookie manager test successful")
                st.session_state.cookie_manager = cookie_manager
                return cookie_manager
            except Exception as test_e:
                print(f"[DEBUG] Cookie manager test failed: {test_e}")
                st.session_state.cookie_manager = cookie_manager  # 準備中でも保存
                return cookie_manager
                
        except Exception as e:
            print(f"[DEBUG] Cookie manager作成失敗: {e}")
            st.session_state.cookie_manager = None
    
    return st.session_state.cookie_manager

def safe_save_cookies(cookies, data_dict):
    """クッキーを安全に保存（エラーハンドリング付き）"""
    if not cookies:
        print("[DEBUG] Cookie manager is None, skipping save")
        return False
    
    try:
        # Cookieが準備完了かチェック
        if hasattr(cookies, '_ready') and not cookies._ready:
            print("[DEBUG] Cookies not ready yet; skip saving this run")
            return False
        
        # データを設定
        for key, value in data_dict.items():
            cookies[key] = value
        
        # 保存実行
        cookies.save()
        print(f"[DEBUG] Cookies saved successfully: {list(data_dict.keys())}")
        return True
        
    except Exception as e:
        print(f"[DEBUG] Cookie save error: {str(e)}")
        return False

def get_cookies():
    """Cookieを安全に取得（CookiesNotReadyエラー完全対応）"""
    # 初期化フラグで重複実行を防止
    if st.session_state.get("cookie_init_attempted"):
        cookies = st.session_state.get("cookie_manager")
        if cookies is not None:
            try:
                # Cookieが準備完了かチェック
                if hasattr(cookies, '_ready') and not cookies._ready:
                    print("[DEBUG] Cookies not ready yet")
                    return None
                # 簡単なアクセステストを行う
                _ = cookies.get("test", None)
                print("[DEBUG] Cookie manager is ready and accessible")
                return cookies
            except Exception as e:
                print(f"[DEBUG] Cookie access error during get: {str(e)}")
                return None
        else:
            print("[DEBUG] Cookie manager is None in session state")
            return None
    
    # 初回のみ初期化を試行
    st.session_state.cookie_init_attempted = True
    try:
        cookies = get_cookie_manager()
        if cookies is not None:
            # 準備完了まで待機（時間をおいて再試行）
            try:
                if hasattr(cookies, '_ready'):
                    if not cookies._ready:
                        print("[DEBUG] Cookie manager created but not ready, will retry next run")
                        return None
                # 簡単なアクセステストを行う
                test_value = cookies.get("test", None)
                st.session_state.cookie_manager = cookies
                print("[DEBUG] Cookie manager ready and functional")
                return cookies
            except Exception as e:
                print(f"[DEBUG] Cookie readiness test failed: {str(e)}")
                print("[DEBUG] Will retry cookie initialization on next app reload")
                return None
        else:
            print("[DEBUG] Cookie manager is None")
            return None
    except Exception as e:
        print(f"[DEBUG] Cookie initialization error: {str(e)}")
        return None

FIREBASE_API_KEY = st.secrets["firebase_api_key"]
FIREBASE_AUTH_SIGNUP_URL = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
FIREBASE_AUTH_SIGNIN_URL = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
FIREBASE_REFRESH_TOKEN_URL = f"https://securetoken.googleapis.com/v1/token?key={FIREBASE_API_KEY}"

# HTTPセッション再利用でパフォーマンス向上
@st.cache_resource
def get_http_session():
    """HTTPセッションを再利用してパフォーマンスを向上"""
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'DentalAI/1.0 (Streamlit)',
        'Accept': 'application/json',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive'
    })
    return session

def firebase_signup(email, password):
    """Firebase新規登録（最適化版）"""
    session = get_http_session()
    payload = {"email": email, "password": password, "returnSecureToken": True}
    try:
        r = session.post(FIREBASE_AUTH_SIGNUP_URL, json=payload, timeout=3)
        return r.json()
    except requests.exceptions.RequestException as e:
        return {"error": {"message": f"Network error: {str(e)}"}}

@performance.trace
def firebase_signin(email, password):
    """Firebase認証（超高速版）"""
    import time
    start = time.time()
    
    # 重複ログイン防止：既にログイン処理中の場合はスキップ
    if st.session_state.get("login_in_progress"):
        print(f"[DEBUG] firebase_signin - ログイン処理中のためスキップ")
        return {"error": {"message": "Login already in progress"}}
    
    st.session_state["login_in_progress"] = True
    
    try:
        payload = {"email": email, "password": password, "returnSecureToken": True}
        session = get_http_session()
        
        api_start = time.time()
        # 超短タイムアウトで高速化（通常は1-2秒で完了するはず）
        r = session.post(FIREBASE_AUTH_SIGNIN_URL, json=payload, timeout=3)
        api_time = time.time() - api_start
        
        parse_start = time.time()
        result = r.json()
        parse_time = time.time() - parse_start
        
        total_time = time.time() - start
        print(f"[DEBUG] firebase_signin - API通信: {api_time:.3f}s, JSON解析: {parse_time:.3f}s, 合計: {total_time:.3f}s")
        print(f"[DEBUG] firebase_signin - HTTPステータス: {r.status_code}")
        
        if r.status_code != 200:
            print(f"[DEBUG] firebase_signin - HTTPエラー: {r.status_code}, レスポンス: {result}")
        
        return result
    except requests.exceptions.Timeout:
        total_time = time.time() - start
        print(f"[DEBUG] firebase_signin - タイムアウト: {total_time:.3f}s")
        return {"error": {"message": "Authentication timeout. Please check your network connection."}}
    except requests.exceptions.RequestException as e:
        total_time = time.time() - start
        print(f"[DEBUG] firebase_signin - ネットワークエラー: {e}, 時間: {total_time:.3f}s")
        return {"error": {"message": f"Network error: {str(e)}"}}
    except Exception as e:
        total_time = time.time() - start
        print(f"[DEBUG] firebase_signin - 例外発生: {e}, 時間: {total_time:.3f}s")
        return {"error": {"message": str(e)}}
    finally:
        # ログイン処理完了フラグをクリア
        st.session_state["login_in_progress"] = False

def firebase_refresh_token(refresh_token):
    """リフレッシュトークンを使って新しいidTokenを取得（最適化版）"""
    payload = {"grant_type": "refresh_token", "refresh_token": refresh_token}
    session = get_http_session()
    try:
        # 修正：JSONではなくx-www-form-urlencoded + 短いタイムアウト
        r = session.post(FIREBASE_REFRESH_TOKEN_URL, data=payload, timeout=3)
        result = r.json()
        if "id_token" in result:
            return {
                "idToken": result["id_token"],
                "refreshToken": result["refresh_token"],
                "expiresIn": int(result.get("expires_in", 3600))
            }
    except requests.exceptions.RequestException as e:
        print(f"Token refresh error: {e}")
    except Exception as e:
        print(f"Token refresh error: {e}")
    return None

def firebase_reset_password(email):
    """Firebase パスワードリセットメール送信"""
    api_key = st.secrets["firebase_api_key"]
    password_reset_url = f"https://identitytoolkit.googleapis.com/v1/accounts:sendOobCode?key={api_key}"
    
    payload = {
        "requestType": "PASSWORD_RESET",
        "email": email
    }
    
    session = get_http_session()
    try:
        r = session.post(password_reset_url, json=payload, timeout=5)
        result = r.json()
        
        if r.status_code == 200:
            print(f"[DEBUG] パスワードリセットメール送信成功: {email}")
            return {"success": True, "message": "パスワードリセットメールを送信しました"}
        else:
            print(f"[DEBUG] パスワードリセットメール送信失敗: {result}")
            error_message = result.get("error", {}).get("message", "Unknown error")
            
            # エラーメッセージを日本語化
            if "EMAIL_NOT_FOUND" in error_message:
                return {"success": False, "message": "このメールアドレスは登録されていません"}
            elif "INVALID_EMAIL" in error_message:
                return {"success": False, "message": "メールアドレスの形式が正しくありません"}
            else:
                return {"success": False, "message": f"エラー: {error_message}"}
                
    except requests.exceptions.RequestException as e:
        print(f"[DEBUG] パスワードリセット通信エラー: {e}")
        return {"success": False, "message": "ネットワークエラーが発生しました"}
    except Exception as e:
        print(f"[DEBUG] パスワードリセット例外: {e}")
        return {"success": False, "message": "予期しないエラーが発生しました"}

def is_token_expired(token_timestamp, expires_in=3600):
    """トークンが期限切れかどうかをチェック（デフォルト1時間だが、50分でリフレッシュで余裕を持つ）"""
    if not token_timestamp:
        return True
    now = datetime.datetime.now(datetime.timezone.utc)
    token_time = datetime.datetime.fromisoformat(token_timestamp)
    # 50分（3000秒）で期限切れとして扱い、余裕を持ってリフレッシュ（従来30分→50分に延長）
    return (now - token_time).total_seconds() > 3000

def try_auto_login_from_cookie():
    """クッキーからの自動ログイン（超高速版）"""
    import time
    start = time.time()
    
    # すでにログイン済みの場合は早期リターン
    if st.session_state.get("user_logged_in"):
        print(f"[DEBUG] try_auto_login_from_cookie - 既にログイン済み: {time.time() - start:.3f}s")
        return False
    
    # Cookie取得（安全に）
    cookies = get_cookies()
    
    # Cookie取得に失敗した場合は早期リターン
    if cookies is None:
        print(f"[DEBUG] try_auto_login_from_cookie - Cookie取得失敗: {time.time() - start:.3f}s")
        return False
    
    # Cookie取得（高速化・安全性強化）
    try:
        rt = None
        email = None
        uid = None
        
        # CookiesNotReadyエラー対応でtry-catchでアクセス
        try:
            rt = cookies.get("refresh_token")
            email = cookies.get("email") or ""
            uid = cookies.get("uid") or ""
        except Exception as e:
            print(f"[DEBUG] Cookie access error during auto-login: {e}")
            print(f"[DEBUG] try_auto_login_from_cookie - Cookie準備未完了: {time.time() - start:.3f}s")
            return False
            
        if not rt:
            print(f"[DEBUG] try_auto_login_from_cookie - refresh_tokenなし")
            return False
        
        # トークンリフレッシュ（タイムアウト短縮）
        result = firebase_refresh_token(rt)
        if not result:
            print(f"[DEBUG] try_auto_login_from_cookie - リフレッシュ失敗")
            # 失敗したCookieは削除
            safe_save_cookies(cookies, {"refresh_token": ""})
            return False
        
        # 高速セッション復元（emailベース管理）
        # email, uidは上で既に取得済み
        if not uid:
            uid = result.get("user_id")
        
        if not email:
            print(f"[DEBUG] try_auto_login_from_cookie - emailなし")
            return False
        
        st.session_state.update({
            "name": email.split("@")[0],
            "username": email,  # emailをプライマリIDとして使用
            "email": email,
            "uid": uid,  # FirebaseのUIDは保持するが、プライマリIDはemail
            "id_token": result["idToken"],
            "refresh_token": result["refreshToken"],
            "token_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "user_logged_in": email  # emailをログイン状態の識別子として使用
        })
        
        total_time = time.time() - start
        print(f"[DEBUG] try_auto_login_from_cookie - 成功: {total_time:.3f}s")
        return True
        
    except Exception as e:
        total_time = time.time() - start
        print(f"[DEBUG] try_auto_login_from_cookie - エラー: {e}, 時間: {total_time:.3f}s")
        return False

def ensure_valid_session():
    """セッションが有効かチェックし、必要に応じてトークンをリフレッシュ（強化版）"""
    if not st.session_state.get("user_logged_in"):
        return False
    
    token_timestamp = st.session_state.get("token_timestamp")
    refresh_token = st.session_state.get("refresh_token")
    
    # トークンが期限切れの場合はリフレッシュを試行
    if is_token_expired(token_timestamp) and refresh_token:
        print(f"[DEBUG] トークン期限切れ検出 - 自動リフレッシュ実行中")
        refresh_result = firebase_refresh_token(refresh_token)
        if refresh_result:
            # トークンの更新
            st.session_state["id_token"] = refresh_result["idToken"]
            st.session_state["refresh_token"] = refresh_result["refreshToken"]
            st.session_state["token_timestamp"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            
            # Cookieも更新（Remember meの場合）
            cookies = get_cookies()
            if cookies is not None:
                cookie_data = {
                    "refresh_token": refresh_result["refreshToken"],
                    "uid": st.session_state.get("uid"),
                    "email": st.session_state.get("email")
                }
                safe_save_cookies(cookies, cookie_data)
            
            print(f"[DEBUG] セッション自動リフレッシュ成功")
            return True
        else:
            # リフレッシュに失敗した場合はログアウト
            print(f"[DEBUG] セッションリフレッシュ失敗 - ログアウト実行")
            # セッション状態をクリア
            for key in ["user_logged_in", "authenticated", "id_token", "refresh_token", "token_timestamp", "uid", "email"]:
                if key in st.session_state:
                    del st.session_state[key]
            return False
    
    return True

@st.cache_data(ttl=3600)  # 1時間キャッシュ
def load_master_data(version="v2025-08-14-gakushi-1-2-fixed"):  # キャッシュ更新用バージョン
    import time
    start = time.time()
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    master_dir = os.path.join(script_dir, 'data')
    
    # 読み込むファイルを直接指定する
    files_to_load = [
        'master_questions_final.json', 
        'gakushi-2022-1-1.json', 
        'gakushi-2022-1-2.json', 
        'gakushi-2022-1-3.json', 
        'gakushi-2022-1再.json',  
        'gakushi-2022-2.json', 
        'gakushi-2023-1-1.json',
        'gakushi-2023-1-2.json', 
        'gakushi-2023-2.json',  
        'gakushi-2024-1-1.json', 
        'gakushi-2024-2.json', 
        'gakushi-2025-1-1.json'
    ]
    target_files = [os.path.join(master_dir, f) for f in files_to_load]

    all_cases = {}
    all_questions = []
    seen_numbers = set()
    missing_files = []
    
    file_load_times = []

    for file_path in target_files:
        file_start = time.time()
        # ファイルが存在するか念のため確認
        if not os.path.exists(file_path):
            missing_files.append(file_path)
            continue
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            file_load_time = time.time() - file_start
            file_load_times.append((os.path.basename(file_path), file_load_time))

            if isinstance(data, dict):
                # 'cases'キーがない場合もエラーにならないように.get()を使用
                cases = data.get('cases', {})
                if isinstance(cases, dict):
                    all_cases.update(cases)
                
                questions = data.get('questions', [])
                if isinstance(questions, list):
                    for q in questions:
                        num = q.get('number')
                        if num and num not in seen_numbers:
                            all_questions.append(q)
                            seen_numbers.add(num)
            
            elif isinstance(data, list):
                for q in data:
                    num = q.get('number')
                    if num and num not in seen_numbers:
                        all_questions.append(q)
                        seen_numbers.add(num)

        except Exception as e:
            # ログだけ残してUIには表示しない
            print(f"{file_path} の読み込みでエラー: {e}")
    
    total_time = time.time() - start
    print(f"[DEBUG] load_master_data - 総時間: {total_time:.3f}s, 問題数: {len(all_questions)}")
    for filename, file_time in file_load_times:
        print(f"[DEBUG] load_master_data - {filename}: {file_time:.3f}s")
    
    # ファイルが足りない場合は警告をUIに出さない
    return all_cases, all_questions

def is_hisshu(q_num_str):
    """問題番号文字列を受け取り、必修問題かどうかを判定する"""
    match = re.match(r'(\d+)([A-D])(\d+)', q_num_str)
    if not match:
        return False
    kai, ryoiki, num = int(match.group(1)), match.group(2), int(match.group(3))
    if 101 <= kai <= 102:
        return ryoiki in ['A', 'B'] and 1 <= num <= 25
    elif 103 <= kai <= 110:
        return ryoiki in ['A', 'C'] and 1 <= num <= 35
    elif 111 <= kai <= 118:
        return ryoiki in ['A', 'B', 'C', 'D'] and 1 <= num <= 20
    return False

def is_gakushi_hisshu(q_num_str):
    """学士試験の問題番号文字列を受け取り、必修問題かどうかを判定する"""
    # 学士試験の必修問題は1-20番（全領域A-D共通）
    match = re.match(r'^G\d{2}-[\d\-再]+-[A-D]-(\d+)$', q_num_str)
    if match:
        num = int(match.group(1))
        return 1 <= num <= 20
    return False

@st.cache_data(ttl=3600)
def get_derived_data(all_questions):
    """派生データを別途キャッシュして計算コストを分散"""
    import time
    start = time.time()
    
    questions_dict = {q['number']: q for q in all_questions}
    subjects = sorted(list(set(q['subject'] for q in all_questions if q.get('subject') and q.get('subject') != '（未分類）')))
    exam_numbers = sorted(list(set(re.match(r'(\d+)', q['number']).group(1) for q in all_questions if re.match(r'(\d+)', q['number']))), key=int, reverse=True)
    exam_sessions = sorted(list(set(re.match(r'(\d+[A-D])', q['number']).group(1) for q in all_questions if re.match(r'(\d+[A-D])', q['number']))))
    hisshu_numbers = {q['number'] for q in all_questions if is_hisshu(q['number'])}
    gakushi_hisshu_numbers = {q['number'] for q in all_questions if is_gakushi_hisshu(q['number'])}
    
    derived_time = time.time() - start
    print(f"[DEBUG] get_derived_data - 派生データ計算: {derived_time:.3f}s")
    
    return questions_dict, subjects, exam_numbers, exam_sessions, hisshu_numbers, gakushi_hisshu_numbers

# --- 学士インデックスとフィルタ ---
import re
from collections import defaultdict

def build_gakushi_indices(all_questions):
    years = set()
    areas_by_year = defaultdict(set)
    subjects = set()
    for q in all_questions:
        qn = q.get("number", "")
        if not qn.startswith("G"):
            continue
        # 2つの形式に対応: G23-2-A-1 と G25-1-1-A-1
        m = re.match(r'^G(\d{2})-([^-]+(?:-[^-]+)*)-([A-D])-\d+$', qn)
        if m:
            y2 = int(m.group(1))
            year = 2000 + y2 if y2 <= 30 else 1900 + y2
            area = m.group(3)
            years.add(year)
            areas_by_year[year].add(area)
        s = (q.get("subject") or "").strip()
        if qn.startswith("G") and s:
            subjects.add(s)
    years_sorted = sorted(years, reverse=True)
    areas_map = {y: sorted(list(areas_by_year[y])) for y in years_sorted}
    gakushi_subjects = sorted(list(subjects))
    return years_sorted, areas_map, gakushi_subjects

def build_gakushi_indices_with_sessions(all_questions):
    """学士試験の年度、回数、領域の情報を整理する"""
    years = set()
    sessions_by_year = defaultdict(set)
    areas_by_year_session = defaultdict(lambda: defaultdict(set))
    subjects = set()
    
    for q in all_questions:
        qn = q.get("number", "")
        if not qn.startswith("G"):
            continue
            
        # G23-2-A-1, G25-1-1-A-1, G22-1再-A-1 などの形式に対応
        m = re.match(r'^G(\d{2})-([^-]+(?:-[^-]+)*)-([A-D])-\d+$', qn)
        if m:
            y2 = int(m.group(1))
            year = 2000 + y2 if y2 <= 30 else 1900 + y2
            session = m.group(2)  # 1-1, 1-2, 1-3, 1再, 2, 2再 など
            area = m.group(3)
            
            years.add(year)
            sessions_by_year[year].add(session)
            areas_by_year_session[year][session].add(area)
            
        s = (q.get("subject") or "").strip()
        if qn.startswith("G") and s:
            subjects.add(s)
    
    years_sorted = sorted(years, reverse=True)
    
    # セッションをソート（1-1, 1-2, 1-3, 1再, 2, 2再 の順序）
    def sort_sessions(sessions):
        def session_key(s):
            if s == "1-1": return (1, 1, 0)
            elif s == "1-2": return (1, 2, 0)
            elif s == "1-3": return (1, 3, 0)
            elif s == "1再": return (1, 99, 0)
            elif s == "2": return (2, 0, 0)
            elif s == "2再": return (2, 99, 0)
            else: return (99, 0, 0)
        return sorted(sessions, key=session_key)
    
    sessions_map = {y: sort_sessions(list(sessions_by_year[y])) for y in years_sorted}
    areas_map = {}
    for year in years_sorted:
        areas_map[year] = {}
        for session in sessions_map[year]:
            areas_map[year][session] = sorted(list(areas_by_year_session[year][session]))
    
    gakushi_subjects = sorted(list(subjects))
    return years_sorted, sessions_map, areas_map, gakushi_subjects

def filter_gakushi_by_year_area(all_questions, year, area):
    yy = str(year)[2:]  # 2024 -> "24"
    pat = re.compile(rf'^G{yy}-[^-]+(?:-[^-]+)*-{area}-\d+$')
    res = []
    for q in all_questions:
        qn = q.get("number", "")
        if qn.startswith("G") and pat.match(qn):
            res.append(q)
    return res

def filter_gakushi_by_year_session_area(all_questions, year, session, area):
    """学士試験の年度、回数、領域で問題をフィルタリング"""
    yy = str(year)[2:]  # 2024 -> "24"
    # セッション部分をエスケープして正確にマッチさせる
    escaped_session = re.escape(session)
    pat = re.compile(rf'^G{yy}-{escaped_session}-{area}-\d+$')
    res = []
    for q in all_questions:
        qn = q.get("number", "")
        if qn.startswith("G") and pat.match(qn):
            res.append(q)
    return res

# 初期データ読み込み
CASES, ALL_QUESTIONS = load_master_data()  # バージョンパラメータで自動的にキャッシュ更新
ALL_QUESTIONS_DICT, ALL_SUBJECTS, ALL_EXAM_NUMBERS, ALL_EXAM_SESSIONS, HISSHU_Q_NUMBERS_SET, GAKUSHI_HISSHU_Q_NUMBERS_SET = get_derived_data(ALL_QUESTIONS)

# --- Firestore連携 ---
def load_user_data_minimal(user_id):
    """ログイン時にユーザーの基本プロフィール情報のみを高速読み込み"""
    import time
    start = time.time()
    
    if not ensure_valid_session():
        print(f"[DEBUG] load_user_data_minimal - セッション無効: {time.time() - start:.3f}s")
        return {"email": "", "settings": {"new_cards_per_day": 10}}

    uid = st.session_state.get("uid")
    
    if uid:
        db = get_db()
        if db:
            try:
                # /users/{uid} から基本プロフィールのみ読み込み
                start_read = time.time()
                doc_ref = db.collection("users").document(uid)
                doc = doc_ref.get(timeout=5)
                read_time = time.time() - start_read
                
                if doc.exists:
                    data = doc.to_dict()
                    total_time = time.time() - start
                    print(f"[DEBUG] load_user_data_minimal - 読み込み成功: {read_time:.3f}s, 合計: {total_time:.3f}s")
                    return data
                else:
                    # 新規ユーザーのデフォルトプロフィール作成
                    email = st.session_state.get("email", "")
                    default_profile = {
                        "email": email,
                        "createdAt": datetime.datetime.utcnow().isoformat(),
                        "settings": {"new_cards_per_day": 10}
                    }
                    doc_ref.set(default_profile)
                    print(f"[DEBUG] load_user_data_minimal - 新規プロフィール作成: {uid}")
                    return default_profile
                
            except Exception as e:
                print(f"[ERROR] load_user_data_minimal エラー: {e}")
    
    print(f"[DEBUG] load_user_data_minimal - デフォルト: {time.time() - start:.3f}s")
    return {"email": "", "settings": {"new_cards_per_day": 10}}




@st.cache_data(ttl=900)
@performance.trace
def load_user_data_full(user_id, cache_buster: int = 0):
    """演習開始時にユーザーの全カードデータを読み込む2段階読み込み版"""
    import time
    start = time.time()
    
    if not ensure_valid_session():
        print(f"[DEBUG] load_user_data_full - セッション無効: {time.time() - start:.3f}s")
        return {"cards": {}, "main_queue": [], "short_term_review_queue": [], "current_q_group": [], "new_cards_per_day": 10}

    uid = st.session_state.get("uid")
    
    if uid:
        db = get_db()
        if db:
            try:
                # 段階1: /users/{uid} から基本プロフィールを取得
                profile_start = time.time()
                user_ref = db.collection("users").document(uid)
                user_doc = user_ref.get(timeout=10)
                profile_time = time.time() - profile_start
                
                if not user_doc.exists:
                    print(f"[DEBUG] load_user_data_full - ユーザープロフィール未存在: {uid}")
                    return {"cards": {}, "main_queue": [], "short_term_review_queue": [], "current_q_group": [], "new_cards_per_day": 10}
                
                user_data = user_doc.to_dict()
                
                # 段階2: /users/{uid}/userCards サブコレクションから全カードを取得
                cards_start = time.time()
                cards_ref = db.collection("users").document(uid).collection("userCards")
                cards_docs = cards_ref.stream()
                
                cards = {}
                for doc in cards_docs:
                    cards[doc.id] = doc.to_dict()
                
                cards_time = time.time() - cards_start
                
                result = {
                    "cards": cards,
                    "main_queue": user_data.get("main_queue", []),
                    "short_term_review_queue": user_data.get("short_term_review_queue", []),
                    "current_q_group": user_data.get("current_q_group", []),
                    "new_cards_per_day": user_data.get("settings", {}).get("new_cards_per_day", 10),
                }
                
                total_time = time.time() - start
                print(f"[DEBUG] load_user_data_full - 成功: プロフィール {profile_time:.3f}s, カード {cards_time:.3f}s, 合計 {total_time:.3f}s, カード数: {len(cards)}")
                return result
                
            except Exception as e:
                print(f"[ERROR] load_user_data_full エラー: {e}")
    
    print(f"[DEBUG] load_user_data_full - デフォルト: {time.time() - start:.3f}s")
    return {"cards": {}, "main_queue": [], "short_term_review_queue": [], "current_q_group": [], "new_cards_per_day": 10}

def load_user_data(user_id):
    """後方互換性のため - 軽量版を呼び出す"""
    return load_user_data_minimal(user_id)

@performance.trace
def save_user_data(user_id, session_state):
    """新しいFirestore構造での分散データ保存"""
    try:
        if not ensure_valid_session():
            return

        db = get_db()
        if not db or not user_id:
            return
            
        # 1. SM-2進捗の更新: 変更されたカードのみ更新
        cards = session_state.get("cards", {})
        if cards:
            batch = db.batch()
            user_cards_ref = db.collection("users").document(user_id).collection("userCards")
            
            for question_id, card_data in cards.items():
                card_ref = user_cards_ref.document(question_id)
                batch.set(card_ref, card_data, merge=True)
            
            batch.commit()
            print(f"[DEBUG] save_user_data - カードデータ更新: {len(cards)}件")
        
        # 2. 学習ログの新規作成（解答時のみ）
        if session_state.get("latest_answer_log"):
            log_data = session_state["latest_answer_log"]
            log_data.update({
                "userId": user_id,
                "timestamp": datetime.datetime.utcnow().isoformat()
            })
            db.collection("learningLogs").add(log_data)
            # ログ送信後はクリア
            del session_state["latest_answer_log"]
            print(f"[DEBUG] save_user_data - 学習ログ作成: {log_data.get('questionId')}")
        
        # 3. 設定の更新（設定変更時のみ）
        settings_changed = session_state.get("settings_changed", False)
        if settings_changed:
            user_ref = db.collection("users").document(user_id)
            settings_update = {
                "settings": {
                    "new_cards_per_day": session_state.get("new_cards_per_day", 10)
                },
                "lastUpdated": datetime.datetime.utcnow().isoformat()
            }
            user_ref.update(settings_update)
            session_state["settings_changed"] = False
            print(f"[DEBUG] save_user_data - 設定更新完了")
            
    except Exception as e:
        print(f"[ERROR] save_user_data エラー: {e}")
        # エラーが発生してもアプリケーションを停止させない

# ユーザー権限チェック（キャッシュを復活）
@st.cache_data(ttl=300)  # 5分間キャッシュ
def check_gakushi_permission(user_id):
    """
    Firestoreのuser_permissionsコレクションから権限を判定。
    can_access_gakushi: trueならTrue, それ以外はFalse
    新しいFirestore構造対応版
    """
    db = get_db()
    if not db:
        return False
    
    uid = st.session_state.get("uid")
    if not uid:
        return False
    
    try:
        # /user_permissions/{uid} から権限情報を取得
        doc_ref = db.collection("user_permissions").document(uid)
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict()
            result = bool(data.get("can_access_gakushi", False))
            print(f"[DEBUG] 学士権限チェック(UID): {result}")
            return result
        else:
            print(f"[DEBUG] 学士権限なし: {uid}")
            return False
    except Exception as e:
        print(f"[ERROR] 学士権限チェックエラー: {e}")
        return False

def _subject_of(q):
    return (q.get("subject") or "未分類").strip()

def _make_subject_index(all_questions):
    qid_to_subject, subj_to_qids = {}, {}
    for q in all_questions:
        qid = q.get("number")
        if not qid: continue
        s = _subject_of(q)
        qid_to_subject[qid] = s
        subj_to_qids.setdefault(s, set()).add(qid)
    return qid_to_subject, subj_to_qids

def _recent_subject_penalty(q_subject, recent_qids, qid_to_subject):
    if not recent_qids: return 0.0
    recent_subjects = [qid_to_subject.get(r) for r in recent_qids if r in qid_to_subject]
    return 0.15 if q_subject in recent_subjects else 0.0

@performance.trace
def pick_new_cards_for_today(all_questions, cards, N=10, recent_qids=None):
    recent_qids = recent_qids or []
    qid_to_subject, subj_to_qids = _make_subject_index(all_questions)

    # 科目ごとの導入済み枚数
    introduced_counts = {subj: 0 for subj in subj_to_qids.keys()}
    for qid, card in cards.items():
        if qid in qid_to_subject:
            # n が 0 より大きいか、historyが存在する場合に導入済みとみなす
            if card.get("n", 0) > 0 or card.get("history"):
                introduced_counts[qid_to_subject[qid]] += 1

    # 目標は当面「均等配分」
    target_ratio = {subj: 1/len(subj_to_qids) for subj in subj_to_qids.keys()} if subj_to_qids else {}

    # 全体正答率（subject別が無くても動く簡易版）
    global_correct = global_total = 0
    for card in cards.values():
        for h in card.get("history", []):
            if isinstance(h, dict) and "quality" in h:
                global_total += 1
                if h["quality"] >= 4: global_correct += 1
    global_mastery = (global_correct / global_total) if global_total else 0.0

    # 候補は未演習のみ
    seen_qids = set(cards.keys())
    candidates = []
    for q in all_questions:
        qid = q.get("number")
        if not qid: continue
        c = cards.get(qid, {})
        if qid not in seen_qids or (not c.get("history") and c.get("n") in (None, 0)):
            candidates.append(q)

    def score_of(q):
        qid = q["number"]; subj = qid_to_subject.get(qid, "未分類")
        mastery_term = 1.0 - global_mastery
        subj_pool = len(subj_to_qids.get(subj, [])) or 1
        introduced_ratio = introduced_counts.get(subj, 0) / subj_pool
        gap = max(0.0, target_ratio.get(subj, 0.0) - introduced_ratio)
        difficulty_prior = 0.5
        penalty = _recent_subject_penalty(subj, recent_qids, qid_to_subject)
        return 0.6*mastery_term + 0.2*gap + 0.2*difficulty_prior - penalty

    # case_id がある問題は代表1問のみ（兄弟を同時に出さない）
    case_groups, singles = {}, []
    for q in candidates:
        cid = q.get("case_id")
        (case_groups.setdefault(cid, []).append(q)) if cid else singles.append(q)

    case_reps = [max(qs, key=score_of) for qs in case_groups.values()]
    pool_sorted = sorted(singles + case_reps, key=score_of, reverse=True)
    return [q["number"] for q in pool_sorted[:N]]

def list_storage_files(prefix="", max_files=50):
    """Firebase Storageのファイル一覧を取得してデバッグ用に表示"""
    try:
        bucket = get_bucket()  # 統一
        if bucket is None:
            return []
        blobs = bucket.list_blobs(prefix=prefix, max_results=max_files)
        files = [blob.name for blob in blobs]
        print(f"[DEBUG] Storage files with prefix '{prefix}': {files[:10]}...")  # 最初の10件のみ表示
        return files
    except Exception as e:
        print(f"[ERROR] Storage file listing error: {e}")
        return []

def get_secure_image_url(path):
    """
    Firebase Storageのパスから15分有効な署名付きURLを生成。
    http(s) はそのまま返す。gs:// にも対応。
    """
    print(f"[DEBUG] 画像URL生成開始: {path}")
    
    if isinstance(path, str) and (path.startswith('http://') or path.startswith('https://')):
        print(f"[DEBUG] HTTPURLをそのまま返却: {path}")
        return path
    try:
        # 既定バケット（initialize_firebaseで正しい appspot.com が設定されている前提）
        default_bucket = get_bucket()  # 統一
        if default_bucket is None:
            print(f"[ERROR] バケット取得失敗")
            return None
        blob = None

        if isinstance(path, str) and path.startswith("gs://"):
            print(f"[DEBUG] gs://形式のパス処理: {path}")
            # gs://<bucket>/<object> を安全に分解
            rest = path[5:]
            if "/" in rest:
                bname, bpath = rest.split("/", 1)
            else:
                bname, bpath = rest, ""
            print(f"[DEBUG] バケット名: {bname}, ブロブパス: {bpath}")
            bucket_to_use = storage.bucket(name=bname)
            blob = bucket_to_use.blob(bpath)
        else:
            print(f"[DEBUG] 相対パス処理: {path}")
            # 相対パスは既定バケット
            blob = default_bucket.blob(path)

        print(f"[DEBUG] blob作成完了: {blob.name}")
        
        # ブロブの存在確認を無効化して、とりあえずURL生成を試す
        try:
            # 存在確認をせずにURL生成を試行
            print(f"[DEBUG] 存在確認をスキップしてURL生成を試行")
            url = blob.generate_signed_url(
                expiration=datetime.timedelta(minutes=15),
                method="GET",
                version="v4"  # v4署名を明示
            )
            print(f"[DEBUG] 署名付きURL生成完了: {url[:100]}...")
            return url
        except Exception as url_err:
            print(f"[ERROR] URL生成エラー: {url_err}")
            
            # フォールバック: 異なるパス形式を試行
            alternative_paths = [
                path.replace("gakushi/", ""),  # gakushiプレフィックスを削除
                path.replace("/", "_"),  # スラッシュをアンダースコアに変更
                f"images/{path}",  # imagesプレフィックスを追加
                f"dental_images/{path}",  # dental_imagesプレフィックスを追加
            ]
            
            for alt_path in alternative_paths:
                try:
                    print(f"[DEBUG] 代替パス試行: {alt_path}")
                    alt_blob = default_bucket.blob(alt_path)
                    alt_url = alt_blob.generate_signed_url(
                        expiration=datetime.timedelta(minutes=15),
                        method="GET",
                        version="v4"
                    )
                    print(f"[DEBUG] 代替パス成功: {alt_path}")
                    return alt_url
                except Exception as alt_err:
                    print(f"[DEBUG] 代替パス失敗: {alt_path} - {alt_err}")
                    continue
            
            print(f"[ERROR] 全ての代替パスでも失敗")
            return None
            
    except Exception as e:
        print(f"[ERROR] 画像URL生成エラー for {path}: {e}")
        import traceback
        print(f"[ERROR] スタックトレース: {traceback.format_exc()}")
        return None

def _latex_escape(s: str) -> str:
    """
    LaTeX特殊文字をエスケープする関数
    バックスラッシュを最初に処理して二重エスケープを防ぐ
    """
    if not s:
        return ""
    # バックスラッシュを最初に処理
    s = s.replace("\\", r"\textbackslash{}")
    # 残りの特殊文字
    for a, b in [
        ("&", r"\&"), ("%", r"\%"), ("$", r"\$"),
        ("#", r"\#"), ("_", r"\_"), ("{", r"\{"), ("}", r"\}"),
        ("^", r"\textasciicircum{}"), ("~", r"\textasciitilde{}"),
    ]:
        s = s.replace(a, b)
    return s

import subprocess, shutil, tempfile

def create_simple_fallback_template(latex_source: str) -> str:
    """最小限のパッケージでフォールバック版LaTeXテンプレートを作成"""
    import re
    
    # 基本的なヘッダーのみ使用
    simple_header = r"""\documentclass[dvipdfmx,a4paper,uplatex]{jsarticle}
\usepackage[utf8]{inputenc}
\usepackage[dvipdfmx]{hyperref}
\usepackage{xcolor}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage[top=30truemm,bottom=30truemm,left=25truemm,right=25truemm]{geometry}
\newcommand{\ctext}[1]{\textcircled{\scriptsize{#1}}}
\begin{document}
"""
    
    # ボディ部分を抽出（\begin{document}から\end{document}まで）
    body_match = re.search(r'\\begin\{document\}(.*?)\\end\{document\}', latex_source, re.DOTALL)
    if body_match:
        body = body_match.group(1)
        # tcolorboxやその他の高度な機能を削除
        body = re.sub(r'\\begin\{tcolorbox\}.*?\\end\{tcolorbox\}', '', body, flags=re.DOTALL)
        body = re.sub(r'\\tcbset\{.*?\}', '', body)
        body = re.sub(r'\\tcbuselibrary\{.*?\}', '', body)
    else:
        body = "\n\\section{PDF生成エラー}\n最小限のテンプレートで生成しています。\n"
    
    return simple_header + body + "\n\\end{document}"

def compile_latex_to_pdf(latex_source: str, assets: dict | None = None):
    """
    LaTeX → PDF。画像バイト列(assets)を同一作業ディレクトリへ展開してから
    uplatex + dvipdfmx 優先でコンパイル。
    """
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tex_path = os.path.join(tmp, "doc.tex")
            with open(tex_path, "w", encoding="utf-8") as f:
                f.write(latex_source)

            # 画像を書き出し
            if assets:
                for name, data in assets.items():
                    with open(os.path.join(tmp, os.path.basename(name)), "wb") as g:
                        g.write(data)

            def _run(cmd):
                cp = subprocess.run(cmd, cwd=tmp, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                return cp.returncode, cp.stdout

            if shutil.which("uplatex") and shutil.which("dvipdfmx"):
                for i in range(2):
                    rc, log = _run(["uplatex", "-interaction=nonstopmode", "-halt-on-error", "doc.tex"])
                    if rc != 0:
                        # 最初の失敗時に、シンプルなテンプレートで再試行
                        if i == 0:
                            print(f"[DEBUG] uplatex failed on first try, attempting with minimal template")
                            simple_template = create_simple_fallback_template(latex_source)
                            with open(tex_path, "w", encoding="utf-8") as f:
                                f.write(simple_template)
                            continue
                        return None, f"uplatex failed (pass {i+1}):\n{log}"
                rc, log = _run(["dvipdfmx", "-o", "doc.pdf", "doc.dvi"])
                if rc != 0:
                    return None, f"dvipdfmx failed:\n{log}"
                pdf_path = os.path.join(tmp, "doc.pdf")
                if os.path.exists(pdf_path):
                    with open(pdf_path, "rb") as f:
                        return f.read(), "uplatex+dvipdfmx ok"
                return None, "PDF not found"

            if shutil.which("latexmk") and shutil.which("uplatex") and shutil.which("dvipdfmx"):
                rc, log = _run(["latexmk", "-interaction=nonstopmode", "-pdfdvi", "-latex=uplatex", "doc.tex"])
                pdf_path = os.path.join(tmp, "doc.pdf")
                if rc == 0 and os.path.exists(pdf_path):
                    with open(pdf_path, "rb") as f:
                        return f.read(), "latexmk ok"
                return None, f"latexmk failed:\n{log}"

            if shutil.which("tectonic"):
                rc, log = _run(["tectonic", "-X", "compile", "--keep-intermediates", "--keep-logs", "doc.tex"])
                pdf_path = os.path.join(tmp, "doc.pdf")
                if rc == 0 and os.path.exists(pdf_path):
                    with open(pdf_path, "rb") as f:
                        return f.read(), "tectonic ok"
                return None, f"tectonic failed:\n{log}"

            if shutil.which("xelatex"):
                # XeLaTeX用にテンプレートを変換
                with open(tex_path, "r", encoding="utf-8") as f:
                    orig = f.read()
                xetex_src = rewrite_to_xelatex_template(orig)
                with open(tex_path, "w", encoding="utf-8") as f:
                    f.write(xetex_src)
                
                for i in range(2):
                    rc, log = _run(["xelatex", "-interaction=nonstopmode", "-halt-on-error", "doc.tex"])
                    if rc != 0:
                        return None, f"xelatex failed (pass {i+1}):\n{log}"
                pdf_path = os.path.join(tmp, "doc.pdf")
                if os.path.exists(pdf_path):
                    with open(pdf_path, "rb") as f:
                        return f.read(), "xelatex ok"
                return None, "PDF not found"

            return None, "TeXエンジン未検出（uplatex/dvipdfmx 推奨）"
    except Exception as e:
        return None, f"Unexpected error: {e}"

def rewrite_to_xelatex_template(tex_source: str) -> str:
    """XeLaTeX用にjsarticleをbxjsarticleに変換し、日本語フォント設定を追加"""
    import re
    tex = tex_source
    # uplatexオプション付きのjsarticleをbxjsarticleに変換
    tex = re.sub(r"\\documentclass\[.*?\]\{jsarticle\}", r"\\documentclass[a4paper]{bxjsarticle}", tex, flags=re.S)
    tex = tex.replace(r"\usepackage[dvipdfmx]{hyperref}", r"\usepackage{hyperref}")
    if r"\usepackage{graphicx}" not in tex:
        tex = tex.replace(r"\begin{document}", r"\usepackage{graphicx}\n\begin{document}")
    if r"\usepackage{xeCJK}" not in tex:
        extra = r"""
\usepackage{xeCJK}
\setCJKmainfont{Noto Serif CJK JP}
\setCJKsansfont{Noto Sans CJK JP}
\setmainfont{Noto Serif}
"""
        tex = tex.replace(r"\begin{document}", extra + "\n\\begin{document}")
    return tex

# --- tcolorbox PDF用ヘルパ ---
def _answer_mark_for_overlay(answer_str: str) -> str:
    """'A', 'C', 'A/C' を右下用 'a', 'c', 'a/c' へ正規化"""
    if not answer_str:
        return ""
    raw = answer_str.replace("／", "/")
    letters = (raw.split("/") if "/" in raw else list(raw.strip()))
    def _to_alph(ch):
        return chr(ord('a') + (ord(ch.upper()) - ord('A'))) if ch.isalpha() else ch
    return "/".join(_to_alph(ch) for ch in letters if ch)

def _image_block_latex(file_list):
    """1枚 → 0.45幅、2枚 → 0.45×2、3枚以上 → 2列折返し"""
    if not file_list:
        return ""
    if len(file_list) == 1:
        return rf"\begin{{center}}\includegraphics[width=0.45\textwidth]{{{file_list[0]}}}\end{{center}}"
    if len(file_list) == 2:
        a, b = file_list[0], file_list[1]
        return (r"\begin{center}"
                rf"\includegraphics[width=0.45\textwidth]{{{a}}}"
                rf"\includegraphics[width=0.45\textwidth]{{{b}}}"
                r"\end{center}")
    out = [r"\begin{center}"]
    for i, fn in enumerate(file_list):
        out.append(rf"\includegraphics[width=0.45\textwidth]{{{fn}}}")
        if i % 2 == 1 and i != len(file_list) - 1:
            out.append(r"\\[0.5ex]")
    out.append(r"\end{center}")
    return "\n".join(out)

def _gather_images_for_questions(questions):
    """
    各問題の image_urls / image_paths を署名URL化してダウンロード。
    戻り値: ( {ファイル名:バイト列}, [[問題ごとのローカル名...], ...] )
    """
    import pathlib
    assets = {}
    per_q_files = []
    session = get_http_session()

    for qi, q in enumerate(questions, start=1):
        files = []
        candidates = []
        for k in ("image_urls", "image_paths"):
            v = q.get(k)
            if v: candidates.extend(v)

        # URL解決（http/https はそのまま、Storage パスは署名URL）
        resolved = []
        for path in candidates:
            if isinstance(path, str) and (path.startswith("http://") or path.startswith("https://")):
                resolved.append(path)
            else:
                url = get_secure_image_url(path)
                if url: resolved.append(url)

        # ダウンロード
        for j, url in enumerate(resolved, start=1):
            try:
                r = session.get(url, timeout=10)
                if r.status_code != 200:
                    continue
                # 拡張子推定
                ext = ".jpg"
                p = pathlib.Path(url.split("?")[0])
                if p.suffix.lower() in [".jpg", ".jpeg", ".png", ".pdf"]:
                    ext = p.suffix.lower()
                else:
                    ct = (r.headers.get("Content-Type") or "").lower()
                    if "png" in ct: ext = ".png"
                    if "jpeg" in ct or "jpg" in ct: ext = ".jpg"
                name = f"q{qi:03d}_img{j:02d}{ext}"
                assets[name] = r.content
                files.append(name)
            except Exception:
                continue

        per_q_files.append(files)

    return assets, per_q_files

def export_questions_to_latex_tcb_jsarticle(questions, right_label_fn=None):
    """
    tcolorbox(JS)版のLaTeX生成。高品質レイアウトで問題を出力。
    right_label_fn: lambda q -> 右上に出す文字列（例: 科目/年度など）。未指定なら '◯◯◯◯◯'
    title={...} には q['display_title']→q['number'] の優先で入れます。
    """
    header = r"""\documentclass[dvipdfmx,a4paper,uplatex]{jsarticle}
\usepackage[utf8]{inputenc}
\usepackage[dvipdfmx]{hyperref}
\hypersetup{colorlinks=true,citecolor=blue,linkcolor=blue}
\usepackage{xcolor}
\definecolor{lightgray}{HTML}{F9F9F9}
\renewcommand{\labelitemi}{・}
\def\labelitemi{・}
\usepackage{tikz}
\usetikzlibrary{calc}
\IfFileExists{bxtexlogo.sty}{\usepackage{bxtexlogo}}{}
\IfFileExists{ascmac.sty}{\usepackage{ascmac}}{}
\IfFileExists{mhchem.sty}{\usepackage[version=3]{mhchem}}{}
\usepackage{tcolorbox}
\tcbuselibrary{breakable, skins, theorems}
\usepackage[top=30truemm,bottom=30truemm,left=25truemm,right=25truemm]{geometry}
\newcommand{\ctext}[1]{\raise0.2ex\hbox{\textcircled{\scriptsize{#1}}}}
\renewcommand{\labelenumii}{\theenumii}
\renewcommand{\theenumii}{\alph{enumi}}
\IfFileExists{chemfig.sty}{\usepackage{chemfig}}{}
\IfFileExists{adjustbox.sty}{\usepackage{adjustbox}}{}
\usepackage{amsmath,amssymb}
\usepackage{tabularx}
\usepackage{enumitem}
\usepackage{graphicx} % 画像
\begin{document}
"""
    body = []
    for i, q in enumerate(questions, start=1):
        title_text = _latex_escape(q.get("display_title") or q.get("number") or f"問{i}")
        question_text = _latex_escape(q.get("question", "") or "")
        right_label = _latex_escape((right_label_fn(q) if right_label_fn else "◯◯◯◯◯") or "")
        ans_mark = _answer_mark_for_overlay((q.get("answer") or "").strip())

        box_open = (
            rf"\begin{{tcolorbox}}"
            r"[enhanced, colframe=black, colback=white,"
            rf" title={{{title_text}}}, fonttitle=\bfseries, breakable=true,"
            r" coltitle=black,"
            r" attach boxed title to top left={xshift=5mm, yshift=-3mm},"
            r" boxed title style={colframe=black, colback=white, },"
            r" top=4mm,"
            r" overlay={"
            + (rf"\node[anchor=north east, xshift=-5mm, yshift=3mm, font=\bfseries\Large, fill=white, inner sep=2pt] at (frame.north east) {{{right_label}}};" if right_label else "")
            + (rf"\node[anchor=south east, xshift=-3mm, yshift=3mm] at (frame.south east) {{{ans_mark}}};" if ans_mark else "")
            + r"}]"
        )
        body.append(box_open)
        body.append(question_text)

        # 画像スロット（後で置換）
        body.append(rf"%__IMAGES_SLOT__{i}__")

        # 選択肢
        choices = q.get("choices") or []
        if choices:
            body.append(r"\begin{enumerate}[nosep, left=0pt,label=\alph*.]")
            for ch in choices:
                text = ch.get("text", str(ch)) if isinstance(ch, dict) else str(ch)
                body.append(r"\item " + _latex_escape(text))
            body.append(r"\end{enumerate}")

        body.append(r"\end{tcolorbox}")
        body.append(r"\vspace{0.8em}")

        # ▼ここを変更：各問題ごとに改ページ（最後だけ入れない）
        if i < len(questions):
            body.append(r"\clearpage")  # 画像(浮動体)があっても確実に改ページ

    footer = r"\end{document}"
    return header + "\n".join(body) + "\n" + footer

def get_shuffled_choices(q):
    key = f"shuffled_{q['number']}"
    if key not in st.session_state or len(st.session_state.get(key, [])) != len(q.get("choices", [])):
        indices = list(range(len(q.get("choices", []))))
        random.shuffle(indices)
        st.session_state[key] = indices
    return [q["choices"][i] for i in st.session_state[key]], st.session_state[key]

def extract_year_from_question_number(q_num):
    """
    問題番号から年度を抽出する
    従来形式: "112A5" -> 112
    学士試験形式: "G22-1-1-A-1" -> 2022
    """
    if not q_num:
        return None
    
    # 従来形式（例：112A5）
    if q_num[:3].isdigit():
        return int(q_num[:3])
    
    # 学士試験形式（例：G22-1-1-A-1）
    if q_num.startswith("G") and len(q_num) >= 3 and q_num[1:3].isdigit():
        year_2digit = int(q_num[1:3])
        # 2桁年を4桁年に変換（22 -> 2022）
        return 2000 + year_2digit if year_2digit <= 30 else 1900 + year_2digit
    
    return None

def get_natural_sort_key(q_dict):
    """
    問題辞書を受け取り、自然順ソート用のキー（タプル）を返す。
    例: "112A5" -> (112, 'A', 5)
    学士試験形式: "G24-1-1-A-1" や "G24-2再-A-1" -> ('G', 24, '1-1', 'A', 1)
    """
    try:
        q_num_str = q_dict.get('number', '0')
        # 学士試験形式: G24-1-1-A-1 や G24-2再-A-1 に対応
        # データ正規化済みでハイフンのみ使用
        m_gakushi = re.match(r'^(G)(\d+)-([\d\-再]+)-([A-Z])-(\d+)$', q_num_str)
        if m_gakushi:
            return (
                0,                       # 学士試験は先頭に0を置いて従来形式と区別
                m_gakushi.group(1),      # G
                int(m_gakushi.group(2)), # 24
                m_gakushi.group(3),      # '1-1' や '2再' など（文字列としてソート）
                m_gakushi.group(4),      # A
                int(m_gakushi.group(5))  # 1
            )
        # 従来形式: 112A5
        m_normal = re.match(r'^(\d+)([A-Z]*)(\d+)$', q_num_str)
        if m_normal:
            part1 = int(m_normal.group(1))
            part2 = m_normal.group(2)
            part3 = int(m_normal.group(3))
            return (1, part1, part2, part3, "", 0)  # 従来形式は1から始めて構造を統一
        # フォールバック: すべて文字列として扱う
        return (2, q_num_str, "", 0, "", 0)
    except Exception as e:
        # エラーが発生した場合のフォールバック: すべて文字列として扱う
        return (3, str(q_dict.get('number', 'unknown')), "", 0, "", 0)

def chem_latex(text):
    return text.replace('Ca2+', '$\\mathrm{Ca^{2+}}$')

def is_ordering_question(q):
    text = q.get("question", "")
    keywords = ["順番に並べよ", "正しい順序", "適切な順序", "正しい順番", "順序で"]
    return any(k in text for k in keywords)

def search_questions_by_keyword(keyword, gakushi_only=False, has_gakushi_permission=True):
    """
    キーワードで問題を検索する関数
    問題文、選択肢、解説などからキーワードを検索
    has_gakushi_permission: 学士試験の問題を表示する権限があるかどうか
    """
    if not keyword:
        return []
    
    keyword_lower = keyword.lower()
    matching_questions = []
    
    for q in ALL_QUESTIONS:
        question_number = q.get("number", "")
        
        # 学士試験の問題かどうかをチェック
        is_gakushi_question = question_number.startswith("G")
        
        # 権限チェック：学士試験の問題で権限がない場合はスキップ
        if is_gakushi_question and not has_gakushi_permission:
            continue
        
        # 学士試験限定検索の場合、学士試験の問題のみに絞る
        if gakushi_only and not is_gakushi_question:
            continue
        
        # 検索対象のテキストを収集
        search_texts = []
        
        # 問題文
        if q.get("question"):
            search_texts.append(q["question"])
        
        # 選択肢
        if q.get("choices"):
            for choice in q["choices"]:
                if isinstance(choice, dict):
                    search_texts.append(choice.get("text", ""))
                else:
                    search_texts.append(str(choice))
        
        # 解説
        if q.get("explanation"):
            search_texts.append(q["explanation"])
        
        # 科目
        if q.get("subject"):
            search_texts.append(q["subject"])
        
        # すべてのテキストを結合して検索
        combined_text = " ".join(search_texts).lower()
        
        # キーワードが含まれているかチェック
        if keyword_lower in combined_text:
            matching_questions.append(q)
    
    return matching_questions

def calculate_card_level(n, latest_quality, history):
    """
    学習回数と評価履歴に基づいてカードのレベルを計算
    - n: 学習回数（SM-2のnパラメータ）
    - latest_quality: 最新の評価（1-5）
    - history: 評価履歴のリスト
    """
    if n == 0:
        return 0  # 未学習
    
    # 最近の成績を重視した評価計算
    if len(history) == 0:
        avg_quality = latest_quality
    else:
        # 最新5回の評価の平均を計算（重み付き：最新ほど重要）
        recent_qualities = []
        for i, record in enumerate(history[-5:]):
            weight = i + 1  # 新しいほど重み大
            recent_qualities.extend([record["quality"]] * weight)
        
        # 最新の評価も追加
        recent_qualities.extend([latest_quality] * len(recent_qualities))
        avg_quality = sum(recent_qualities) / len(recent_qualities)
    
    # レベル計算ロジック
    if n >= 10 and avg_quality >= 4.5:
        return 6  # 習得済み相当
    elif n >= 8 and avg_quality >= 4.0:
        return 5
    elif n >= 6 and avg_quality >= 3.5:
        return 4
    elif n >= 4 and avg_quality >= 3.0:
        return 3
    elif n >= 2 and avg_quality >= 2.5:
        return 2
    elif n >= 1:
        return 1
    else:
        return 0

def sm2_update(card, quality, now=None):
    if now is None: now = datetime.datetime.now(datetime.timezone.utc)
    EF, n, I = card.get("EF", 2.5), card.get("n", 0), card.get("I", 0)
    if quality == 1:
        n = 0
        EF = max(EF - 0.3, 1.3)
        I = 10 / 1440
    elif quality == 2:
        EF = max(EF - 0.15, 1.3)
        I = max(card.get("I", 1) * 0.5, 10 / 1440)
    elif quality == 4 or quality == 5:
        if n == 0:
            I = 1
        elif n == 1:
            I = 4
        else:
            EF = max(EF + (0.1 - (5-quality)*(0.08 + (5-quality)*0.02)), 1.3)
            I = card.get("I", 1) * EF
        n += 1
        if quality == 5:
            I *= 1.3
    else:
        n = 0
        I = 10 / 1440
    next_review_dt = now + datetime.timedelta(days=I)
    card["history"] = card.get("history", []) + [{"timestamp": now.isoformat(), "quality": quality, "interval": I, "EF": EF}]
    
    # レベル計算（学習回数と成績に基づく）
    level = calculate_card_level(n, quality, card.get("history", []))
    
    card.update({"EF": EF, "n": n, "I": I, "next_review": next_review_dt.isoformat(), "quality": quality, "level": level})
    return card

def sm2_update_with_policy(card: dict, quality: int, q_num_str: str, now=None):
    """必修は q==2 を lapse 扱い。それ以外は既存 sm2_update を適用。"""
    if now is None:
        now = datetime.datetime.now(datetime.timezone.utc)
    # 国試の必修または学士試験の必修で「難しい」の場合は lapse 扱い
    if (is_hisshu(q_num_str) or is_gakushi_hisshu(q_num_str)) and quality == 2:
        # ★ 必修で「難しい」の場合は lapse 扱い
        EF = max(card.get("EF", 2.5) - 0.2, 1.3)
        n = 0
        I = 10 / 1440  # 10分
        next_review_dt = now + datetime.timedelta(minutes=10)
        hist = card.get("history", [])
        hist = hist + [{"timestamp": now.isoformat(), "quality": quality, "interval": I, "EF": EF}]
        card.update({"EF": EF, "n": n, "I": I, "next_review": next_review_dt.isoformat(), "quality": quality, "history": hist})
        return card
    else:
        return sm2_update(card, quality, now=now)

# --- 検索ページ ---
def render_search_page():
    # サイドバーのフィルター設定を取得
    uid = st.session_state.get("uid")
    has_gakushi_permission = check_gakushi_permission(uid)
    analysis_target = st.session_state.get("analysis_target", "国試")
    level_filter = st.session_state.get("level_filter", ["未学習", "レベル0", "レベル1", "レベル2", "レベル3", "レベル4", "レベル5", "習得済み"])
    
    # 学習進捗の可視化セクションを追加
    st.subheader("📈 学習ダッシュボード")
    
    # 学習データの準備
    cards = st.session_state.get("cards", {})
    
    # 分析対象に応じたフィルタリング
    filtered_data = []
    for q in ALL_QUESTIONS:
        q_num = q.get("number", "")
        # 権限チェック
        if q_num.startswith("G") and not has_gakushi_permission:
            continue
        
        # 分析対象フィルタ
        if analysis_target == "学士試験" and not q_num.startswith("G"):
            continue
        elif analysis_target == "国試" and q_num.startswith("G"):
            continue
        # analysis_target == "全体" の場合は両方含める（何もしない）
            
        card = cards.get(q_num, {})
        
        # レベル計算
        if not card:
            level = "未学習"
        else:
            # SM-2アルゴリズムのnと評価履歴から動的にレベル計算
            n = card.get("n", 0)
            latest_quality = card.get("quality", 1)
            history = card.get("history", [])
            card_level = calculate_card_level(n, latest_quality, history)
            
            if card_level >= 6:
                level = "習得済み"
            else:
                level = f"レベル{card_level}"
        
        # 必修問題チェック
        if analysis_target == "学士試験":
            is_hisshu = q_num in GAKUSHI_HISSHU_Q_NUMBERS_SET
        else:
            is_hisshu = q_num in HISSHU_Q_NUMBERS_SET
        
        filtered_data.append({
            "id": q_num,
            "subject": q.get("subject", "未分類"),
            "level": level,
            "ef": card.get("EF", 2.5),  # 大文字EFに修正
            "history": card.get("history", []),
            "is_hisshu": is_hisshu
        })
    
    # DataFrameに変換
    import pandas as pd
    filtered_df = pd.DataFrame(filtered_data)
    
    # 科目リストをサイドバー用に設定
    if not filtered_df.empty:
        available_subjects = sorted(filtered_df["subject"].unique())
        st.session_state.available_subjects = available_subjects
        # 科目フィルターの取得（デフォルトは全科目）
        subject_filter = st.session_state.get("subject_filter", available_subjects)
        
        # レベルと科目でフィルタリング
        filtered_df = filtered_df[
            (filtered_df["level"].isin(level_filter)) &
            (filtered_df["subject"].isin(subject_filter))
        ]
    else:
        st.session_state.available_subjects = []
    
    # 4タブ構成の可視化
    tab1, tab2, tab3, tab4 = st.tabs(["概要", "グラフ分析", "問題リスト", "キーワード検索"])
    
    with tab1:
        st.subheader("学習状況サマリー")
        if filtered_df.empty:
            st.warning("選択された条件に一致する問題がありません。")
        else:
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("##### カード習熟度分布")
                levels_sorted = ["未学習", "レベル0", "レベル1", "レベル2", "レベル3", "レベル4", "習得済み"]
                level_counts = filtered_df["level"].value_counts().reindex(levels_sorted).fillna(0).astype(int)
                st.dataframe(level_counts)
            with col2:
                st.markdown("##### 正解率 (True Retention)")
                total_reviews = 0
                correct_reviews = 0
                for history_list in filtered_df["history"]:
                    for review in history_list:
                        if isinstance(review, dict) and "quality" in review:
                            total_reviews += 1
                            if review["quality"] >= 4:
                                correct_reviews += 1
                retention_rate = (correct_reviews / total_reviews * 100) if total_reviews > 0 else 0
                st.metric(label="選択範囲の正解率", value=f"{retention_rate:.1f}%", delta=f"{correct_reviews} / {total_reviews} 回")
                
                # 必修問題の正解率計算
                if analysis_target == "学士試験":
                    hisshu_df = filtered_df[filtered_df["is_hisshu"] == True]
                    hisshu_label = "【学士試験・必修問題】の正解率 (目標: 80%以上)"
                else:
                    hisshu_df = filtered_df[filtered_df["id"].isin(HISSHU_Q_NUMBERS_SET)]
                    hisshu_label = "【必修問題】の正解率 (目標: 80%以上)"
                
                hisshu_total_reviews = 0
                hisshu_correct_reviews = 0
                for history_list in hisshu_df["history"]:
                    for review in history_list:
                        if isinstance(review, dict) and "quality" in review:
                            hisshu_total_reviews += 1
                            if review["quality"] >= 4:
                                hisshu_correct_reviews += 1
                hisshu_retention_rate = (hisshu_correct_reviews / hisshu_total_reviews * 100) if hisshu_total_reviews > 0 else 0
                st.metric(label=hisshu_label, value=f"{hisshu_retention_rate:.1f}%", delta=f"{hisshu_correct_reviews} / {hisshu_total_reviews} 回")

    with tab2:
        st.subheader("学習データの可視化")
        if filtered_df.empty:
            st.warning("選択された条件に一致する問題がありません。")
        else:
            st.markdown("##### 学習の記録")
            review_history = []
            for history_list in filtered_df["history"]:
                for review in history_list:
                    if isinstance(review, dict) and "timestamp" in review:
                        review_history.append(datetime.datetime.fromisoformat(review["timestamp"]).date())
            
            if review_history:
                from collections import Counter
                review_counts = Counter(review_history)
                ninety_days_ago = datetime.datetime.now(datetime.timezone.utc).date() - datetime.timedelta(days=90)
                dates = [ninety_days_ago + datetime.timedelta(days=i) for i in range(91)]
                counts = [review_counts.get(d, 0) for d in dates]
                chart_df = pd.DataFrame({"Date": dates, "Reviews": counts})
                
                # plotlyを使ってy軸の最小値を0に固定
                try:
                    import plotly.express as px
                    fig = px.bar(chart_df, x="Date", y="Reviews", 
                                title="日々の学習量（過去90日間）")
                    fig.update_layout(
                        yaxis=dict(range=[0, max(counts) * 1.1] if counts else [0, 5]),
                        showlegend=False
                    )
                    st.plotly_chart(fig, use_container_width=True)
                except ImportError:
                    # plotlyが利用できない場合は従来のbar_chart
                    st.bar_chart(chart_df.set_index("Date"))
            else:
                st.info("選択された範囲にレビュー履歴がまだありません。")
            
            st.markdown("##### 学習レベル別分布")
            if not filtered_df.empty:
                level_counts = filtered_df['level'].value_counts()
                
                # 色分け定義
                level_colors_chart = {
                    "未学習": "#757575", "レベル0": "#FF9800", "レベル1": "#FFC107",
                    "レベル2": "#8BC34A", "レベル3": "#9C27B0", "レベル4": "#03A9F4",
                    "レベル5": "#1E88E5", "習得済み": "#4CAF50"
                }
                
                try:
                    import plotly.express as px
                    import pandas as pd
                    
                    # レベル順に並べ替え
                    level_order = ["未学習", "レベル0", "レベル1", "レベル2", "レベル3", "レベル4", "レベル5", "習得済み"]
                    chart_data = []
                    colors = []
                    
                    for level in level_order:
                        if level in level_counts.index:
                            chart_data.append({"Level": level, "Count": level_counts[level]})
                            colors.append(level_colors_chart.get(level, "#888888"))
                    
                    chart_df = pd.DataFrame(chart_data)
                    
                    fig = px.bar(chart_df, x="Level", y="Count", 
                                title="学習レベル別問題数",
                                color="Level",
                                color_discrete_map=level_colors_chart)
                    fig.update_layout(
                        yaxis=dict(range=[0, None]),
                        showlegend=False,
                        xaxis_tickangle=-45
                    )
                    st.plotly_chart(fig, use_container_width=True)
                    
                except ImportError:
                    # plotlyが利用できない場合は基本的なbar_chart
                    st.bar_chart(level_counts)
            else:
                st.info("学習データがありません。")

    with tab3:
        st.subheader("問題リスト")
        level_colors = {
            "未学習": "#757575", "レベル0": "#FF9800", "レベル1": "#FFC107",
            "レベル2": "#8BC34A", "レベル3": "#9C27B0", "レベル4": "#03A9F4",
            "レベル5": "#1E88E5", "習得済み": "#4CAF50"
        }
        
        # サイドバーのフィルターを適用
        if not filtered_df.empty:
            # サイドバーの level_filter は既に適用済み
            
            st.markdown(f"**{len(filtered_df)}件の問題が見つかりました**")
            if not filtered_df.empty:
                def sort_key(row_id):
                    m_gakushi = re.match(r'^(G)(\d+)[–\-]([\d–\-再]+)[–\-]([A-Z])[–\-](\d+)$', str(row_id))
                    if m_gakushi: return (m_gakushi.group(1), int(m_gakushi.group(2)), m_gakushi.group(3), m_gakushi.group(4), int(m_gakushi.group(5)))
                    m_normal = re.match(r"(\d+)([A-D])(\d+)", str(row_id))
                    if m_normal: return ('Z', int(m_normal.group(1)), m_normal.group(2), '', int(m_normal.group(3)))
                    return ('Z', 0, '', '', 0)

                detail_filtered_sorted = filtered_df.copy()
                detail_filtered_sorted['sort_key'] = detail_filtered_sorted['id'].apply(sort_key)
                detail_filtered_sorted = detail_filtered_sorted.sort_values(by='sort_key').drop(columns=['sort_key'])
                for _, row in detail_filtered_sorted.iterrows():
                    # 権限チェック：学士試験の問題で権限がない場合はスキップ
                    if str(row.id).startswith("G") and not has_gakushi_permission:
                        continue
                        
                    st.markdown(
                        f"<div style='margin-bottom: 5px; padding: 5px; border-left: 5px solid {level_colors.get(row.level, '#888')};'>"
                        f"<span style='display:inline-block;width:80px;font-weight:bold;color:{level_colors.get(row.level, '#888')};'>{row.level}</span>"
                        f"<span style='font-size:1.1em;'>{row.id}</span>"
                        f"</div>",
                        unsafe_allow_html=True
                    )
            else:
                st.info("フィルタ条件に一致する問題がありません。")
        else:
            st.info("表示する問題がありません。")
    
    with tab4:
        # キーワード検索フォーム（サイドバーフィルター連動）
        st.subheader("🔍 キーワード検索")
        
        col1, col2 = st.columns([4, 1])
        with col1:
            search_keyword = st.text_input("検索キーワード", placeholder="検索したいキーワードを入力", key="search_keyword_input")
        with col2:
            shuffle_results = st.checkbox("結果をシャッフル", key="shuffle_checkbox")
        
        search_btn = st.button("検索実行", type="primary", use_container_width=True)
        
        # キーワード検索の実行と結果表示
        if search_btn and search_keyword.strip():
            # キーワード検索を実行
            search_words = [word.strip() for word in search_keyword.strip().split() if word.strip()]
            
            keyword_results = []
            for q in ALL_QUESTIONS:
                # 権限チェック：学士試験の問題で権限がない場合はスキップ
                question_number = q.get('number', '')
                if question_number.startswith("G") and not has_gakushi_permission:
                    continue
                
                # 分析対象フィルタチェック（サイドバーの設定を使用）
                if analysis_target == "学士試験" and not question_number.startswith("G"):
                    continue
                elif analysis_target == "国試" and question_number.startswith("G"):
                    continue
                # analysis_target == "全体" の場合は全て含める
                
                # キーワード検索
                text_to_search = f"{q.get('question', '')} {q.get('subject', '')} {q.get('number', '')}"
                if any(word.lower() in text_to_search.lower() for word in search_words):
                    keyword_results.append(q)
            
            # シャッフル処理
            if shuffle_results:
                random.shuffle(keyword_results)
            
            # 結果をセッション状態に保存
            st.session_state["search_results"] = keyword_results
            st.session_state["search_query"] = search_keyword.strip()
            st.session_state["search_page_analysis_target"] = analysis_target
            st.session_state["search_page_shuffle_setting"] = shuffle_results
        
        # 検索結果の表示
        if "search_results" in st.session_state:
            results = st.session_state["search_results"]
            query = st.session_state.get("search_query", "")
            search_type = st.session_state.get("search_page_analysis_target", "全体")
            shuffle_info = "（シャッフル済み）" if st.session_state.get("search_page_shuffle_setting", False) else "（順番通り）"
            
            if results:
                st.success(f"「{query}」で{len(results)}問見つかりました（{search_type}）{shuffle_info}")
                
                # 結果の統計を表示
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("検索結果", f"{len(results)}問")
                with col2:
                    subjects = [q.get("subject", "未分類") for q in results]
                    unique_subjects = len(set(subjects))
                    st.metric("関連科目", f"{unique_subjects}科目")
                with col3:
                    years = []
                    for q in results:
                        year = extract_year_from_question_number(q.get("number", ""))
                        if year is not None:
                            years.append(int(year))
                    
                    year_range = f"{min(years)}-{max(years)}" if years else "不明"
                    st.metric("年度範囲", year_range)
                
                # 検索結果の詳細表示
                st.subheader("検索結果")
                
                # レベル別色分け定義
                level_colors = {
                    "未学習": "#757575", "レベル0": "#FF9800", "レベル1": "#FFC107",
                    "レベル2": "#8BC34A", "レベル3": "#9C27B0", "レベル4": "#03A9F4",
                    "レベル5": "#1E88E5", "習得済み": "#4CAF50"
                }
                
                level_icons = {
                    "未学習": "#757575",        # グレー系
                    "レベル0": "#FF9800",      # オレンジ #FF9800
                    "レベル1": "#FFC107",      # イエロー #FFC107
                    "レベル2": "#8BC34A",      # グリーン #8BC34A
                    "レベル3": "#9C27B0",      # パープル #9C27B0
                    "レベル4": "#03A9F4",      # ブルー #03A9F4
                    "レベル5": "#1E88E5",      # ダークブルー #1E88E5
                    "習得済み": "#4CAF50"      # グリーン完了 #4CAF50
                }
                
                for i, q in enumerate(results[:20]):  # 最初の20件を表示
                    # 権限チェック：学士試験の問題で権限がない場合はスキップ
                    question_number = q.get('number', '')
                    if question_number.startswith("G") and not has_gakushi_permission:
                        continue
                    
                    # 学習レベルの取得
                    card = st.session_state.cards.get(question_number, {})
                    if not card:
                        level = "未学習"
                    else:
                        card_level = card.get("level", 0)
                        if card_level >= 6:
                            level = "習得済み"
                        else:
                            level = f"レベル{card_level}"
                    
                    # 必修問題チェック
                    if search_type == "学士試験":
                        is_hisshu = question_number in GAKUSHI_HISSHU_Q_NUMBERS_SET
                    else:
                        is_hisshu = question_number in HISSHU_Q_NUMBERS_SET
                    
                    level_color = level_colors.get(level, "#888888")
                    hisshu_mark = "🔥" if is_hisshu else ""
                    
                    # 色付きドットアイコンをHTMLで生成
                    color_dot = f'<span style="color: {level_color}; font-size: 1.2em; font-weight: bold;">●</span>'
                    
                    with st.expander(f"● {q.get('number', 'N/A')} - {q.get('subject', '未分類')} {hisshu_mark}"):
                        # レベルを大きく色付きで表示  
                        st.markdown(f"**学習レベル:** <span style='color: {level_color}; font-weight: bold; font-size: 1.2em;'>{level}</span>", unsafe_allow_html=True)
                        st.markdown(f"**問題:** {q.get('question', '')[:100]}...")
                        if q.get('choices'):
                            st.markdown("**選択肢:**")
                            for j, choice in enumerate(q['choices']):  # 全ての選択肢を表示
                                choice_text = choice.get('text', str(choice)) if isinstance(choice, dict) else str(choice)
                                st.markdown(f"  {chr(65+j)}. {choice_text[:50]}...")
                        
                        # 学習履歴の表示
                        if card and card.get('history'):
                            st.markdown(f"**学習履歴:** {len(card['history'])}回")
                            for j, review in enumerate(card['history'][-3:]):  # 最新3件
                                if isinstance(review, dict):
                                    timestamp = review.get('timestamp', '不明')
                                    quality = review.get('quality', 0)
                                    quality_emoji = "✅" if quality >= 4 else "❌"
                                    st.markdown(f"  {j+1}. {timestamp} - 評価: {quality} {quality_emoji}")
                        else:
                            st.markdown("**学習履歴:** なし")
                
                if len(results) > 20:
                    st.info(f"表示は最初の20件です。全{len(results)}件中")
                
                # PDF生成とダウンロード機能
                st.markdown("#### 📄 PDF生成")
                
                colA, colB = st.columns(2)
                with colA:
                    if st.button("📄 PDFを生成", key="pdf_tcb_js_generate"):
                        with st.spinner("PDFを生成中..."):
                            # 1) LaTeX本文（右上は固定の'◯◯◯◯◯'を表示）
                            latex_tcb = export_questions_to_latex_tcb_jsarticle(results)
                            # 2) 画像収集（URL/Storage問わず）
                            assets, per_q_files = _gather_images_for_questions(results)
                            # 3) 画像スロットを includegraphics に差し替え
                            for i, files in enumerate(per_q_files, start=1):
                                block = _image_block_latex(files)
                                latex_tcb = latex_tcb.replace(rf"%__IMAGES_SLOT__{i}__", block)
                            # 4) コンパイル
                            pdf_bytes, log = compile_latex_to_pdf(latex_tcb, assets=assets)
                            if pdf_bytes:
                                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                                st.session_state["pdf_bytes_tcb_js"] = pdf_bytes
                                st.session_state["pdf_filename_tcb_js"] = f"dental_questions_tcb_js_{ts}.pdf"
                                st.success("✅ PDFの生成に成功しました。右のボタンからDLできます。")
                            else:
                                st.error("❌ PDF生成に失敗しました。")
                                with st.expander("ログを見る"):
                                    st.code(log or "no log", language="text")

                with colB:
                    if "pdf_bytes_tcb_js" in st.session_state:
                        # 統一されたPDFダウンロード（新タブで開く）
                        pdf_data = st.session_state["pdf_bytes_tcb_js"]
                        filename = st.session_state.get("pdf_filename_tcb_js", "dental_questions_tcb_js.pdf")
                        
                        # Base64エンコード
                        import base64
                        b64_pdf = base64.b64encode(pdf_data).decode()
                        
                        # Data URI を持つHTMLリンクを生成（新タブで開く）
                        href = f'<a href="data:application/pdf;base64,{b64_pdf}" download="{filename}" target="_blank" style="display: inline-block; padding: 12px; background-color: #ff6b6b; color: white; text-decoration: none; border-radius: 6px; text-align: center; width: 100%; font-size: 16px; font-weight: bold; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">📥 PDFをダウンロード</a>'
                        
                        st.markdown(href, unsafe_allow_html=True)
                    else:
                        st.button("⬇️ PDFをDL", disabled=True, use_container_width=True)
                
            else:
                st.warning(f"「{query}」に該当する問題が見つかりませんでした")
        else:
            st.info("キーワードを入力して検索してください")



# --- 短期復習キュー管理関数 ---
SHORT_REVIEW_COOLDOWN_MIN_Q1 = 5        # もう一度
SHORT_REVIEW_COOLDOWN_MIN_Q2_HISSHU = 10 # 必修で「難しい」

def enqueue_short_review(group, minutes: int):
    ready_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=minutes)
    st.session_state.short_term_review_queue = st.session_state.get("short_term_review_queue", [])
    st.session_state.short_term_review_queue.append({"group": group, "ready_at": ready_at})

# --- 演習ページ ---
def render_practice_page():
    # 前回セッション復帰処理
    if st.session_state.get("continue_previous") and st.session_state.get("session_choice_made"):
        st.success("🔄 前回のセッションを復帰しました")
        # 復帰フラグをクリア
        st.session_state.pop("continue_previous", None)
        
        # 前回のアクティブセッション情報があれば、完全なデータを読み込んでキューを復元
        if st.session_state.get("current_question_index") is not None:
            st.info(f"問題 {st.session_state.get('current_question_index', 0) + 1} から継続します")
        
        # おまかせ演習の場合は学習キューを復元
        uid = st.session_state.get("uid")
        if uid and st.session_state.get("previous_session_type") == "おまかせ演習":
            st.info("📚 おまかせ演習の学習キューを復元中...")
            # 完全なユーザーデータを読み込み
            full_data = load_user_data_full(uid, cache_buster=int(time.time()))
            if full_data:
                # 学習キューをセッションに復元
                st.session_state["main_queue"] = full_data.get("main_queue", [])
                st.session_state["short_term_review_queue"] = full_data.get("short_term_review_queue", [])
                st.session_state["current_q_group"] = full_data.get("current_q_group", [])
                print(f"[DEBUG] 学習キュー復元: main_queue={len(st.session_state.get('main_queue', []))}, current_q_group={len(st.session_state.get('current_q_group', []))}")
    
    def get_next_q_group():
        now = datetime.datetime.now(datetime.timezone.utc)
        
        # 利用可能な復習問題を取得
        stq = st.session_state.get("short_term_review_queue", [])
        ready_reviews = []
        for i, item in enumerate(stq):
            ra = item.get("ready_at")
            if isinstance(ra, str):
                try: ra = datetime.datetime.fromisoformat(ra)
                except Exception: ra = now
            if not ra or ra <= now:
                ready_reviews.append((i, item))
        
        # 利用可能な新規問題を取得
        main_queue = st.session_state.get("main_queue", [])
        
        # 復習問題と新規問題のバランス調整
        # 復習問題が多い場合は優先度を上げる
        review_count = len(ready_reviews)
        new_count = len(main_queue)
        
        # 復習問題が5個以上溜まっている場合は復習を優先
        if review_count >= 5:
            if ready_reviews:
                i, item = ready_reviews[0]
                stq.pop(i)
                return item.get("group", [])
        
        # 通常時：復習30%、新規70%の確率で選択
        elif review_count > 0 and new_count > 0:
            import random
            if random.random() < 0.3:  # 30%の確率で復習
                i, item = ready_reviews[0]
                stq.pop(i)
                return item.get("group", [])
            else:  # 70%の確率で新規
                return main_queue.pop(0)
        
        # 復習問題のみ利用可能
        elif ready_reviews:
            i, item = ready_reviews[0]
            stq.pop(i)
            return item.get("group", [])
        
        # 新規問題のみ利用可能
        elif main_queue:
            return main_queue.pop(0)
        
        return []

    if not st.session_state.get("current_q_group"):
        st.session_state.current_q_group = get_next_q_group()

    current_q_group = st.session_state.get("current_q_group", [])
    if not current_q_group:
        st.info("学習を開始するには、サイドバーで問題を選択してください。")
        st.stop()

    q_objects = []
    uid = st.session_state.get("uid")
    has_gakushi_permission = check_gakushi_permission(uid)
    
    for q_num in current_q_group:
        if q_num in ALL_QUESTIONS_DICT:
            # 権限チェック：学士試験の問題で権限がない場合はスキップ
            if q_num.startswith("G") and not has_gakushi_permission:
                continue
            q_objects.append(ALL_QUESTIONS_DICT[q_num])
    if not q_objects:
        # デバッグ情報の表示
        now = datetime.datetime.now(datetime.timezone.utc)
        stq = st.session_state.get("short_term_review_queue", [])
        ready_reviews = sum(1 for item in stq if (lambda ra: not ra or ra <= now)(
            datetime.datetime.fromisoformat(item.get("ready_at")) if isinstance(item.get("ready_at"), str) 
            else item.get("ready_at", now)
        ))
        pending_new = len(st.session_state.get("main_queue", []))
        
        if ready_reviews + pending_new > 0:
            st.warning(f"📊 **学習キュー状況**: 復習待ち{ready_reviews}問、新規待ち{pending_new}問")
            st.info("学習を開始するには、サイドバーで「🚀 今日の学習を開始する」をクリックしてください。")
        else:
            st.success("🎉 このセッションの学習はすべて完了しました！")
            st.balloons()
        st.stop()

    first_q = q_objects[0]
    group_id = first_q['number']
    is_checked = st.session_state.get(f"checked_{group_id}", False)
    case_data = CASES.get(first_q.get('case_id')) if first_q.get('case_id') else None

    # 問題タイプの表示（復習か新規か）
    cards = st.session_state.get("cards", {})
    if group_id in cards and cards[group_id].get('n', 0) > 0:
        study_count = cards[group_id].get('n', 0)
        if study_count == 1:
            st.info(f"🔄 **復習問題** - この問題は{study_count}回目の学習です")
        else:
            st.info(f"🔄 **復習問題** - この問題は{study_count}回目の学習です")
    else:
        st.info("🆕 **新規問題** - 初回の学習です")

    if case_data:
        st.info(f"【連問】この症例には{len(q_objects)}問の問題が含まれています。")
        if 'scenario_text' in case_data:
            st.markdown(case_data['scenario_text'])

    if not is_checked:
        with st.form(key=f"answer_form_{group_id}"):
            for q in q_objects:
                st.markdown(f"#### {q['number']}")
                st.markdown(chem_latex(q.get('question', '')))
                
                if is_ordering_question(q):
                    # --- 修正箇所①：並び替え問題の選択肢表示 ---
                    # 選択肢をシャッフルし、A, B, C...のラベルを付けて表示
                    shuffled_choices, _ = get_shuffled_choices(q)
                    st.markdown("##### 選択肢")
                    for i, choice_text in enumerate(shuffled_choices):
                        st.markdown(f"**{chr(65 + i)}.** {choice_text}")
                    # 解答例を固定のプレースホルダーに変更
                    st.text_input("解答を順番に入力してください（例: ABCDE）", key=f"order_input_{q['number']}")
                elif "choices" in q and q["choices"]:
                    shuffled_choices, _ = get_shuffled_choices(q)
                    user_selection_key = f"user_selection_{q['number']}"
                    if user_selection_key not in st.session_state:
                        st.session_state[user_selection_key] = [False] * len(shuffled_choices)
                    for i, choice_item in enumerate(shuffled_choices):
                        if isinstance(choice_item, dict):
                            label = f"{chr(65 + i)}. {chem_latex(choice_item.get('text', str(choice_item)))}"
                        else:
                            label = f"{chr(65 + i)}. {chem_latex(str(choice_item))}"
                        checked = st.session_state[user_selection_key][i]
                        new_checked = st.checkbox(label, value=checked, key=f"user_selection_{q['number']}_{i}")
                        st.session_state[user_selection_key][i] = new_checked
                else:
                    st.text_input("回答を入力", key=f"free_input_{q['number']}")
            submitted_check = st.form_submit_button("回答をチェック", type="primary")
            # スキップボタンに追加のマークアップを提供
            st.markdown("""
            <style>
            /* スキップボタン専用スタイル */
            .stForm button:nth-of-type(2) {
                background-color: #4a5568 !important;
                color: #ffffff !important;
                border: 1px solid #718096 !important;
            }
            .stForm button:nth-of-type(2):hover {
                background-color: #718096 !important;
                color: #ffffff !important;
            }
            </style>
            """, unsafe_allow_html=True)
            skipped = st.form_submit_button("スキップ", type="secondary")
            if submitted_check:
                # セッション維持：ユーザー活動検知
                if not ensure_valid_session():
                    st.warning("セッションが期限切れです。再度ログインしてください。")
                    st.rerun()
                    
                for q in q_objects:
                    answer_str = (q.get("answer") or "").strip()

                    # 補助: 文字列 → インデックス列（A=0, B=1,...）。全角英字・区切り文字も許容
                    def _letters_to_indices(s: str, num_choices: int, uniq=False, sort=False):
                        if not isinstance(s, str):
                            return []
                        # 全角英大文字→半角, 非英字は除去
                        table = str.maketrans({chr(0xFF21 + i): chr(0x41 + i) for i in range(26)})  # Ａ..Ｚ→A..Z
                        s = s.translate(table)
                        # よくある区切り: / , ・ 、 ， と → - > スペース などを全部削除して A..Z のみ残す
                        s = re.sub(r"[^A-Za-z]", "", s).upper()
                        idxs = [ord(ch) - 65 for ch in s if 0 <= (ord(ch) - 65) < num_choices]
                        if uniq:
                            idxs = list(dict.fromkeys(idxs))
                        if sort:
                            idxs = sorted(idxs)
                        return idxs

                    # 並び替え問題
                    if is_ordering_question(q):
                        shuffle_indices = st.session_state.get(
                            f"shuffled_{q['number']}",
                            list(range(len(q.get("choices", []))))
                        )
                        n = len(q.get("choices", []))
                        user_raw = st.session_state.get(f"order_input_{q['number']}", "")

                        # 表示上の A,B,C...（=シャッフル後の並び）を元のインデックスへ戻す
                        disp_idxs = _letters_to_indices(user_raw, n)
                        if len(disp_idxs) != n:
                            is_correct = False
                            reason = "入力の文字数が選択肢数と一致しません。例: ABCDE"
                        else:
                            user_orig_order = [shuffle_indices[i] for i in disp_idxs]
                            correct_orig_order = _letters_to_indices(answer_str, n)
                            is_correct = (user_orig_order == correct_orig_order)
                            reason = ""

                        # 結果表示（正解シーケンスも見せる）
                        def _fmt_seq(idxs):
                            return " → ".join(chr(65 + i) for i in idxs)

                        if is_correct:
                            # 正解表示は削除（ユーザーリクエスト）
                            pass
                        else:
                            # 正解は元の並び基準。ユーザー入力は表示基準なので、見せるときは表示基準にも直す
                            # 正解（表示基準）に変換: 正解の各 original idx が shuffle 上で何番目かを逆写像で求める
                            inv = {orig: disp for disp, orig in enumerate(shuffle_indices)}
                            correct_disp = [_fmt_seq([inv[i] for i in _letters_to_indices(answer_str, n)])]
                            # 不正解表示は削除（ユーザーリクエスト）
                            pass

                        # 結果をセッション状態に保存（自己評価後にSM-2更新）
                        st.session_state.result_log[q["number"]] = is_correct

                    # 単一/複数選択（チェックボックス）
                    elif "choices" in q and q["choices"]:
                        shuffled_choices, shuffle_indices = get_shuffled_choices(q)
                        user_selection_key = f"user_selection_{q['number']}"
                        picks_disp = [
                            i for i, v in enumerate(st.session_state.get(user_selection_key, []))
                            if bool(v)
                        ]
                        picks_orig = sorted(shuffle_indices[i] for i in picks_disp)

                        n = len(q["choices"])
                        ans_orig = sorted(set(_letters_to_indices(answer_str, n)))

                        is_correct = (picks_orig == ans_orig)

                        # 結果表示
                        def _fmt_set(idxs):
                            return " / ".join(sorted(chr(65 + i) for i in idxs))

                        if is_correct:
                            # 正解表示は削除（ユーザーリクエスト）
                            pass
                        else:
                            # 不正解表示は削除（ユーザーリクエスト）
                            pass

                        # 結果をセッション状態に保存（自己評価後にSM-2更新）
                        st.session_state.result_log[q["number"]] = is_correct

                    # 自由入力
                    else:
                        user_ans = (st.session_state.get(f"free_input_{q['number']}", "") or "").strip()
                        def _norm(s: str) -> str:
                            s = str(s)
                            # 記号・空白を除いて小文字化（ざっくり一致）
                            return re.sub(r"\s+", "", s).lower()

                        is_correct = (_norm(user_ans) == _norm(answer_str))

                        if is_correct:
                            # 正解表示は削除（ユーザーリクエスト）
                            pass
                        else:
                            # 不正解表示は削除（ユーザーリクエスト）
                            pass

                        # 結果をセッション状態に保存（自己評価後にSM-2更新）
                        st.session_state.result_log[q["number"]] = is_correct

                # フォーム全体の後処理：解答結果を保存し、自己評価段階へ移行
                st.session_state[f"checked_{group_id}"] = True
                # 画面を再描画して自己評価フォームを表示
                st.rerun()
            if skipped:
                # セッション維持：ユーザー活動検知
                if not ensure_valid_session():
                    st.warning("セッションが期限切れです。再度ログインしてください。")
                    st.rerun()
                    
                # スキップ：現在のグループを末尾へ戻して次へ
                st.session_state.main_queue = st.session_state.get("main_queue", [])
                st.session_state.main_queue.append(current_q_group)
                st.session_state.current_q_group = []
                st.rerun()
    else:
        for q in q_objects:
            st.markdown(f"#### {q['number']}")
            st.markdown(chem_latex(q.get('question', '')))
            is_correct = st.session_state.result_log.get(q['number'], False)
            if is_ordering_question(q):
                # --- 修正箇所③：並び替え問題の正解表示 ---
                # 正解を計算するためにシャッフル情報を取得
                shuffled_choices, shuffle_indices = get_shuffled_choices(q)

                # 正解を確認するために、シャッフルされた選択肢を再度表示
                st.markdown("##### 選択肢")
                for i, choice_text in enumerate(shuffled_choices):
                    st.markdown(f"**{chr(65 + i)}.** {choice_text}")

                st.text_input("あなたの解答", value=st.session_state.get(f"order_input_{q['number']}", ""), disabled=True)
                if is_correct:
                    st.markdown("<span style='font-size:1.5em; color:green;'>✓ 正解！</span>", unsafe_allow_html=True)
                else:
                    st.markdown("<span style='font-size:1.5em; color:red;'>× 不正解</span>", unsafe_allow_html=True)
                    # シャッフル後の正しい答えを計算して表示
                    correct_shuffled_answer_str = ""
                    try:
                        reverse_shuffle_map = {orig_idx: new_idx for new_idx, orig_idx in enumerate(shuffle_indices)}
                        original_answer_str = q.get("answer", "").strip().upper()
                        original_indices_correct_order = [ord(c) - 65 for c in original_answer_str]
                        shuffled_correct_indices = [reverse_shuffle_map[orig_idx] for orig_idx in original_indices_correct_order]
                        correct_shuffled_answer_str = "".join([chr(65 + i) for i in shuffled_correct_indices])
                    except (KeyError, TypeError, ValueError):
                        correct_shuffled_answer_str = "エラー"
                    st.markdown(f"<span style='color:blue;'>正解: {correct_shuffled_answer_str}</span>", unsafe_allow_html=True)

            elif "choices" in q and q["choices"]:
                shuffled_choices, shuffle_indices = get_shuffled_choices(q)
                answer_str = q.get("answer", "")
                if "/" in answer_str or "／" in answer_str:
                    correct_letters = answer_str.replace("／", "/").split("/")
                else:
                    correct_letters = list(answer_str)
                correct_indices = [ord(l) - 65 for l in correct_letters if l.isalpha()]
                correct_labels = [chr(65 + shuffle_indices.index(i)) for i in correct_indices if i < len(shuffle_indices) and i in shuffle_indices]
                for i, choice_item in enumerate(shuffled_choices):
                    if isinstance(choice_item, dict):
                        label = f"{chr(65 + i)}. {chem_latex(choice_item.get('text', str(choice_item)))}"
                    else:
                        label = f"{chr(65 + i)}. {chem_latex(str(choice_item))}"
                    user_selection_key = f"user_selection_{q['number']}"
                    is_selected = st.session_state.get(user_selection_key, [False]*len(shuffled_choices))[i]
                    st.checkbox(label, value=is_selected, disabled=True, key=f"user_selection_{q['number']}_{i}")
                
                # 自己評価フォーム内での正解/不正解表示（復活）
                is_correct = st.session_state.result_log.get(q["number"], False)
                if is_correct:
                    st.markdown("<span style='font-size:1.5em; color:green;'>✓ 正解！</span>", unsafe_allow_html=True)
                    # 複数解答の場合はその旨を表示
                    if "/" in answer_str or "／" in answer_str:
                        st.markdown(f"<span style='color:green;'>複数解答問題でした - 正解: {'・'.join(correct_labels)} （いずれも正解）</span>", unsafe_allow_html=True)
                else:
                    st.markdown("<span style='font-size:1.5em; color:red;'>× 不正解</span>", unsafe_allow_html=True)
                    # 複数解答の場合はその旨を表示
                    if "/" in answer_str or "／" in answer_str:
                        st.markdown(f"<span style='color:blue;'>正解: {'・'.join(correct_labels)} （複数解答問題 - いずれも正解）</span>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"<span style='color:blue;'>正解: {'・'.join(correct_labels)}</span>", unsafe_allow_html=True)
            else:
                st.text_input("あなたの解答", value=st.session_state.get(f"free_input_{q['number']}", ""), disabled=True)
                
                # 自己評価フォーム内での正解/不正解表示（復活）
                is_correct = st.session_state.result_log.get(q["number"], False)
                if is_correct:
                    st.markdown("<span style='font-size:1.5em; color:green;'>✓ 正解！</span>", unsafe_allow_html=True)
                else:
                    st.markdown("<span style='font-size:1.5em; color:red;'>× 不正解</span>", unsafe_allow_html=True)
                    st.markdown(f"<span style='color:blue;'>正解: {q.get('answer', '')}</span>", unsafe_allow_html=True)
        with st.form(key=f"eval_form_{group_id}"):
            st.markdown("#### この問題グループの自己評価")
            eval_map = {"もう一度": 1, "難しい": 2, "普通": 4, "簡単": 5}
            
            # グループ内の正解状況を判定してデフォルト選択を決定
            group_all_correct = all(st.session_state.result_log.get(q_num, False) for q_num in current_q_group)
            default_eval = "簡単" if group_all_correct else "もう一度"
            
            # デフォルト選択のindexを計算
            eval_keys = list(eval_map.keys())
            default_index = eval_keys.index(default_eval)
            
            selected_eval_label = st.radio("自己評価", eval_map.keys(), horizontal=True, label_visibility="collapsed", index=default_index)
            if st.form_submit_button("次の問題へ", type="primary"):
                # セッション維持：ユーザー活動検知
                if not ensure_valid_session():
                    st.warning("セッションが期限切れです。再度ログインしてください。")
                    st.rerun()
                    
                with st.spinner('学習記録を保存中...'):
                    quality = eval_map[selected_eval_label]
                    # ★ 評価送信の処理内（quality を決めた後）
                    next_group = get_next_q_group()
                    now_utc = datetime.datetime.now(datetime.timezone.utc)

                    has_hisshu = any(is_hisshu(qn) for qn in current_q_group)

                    for q_num_str in current_q_group:
                        card = st.session_state.cards.get(q_num_str, {})
                        st.session_state.cards[q_num_str] = sm2_update_with_policy(card, quality, q_num_str, now=now_utc)

                    # ★ 短期復習キュー積み直し
                    if quality == 1:
                        enqueue_short_review(current_q_group, SHORT_REVIEW_COOLDOWN_MIN_Q1)
                    elif quality == 2 and has_hisshu:
                        enqueue_short_review(current_q_group, SHORT_REVIEW_COOLDOWN_MIN_Q2_HISSHU)
                    
                    # 間違えた問題を短期復習に追加
                    for q_num_str in current_q_group:
                        is_correct = st.session_state.result_log.get(q_num_str, False)
                        if not is_correct and quality >= 3:  # 間違えたが自己評価が高い場合のみ
                            minutes = SHORT_REVIEW_COOLDOWN_MIN_Q2_HISSHU if (is_hisshu(q_num_str) or is_gakushi_hisshu(q_num_str)) else SHORT_REVIEW_COOLDOWN_MIN_Q1
                            enqueue_short_review([q_num_str], minutes)

                    uid = st.session_state.get("uid")  # UIDベース管理
                    save_user_data(uid, st.session_state)  # UIDを使用
                    st.session_state.current_q_group = next_group
                for key in list(st.session_state.keys()):
                    if key.startswith(("checked_", "user_selection_", "shuffled_", "free_input_", "order_input_")):
                        del st.session_state[key]
                st.rerun()

    display_images = []
    image_keys = ['image_urls', 'image_paths']

    # case_data の画像処理
    if case_data:
        for key in image_keys:
            image_list = case_data.get(key)
            if image_list:  # 値がNoneや空リストでないことを確認
                display_images.extend(image_list)

    # first_q の画像処理
    if first_q:
        for key in image_keys:
            image_list = first_q.get(key)
            if image_list:  # 値がNoneや空リストでないことを確認
                display_images.extend(image_list)

    if display_images:
        print(f"[DEBUG] 画像表示処理開始: {len(display_images)} 個の画像パス")
        
        # Firebase Storageのファイル構造を確認
        print(f"[DEBUG] Firebase Storage構造確認開始")
        list_storage_files("gakushi/", 20)
        list_storage_files("", 20)  # ルートディレクトリ
        
        # 重複を除去して、万が一同じパスが複数あってもエラーを防ぐ
        unique_images = list(dict.fromkeys(display_images))
        print(f"[DEBUG] 重複除去後: {len(unique_images)} 個の画像パス")
        for i, path in enumerate(unique_images):
            print(f"[DEBUG] 画像パス {i+1}: {path}")
        
        secure_urls = []
        for i, path in enumerate(unique_images):
            if path:
                url = get_secure_image_url(path)
                if url:
                    secure_urls.append(url)
                    print(f"[DEBUG] URL生成成功 {i+1}: {url[:100]}...")
                else:
                    print(f"[DEBUG] URL生成失敗 {i+1}: {path}")
        
        print(f"[DEBUG] 署名付きURL生成完了: {len(secure_urls)} 個のURL")
        
        if secure_urls:
            print(f"[DEBUG] st.image()呼び出し開始")
            try:
                # 各画像を個別に表示してエラーを特定
                for i, url in enumerate(secure_urls):
                    try:
                        print(f"[DEBUG] 画像 {i+1} 表示開始: {url[:50]}...")
                        
                        # 方法1: 通常のst.image()
                        try:
                            st.image(url, use_container_width=True, width=400)
                            print(f"[DEBUG] 画像 {i+1} st.image()表示成功")
                        except Exception as st_img_err:
                            print(f"[DEBUG] st.image()失敗、HTMLで試行: {st_img_err}")
                            
                            # 方法2: HTMLマークダウンで直接表示
                            try:
                                st.markdown(
                                    f'<img src="{url}" style="max-width: 100%; height: auto;" alt="Question Image {i+1}">',
                                    unsafe_allow_html=True
                                )
                                print(f"[DEBUG] 画像 {i+1} HTML表示成功")
                            except Exception as html_err:
                                print(f"[ERROR] HTML表示も失敗: {html_err}")
                                st.error(f"画像 {i+1} 表示エラー (両方法失敗): st.image={st_img_err}, HTML={html_err}")
                                continue
                        
                    except Exception as img_err:
                        print(f"[ERROR] 画像 {i+1} 表示失敗: {img_err}")
                        st.error(f"画像 {i+1} 表示エラー: {img_err}")
                        # エラーが出ても続行して他の画像を試す
                        continue
                print(f"[DEBUG] st.image()呼び出し完了")
            except Exception as e:
                print(f"[ERROR] st.image()でエラー: {e}")
                st.error(f"画像表示エラー: {e}")
        else:
            print(f"[DEBUG] 表示可能な画像URL無し")
            st.warning("画像を読み込めませんでした")

# --- メイン ---
# 自動ログインを試行（高速化版・1回限り）
if not st.session_state.get("user_logged_in") and not st.session_state.get("auto_login_attempted"):
    import time
    auto_login_start = time.time()
    st.session_state.auto_login_attempted = True  # 重複実行防止
    
    if try_auto_login_from_cookie():
        print(f"[DEBUG] 自動ログイン成功: {time.time() - auto_login_start:.3f}s")
        st.rerun()
    print(f"[DEBUG] 自動ログイン処理: {time.time() - auto_login_start:.3f}s")

if not st.session_state.get("user_logged_in") or not ensure_valid_session():
    # セッションが無効の場合はログイン情報をクリア
    if not ensure_valid_session():
        for k in ["user_logged_in", "id_token", "refresh_token", "name", "username", "email", "uid", "user_data_loaded", "token_timestamp"]:
            if k in st.session_state:
                del st.session_state[k]
    
    # ログイン画面でのみタイトル表示
    st.title("🦷 歯科国家試験AI対策アプリ")
    st.markdown("### 🔐 ログイン／新規登録")
    tab_login, tab_signup, tab_reset = st.tabs(["ログイン", "新規登録", "パスワードリセット"])
    with tab_login:
        login_email = st.text_input("メールアドレス", key="login_email", autocomplete="email")
        login_password = st.text_input("パスワード", type="password", key="login_password")
        remember_me = st.checkbox("ログイン状態を保存する", value=True, help="このブラウザで次回から自動ログインします。")
        
        # ログイン処理中の場合はボタンを無効化
        login_disabled = st.session_state.get("login_in_progress", False)
        if login_disabled:
            st.info("ログイン処理中です。しばらくお待ちください...")
        
        if st.button("ログイン", key="login_btn", disabled=login_disabled):
            import time
            start_time = time.time()
            print(f"[DEBUG] ログインボタンが押されました - Email: {login_email}")
            
            # 入力チェック
            if not login_email or not login_password:
                st.error("メールアドレスとパスワードを入力してください。")
                st.stop()
            
            # Firebase認証（シンプル化）
            with st.spinner('認証中...'):
                result = firebase_signin(login_email, login_password)
                auth_time = time.time() - start_time
                print(f"[DEBUG] Firebase認証レスポンス取得: {auth_time:.2f}秒")
            
            if "idToken" in result:
                print(f"[DEBUG] 認証成功 - idToken取得")
                # 高速セッション更新（emailベース管理）
                st.session_state.update({
                    "name": login_email.split("@")[0],
                    "username": login_email,  # emailをプライマリIDとして使用
                    "email": login_email,
                    "uid": result.get("localId"),
                    "id_token": result["idToken"],
                    "refresh_token": result.get("refreshToken", ""),
                    "token_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "user_logged_in": login_email,  # emailをログイン状態の識別子として使用
                    "login_in_progress": False  # ログイン完了
                })
                
                # Cookie保存（remember me・emailベース）
                cookies = get_cookies()  # 安全にCookie取得
                if remember_me and cookies is not None and result.get("refreshToken"):
                    cookie_data = {
                        "refresh_token": result["refreshToken"],
                        "uid": result.get("localId"),
                        "email": login_email
                    }
                    safe_save_cookies(cookies, cookie_data)
                
                st.success("ログイン成功！")
                print(f"[DEBUG] ログイン処理完了")
                st.rerun()
                    
                #     perm_start = time.time()
                #     migrate_permission_if_needed(st.session_state["uid"], login_email)
                #     perm_time = time.time() - perm_start
                #     st.write(f"権限データ移行完了: {perm_time:.2f}秒")
                
                # Remember me: クッキー保存（emailベース）
                if remember_me and cookies is not None and st.session_state.get("refresh_token"):
                    cookie_start = time.time()
                    cookie_data = {
                        "refresh_token": st.session_state["refresh_token"],
                        "uid": st.session_state["uid"],
                        "email": login_email
                    }
                    if safe_save_cookies(cookies, cookie_data):
                        cookie_time = time.time() - cookie_start
                        st.write(f"クッキー保存完了: {cookie_time:.3f}秒")
                        print(f"[DEBUG] クッキー保存成功: {cookie_time:.3f}秒")
                else:
                    if not remember_me:
                        print("[DEBUG] クッキー保存スキップ - remember_meがFalse")
                    elif not cookies:
                        print("[DEBUG] クッキー保存スキップ - cookiesが無効")
            else:
                print(f"[DEBUG] 認証失敗 - レスポンス: {result}")
                st.session_state["login_in_progress"] = False  # ログイン失敗時もフラグをクリア
                st.error("ログインに失敗しました。メールアドレスまたはパスワードを確認してください。")
                if "error" in result:
                    error_msg = result['error'].get('message', 'Unknown error')
                    st.error(f"エラー詳細: {error_msg}")
                    # 具体的なエラーメッセージを表示
                    if "INVALID_EMAIL" in error_msg:
                        st.error("メールアドレスの形式が正しくありません。")
                    elif "EMAIL_NOT_FOUND" in error_msg:
                        st.error("このメールアドレスは登録されていません。")
                    elif "INVALID_PASSWORD" in error_msg:
                        st.error("パスワードが間違っています。")
                    elif "USER_DISABLED" in error_msg:
                        st.error("このアカウントは無効化されています。")
    with tab_signup:
        # 新規登録の一時停止フラグ（必要に応じて True に変更）
        SIGNUP_TEMPORARILY_DISABLED = True
        
        if SIGNUP_TEMPORARILY_DISABLED:
            st.warning("🚧 新規登録は一時的に停止中です")
            st.info("既存のアカウントをお持ちの方は「ログイン」タブからログインしてください。")
        else:
            signup_email = st.text_input("メールアドレス", key="signup_email")
            signup_password = st.text_input("パスワード（6文字以上）", type="password", key="signup_password")
            if st.button("新規登録", key="signup_btn"):
                result = firebase_signup(signup_email, signup_password)
                if "idToken" in result:
                    st.success("新規登録に成功しました。ログインしてください。")
                else:
                    st.error("新規登録に失敗しました。メールアドレスが既に使われているか、パスワードが短すぎます。")
        
        # 以下はバックアップ用のコメントアウトコード（削除しないでください）
        # st.warning("🚧 新規登録は一時的に停止中です")
        # st.info("既存のアカウントをお持ちの方は「ログイン」タブからログインしてください。")
        # signup_email = st.text_input("メールアドレス", key="signup_email")
        # signup_password = st.text_input("パスワード（6文字以上）", type="password", key="signup_password")
        # if st.button("新規登録", key="signup_btn"):
        #     result = firebase_signup(signup_email, signup_password)
        #     if "idToken" in result:
        #         st.success("新規登録に成功しました。ログインしてください。")
        #     else:
        #         st.error("新規登録に失敗しました。メールアドレスが既に使われているか、パスワードが短すぎます。")
    
    with tab_reset:
        st.markdown("#### 🔑 パスワードをリセット")
        st.info("登録済みのメールアドレスを入力すると、パスワードリセット用のリンクをお送りします。")
        
        reset_email = st.text_input("メールアドレス", key="reset_email", autocomplete="email")
        
        # パスワードリセット処理中のフラグ
        reset_disabled = st.session_state.get("reset_in_progress", False)
        if reset_disabled:
            st.info("パスワードリセットメールを送信中です。しばらくお待ちください...")
        
        if st.button("パスワードリセットメールを送信", key="reset_btn", disabled=reset_disabled, type="primary"):
            if not reset_email:
                st.error("メールアドレスを入力してください。")
            else:
                # リセット処理中フラグを設定
                st.session_state["reset_in_progress"] = True
                
                with st.spinner('パスワードリセットメールを送信中...'):
                    result = firebase_reset_password(reset_email)
                
                # 処理完了後フラグをクリア
                st.session_state["reset_in_progress"] = False
                
                if result["success"]:
                    st.success("✅ " + result["message"])
                    st.info("📧 メールボックスをご確認ください。メールが届かない場合は、迷惑メールフォルダもご確認ください。")
                else:
                    st.error("❌ " + result["message"])
        
        st.markdown("---")
        st.markdown("**💡 ヒント:**")
        st.markdown("- パスワードリセット後は、新しいパスワードでログインしてください")
        st.markdown("- メールが届かない場合は、迷惑メールフォルダを確認してください")
        st.markdown("- アカウントに関する問題がある場合は、管理者にお問い合わせください")
    
    st.stop()
else:
    import time
    main_start = time.time()
    
    # セッション維持機能：ユーザー活動検知による自動トークンリフレッシュ
    if not ensure_valid_session():
        st.warning("セッションが無効になりました。再度ログインしてください。")
        # セッション情報をクリア
        for k in ["user_logged_in", "id_token", "refresh_token", "name", "username", "email", "uid", "user_data_loaded", "token_timestamp"]:
            if k in st.session_state:
                del st.session_state[k]
        st.rerun()
    
    name = st.session_state.get("name")
    username = st.session_state.get("username")
    uid = st.session_state.get("uid")  # ★ 追加
    
    init_check_time = time.time() - main_start
    
    if not name or not username:
        st.warning("ログイン情報が見つかりません。再度ログインしてください。")
        st.stop()
        
    if "user_data_loaded" not in st.session_state:
        # ログイン直後は軽量版でクイックロード（UIDベース）
        user_data_start = time.time()
        uid = st.session_state.get("uid")  # UIDを主キーとして使用
        user_data = load_user_data_minimal(uid)  # UIDを使用
        user_data_time = time.time() - user_data_start
        
        session_update_start = time.time()
        # 最小限のデータでセッション初期化
        # ▼ 修正：戻り値を反映（空で潰さない）
        st.session_state.cards = user_data.get("cards", {})  # ← 修正
        st.session_state.main_queue = []
        st.session_state.short_term_review_queue = []
        st.session_state.current_q_group = []
        st.session_state.result_log = {}
        if "new_cards_per_day" not in st.session_state:
            st.session_state["new_cards_per_day"] = user_data.get("new_cards_per_day", 10)
        st.session_state.user_data_loaded = True
        session_update_time = time.time() - session_update_start
        
        total_init_time = time.time() - main_start
        print(f"[DEBUG] メイン初期化(軽量) - 初期チェック: {init_check_time:.3f}s, 軽量データ読込: {user_data_time:.3f}s, セッション更新: {session_update_time:.3f}s, 合計: {total_init_time:.3f}s")
        
    if "result_log" not in st.session_state:
        st.session_state.result_log = {}

    # ---------- Sidebar ----------
    with st.sidebar:
        # セッション状態の表示
        name = st.session_state.get("name", "ユーザー")
        token_timestamp = st.session_state.get("token_timestamp")
        if token_timestamp:
            token_time = datetime.datetime.fromisoformat(token_timestamp)
            elapsed = datetime.datetime.now(datetime.timezone.utc) - token_time
            remaining_minutes = max(0, 30 - int(elapsed.total_seconds() / 60))
            if remaining_minutes > 5:
                st.success(f"{name} としてログイン中 (セッション: あと{remaining_minutes}分)")
            else:
                st.warning(f"{name} としてログイン中 (セッション: まもなく更新)")
        else:
            st.success(f"{name} としてログイン中")

        # 前回セッション復帰選択UI
        if st.session_state.get("has_previous_session") and not st.session_state.get("session_choice_made"):
            st.divider()
            st.markdown("### 🔄 前回の続きから")
            previous_type = st.session_state.get("previous_session_type", "演習")
            st.info(f"前回の {previous_type} セッションが見つかりました")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("続きから", key="continue_session", type="primary"):
                    st.session_state["session_choice_made"] = True
                    st.session_state["continue_previous"] = True
                    st.rerun()
            with col2:
                if st.button("新規開始", key="new_session"):
                    st.session_state["session_choice_made"] = True
                    st.session_state["continue_previous"] = False
                    # 前回のセッション情報をクリア
                    st.session_state.pop("has_previous_session", None)
                    st.session_state.pop("previous_session_type", None)
                    # アクティブセッション状態もクリア
                    st.session_state.pop("current_q_group", None)
                    st.session_state.pop("main_queue", None)
                    st.session_state.pop("current_question_index", None)
                    st.session_state.pop("total_questions", None)
                    print("[DEBUG] 新規セッション開始 - 前回の状態をクリア")
                    st.rerun()

        # ページ選択（完成版）
        page = st.radio(
            "ページ選択",
            ["演習", "検索・進捗"],
            index=0,
            key="page_select"
        )

        st.divider()

        # ページに応じてサイドバー内容を動的に変化
        if page == "演習":
            # --- 演習ページのサイドバー ---
            st.markdown("### 🎓 学習ハブ")
            
            # 学習モード選択
            learning_mode = st.radio(
                "学習モード",
                ['おまかせ学習（推奨）', '自由演習（分野・回数指定）'],
                key="learning_mode"
            )
            
            st.divider()
            
            if learning_mode == 'おまかせ学習（推奨）':
                # 学習セッション初期化中の場合の処理
                if st.session_state.get("initializing_study", False):
                    st.markdown("#### 📅 本日の学習目標")
                    st.info("🔄 学習セッションを準備中...")
                    # 初期化中は他の表示を全て停止
                    st.stop()
                else:
                    # Anki風の日次目標表示
                    st.markdown("#### 📅 本日の学習目標")
                    today = datetime.datetime.now(datetime.timezone.utc).date()
                    today_str = today.strftime('%Y-%m-%d')
                    
                    # 本日の復習対象カード数を計算
                    review_count = 0
                    cards = st.session_state.get("cards", {})
                
                    for card in cards.values():
                        if 'next_review' in card:
                            next_review = card['next_review']
                            if isinstance(next_review, str):
                                try:
                                    next_review_date = datetime.datetime.fromisoformat(next_review).date()
                                    if next_review_date <= today:
                                        review_count += 1
                                except:
                                    pass
                            elif isinstance(next_review, datetime.datetime):
                                if next_review.date() <= today:
                                    review_count += 1
                            elif isinstance(next_review, datetime.date):
                                if next_review <= today:
                                    review_count += 1
                    
                    # 本日の学習完了数を計算（重複カウント防止強化版）
                    today_reviews_done = 0
                    today_new_done = 0
                    processed_cards = set()  # 重複カウント防止
                    
                    try:
                        for q_num, card in cards.items():
                            if not isinstance(card, dict) or q_num in processed_cards:
                                continue
                                
                            history = card.get('history', [])
                            if not history:
                                continue
                            
                            # 本日の学習履歴があるかチェック
                            has_today_session = False
                            for review in history:
                                if isinstance(review, dict):
                                    review_date = review.get('timestamp', '')
                                    if isinstance(review_date, str) and review_date.startswith(today_str):
                                        has_today_session = True
                                        break
                            
                            if has_today_session:
                                processed_cards.add(q_num)  # 処理済みマーク
                                
                                # 最初の学習が本日かどうかで新規/復習を判定
                                first_review = history[0] if history else {}
                                first_date = first_review.get('timestamp', '') if isinstance(first_review, dict) else ''
                                
                                if isinstance(first_date, str) and first_date.startswith(today_str):
                                    # 本日初回学習（新規）
                                    today_new_done += 1
                                else:
                                    # 復習
                                    today_reviews_done += 1
                    except Exception as e:
                        # エラーが発生した場合は0で初期化
                        today_reviews_done = 0
                        today_new_done = 0
                    
                    # 新規学習目標数（安全な取得）
                    new_target = st.session_state.get("new_cards_per_day", 10)
                    if not isinstance(new_target, int):
                        new_target = 10
                    
                    # 残り目標数を計算（安全な値チェック付き）
                    review_remaining = max(0, review_count - today_reviews_done) if isinstance(review_count, int) and isinstance(today_reviews_done, int) else 0
                    new_remaining = max(0, new_target - today_new_done) if isinstance(new_target, int) and isinstance(today_new_done, int) else 0
                    
                    # 本日の進捗サマリー
                    total_done = today_reviews_done + today_new_done
                    daily_goal = review_count + new_target
                    progress_rate = min(100, (total_done / daily_goal * 100)) if daily_goal > 0 else 0
                    
                    # メイン進捗表示（縦並び）
                    st.metric(
                        label="本日の学習",
                        value=f"{total_done}枚",
                        help=f"目標: {daily_goal}枚 (達成率: {progress_rate:.0f}%)"
                    )
                    
                    if total_done >= daily_goal:
                        st.metric(
                            label="達成率",
                            value="100%",
                            help="目標達成おめでとうございます！"
                        )
                    else:
                        st.metric(
                            label="達成率",
                            value=f"{progress_rate:.0f}%",
                            help=f"あと{daily_goal - total_done}枚で目標達成"
                        )
                    
                    remaining_total = review_remaining + new_remaining
                    if remaining_total > 0:
                        st.metric(
                            label="残り目標",
                            value=f"{remaining_total}枚",
                            help="本日の残り学習目標数"
                        )
                    else:
                        st.metric(
                            label="✅ 完了",
                            value="目標達成",
                            help="本日の学習目標をすべて達成しました"
                        )
                    
                    st.markdown("---")
                    
                    # 詳細進捗表示（縦並び）
                    if review_remaining > 0:
                        st.metric(
                            label="復習",
                            value=f"{review_remaining}枚",
                            help=f"復習対象: {review_count}枚 / 完了: {today_reviews_done}枚"
                        )
                    else:
                        st.metric(
                            label="復習",
                            value="完了 ✅",
                            help=f"本日の復習: {today_reviews_done}枚完了"
                        )
                    
                    if new_remaining > 0:
                        st.metric(
                            label="新規",
                            value=f"{new_remaining}枚",
                            help=f"新規目標: {new_target}枚 / 完了: {today_new_done}枚"
                        )
                    else:
                        st.metric(
                            label="新規",
                            value="完了 ✅",
                            help=f"本日の新規学習: {today_new_done}枚完了"
                        )
                    
                    # 学習開始ボタン
                    if st.button("🚀 今日の学習を開始する", type="primary", key="start_today_study"):
                        # セッション復帰時は既存キューを優先
                        if st.session_state.get("continue_previous") or st.session_state.get("main_queue"):
                            st.info("前回のセッションを継続します")
                        else:
                            # セッション維持：ユーザー活動検知
                            if not ensure_valid_session():
                                st.warning("セッションが期限切れです。再度ログインしてください。")
                                st.rerun()
                            
                            # 学習開始中フラグを設定
                            st.session_state["initializing_study"] = True
                            
                            with st.spinner("学習セッションを準備中..."):
                                # 復習カードをメインキューに追加
                                grouped_queue = []
                                
                                # 復習カードの追加
                                for q_num, card in cards.items():
                                    if 'next_review' in card:
                                        next_review = card['next_review']
                                        should_review = False
                                        
                                        if isinstance(next_review, str):
                                            try:
                                                next_review_date = datetime.datetime.fromisoformat(next_review).date()
                                                should_review = next_review_date <= today
                                            except:
                                                pass
                                        elif isinstance(next_review, datetime.datetime):
                                            should_review = next_review.date() <= today
                                        elif isinstance(next_review, datetime.date):
                                            should_review = next_review <= today
                                        
                                        if should_review:
                                            grouped_queue.append([q_num])
                                
                                # 新規カードの追加
                                recent_ids = list(st.session_state.get("result_log", {}).keys())[-15:]
                                uid = st.session_state.get("uid")
                                has_gakushi_permission = check_gakushi_permission(uid)
                                
                                if has_gakushi_permission:
                                    available_questions = ALL_QUESTIONS
                                else:
                                    available_questions = [q for q in ALL_QUESTIONS if not q.get("number", "").startswith("G")]
                                
                                pick_ids = pick_new_cards_for_today(
                                    available_questions,
                                    st.session_state.get("cards", {}),
                                    N=new_target,
                                    recent_qids=recent_ids
                                )
                                
                                for qid in pick_ids:
                                    grouped_queue.append([qid])
                                    if qid not in st.session_state.cards:
                                        st.session_state.cards[qid] = {}
                            
                                
                                if grouped_queue:
                                    st.session_state.main_queue = grouped_queue
                                    st.session_state.short_term_review_queue = []
                                    st.session_state.current_q_group = []
                                    
                                    # 一時状態をクリア
                                    for k in list(st.session_state.keys()):
                                        if k.startswith(("checked_", "user_selection_", "shuffled_", "free_input_", "order_input_")):
                                            del st.session_state[k]
                                    
                                    save_user_data(st.session_state.get("uid"), st.session_state)
                                    st.session_state["initializing_study"] = False
                                    st.success(f"今日の学習を開始します！（{len(grouped_queue)}問）")
                                    st.rerun()
                                else:
                                    st.session_state["initializing_study"] = False
                                    st.info("今日の学習対象がありません。")
            
            else:
                # 自由演習モードのUI
                st.markdown("#### 🎯 自由演習設定")
                
                # 以前の選択UIを復活
                uid = st.session_state.get("uid")
                has_gakushi_permission = check_gakushi_permission(uid)
                mode_choices = ["回数別", "科目別", "必修問題のみ", "キーワード検索"]
                mode = st.radio("出題形式を選択", mode_choices, key="free_mode_radio")

                # 対象（国試/学士）セレクタ
                if has_gakushi_permission:
                    target_exam = st.radio("対象", ["国試", "学士"], key="free_target_exam", horizontal=True)
                else:
                    target_exam = "国試"
                
                questions_to_load = []

                if mode == "回数別":
                    if target_exam == "国試":
                        selected_exam_num = st.selectbox("回数", ALL_EXAM_NUMBERS, key="free_exam_num")
                        if selected_exam_num:
                            available_sections = sorted([s[-1] for s in ALL_EXAM_SESSIONS if s.startswith(selected_exam_num)])
                            selected_section_char = st.selectbox("領域", available_sections, key="free_section")
                            if selected_section_char:
                                selected_session = f"{selected_exam_num}{selected_section_char}"
                                questions_to_load = [q for q in ALL_QUESTIONS if q.get("number", "").startswith(selected_session)]
                    else:
                        g_years, g_sessions_map, g_areas_map, _ = build_gakushi_indices_with_sessions(ALL_QUESTIONS)
                        if g_years:
                            g_year = st.selectbox("年度", g_years, key="free_g_year")
                            if g_year:
                                sessions = g_sessions_map.get(g_year, [])
                                if sessions:
                                    g_session = st.selectbox("回数", sessions, key="free_g_session")
                                    if g_session:
                                        areas = g_areas_map.get(g_year, {}).get(g_session, ["A", "B", "C", "D"])
                                        g_area = st.selectbox("領域", areas, key="free_g_area")
                                        if g_area:
                                            questions_to_load = filter_gakushi_by_year_session_area(ALL_QUESTIONS, g_year, g_session, g_area)

                elif mode == "科目別":
                    if target_exam == "国試":
                        KISO_SUBJECTS = ["解剖学", "歯科理工学", "組織学", "生理学", "病理学", "薬理学", "微生物学・免疫学", "衛生学", "発生学・加齢老年学", "生化学"]
                        RINSHOU_SUBJECTS = ["保存修復学", "歯周病学", "歯内治療学", "クラウンブリッジ学", "部分床義歯学", "全部床義歯学", "インプラント学", "口腔外科学", "歯科放射線学", "歯科麻酔学", "矯正歯科学", "小児歯科学"]
                        group = st.radio("科目グループ", ["基礎系科目", "臨床系科目"], key="free_subject_group")
                        subjects_to_display = KISO_SUBJECTS if group == "基礎系科目" else RINSHOU_SUBJECTS
                        available_subjects = [s for s in ALL_SUBJECTS if s in subjects_to_display]
                        selected_subject = st.selectbox("科目", available_subjects, key="free_subject")
                        if selected_subject:
                            questions_to_load = [q for q in ALL_QUESTIONS if q.get("subject") == selected_subject and not str(q.get("number","")).startswith("G")]
                    else:
                        _, _, _, g_subjects = build_gakushi_indices_with_sessions(ALL_QUESTIONS)
                        if g_subjects:
                            selected_subject = st.selectbox("科目", g_subjects, key="free_g_subject")
                            if selected_subject:
                                questions_to_load = [q for q in ALL_QUESTIONS if str(q.get("number","")).startswith("G") and (q.get("subject") == selected_subject)]

                elif mode == "必修問題のみ":
                    if target_exam == "国試":
                        questions_to_load = [q for q in ALL_QUESTIONS if q.get("number") in HISSHU_Q_NUMBERS_SET]
                    else:
                        questions_to_load = [q for q in ALL_QUESTIONS if q.get("number") in GAKUSHI_HISSHU_Q_NUMBERS_SET]

                elif mode == "キーワード検索":
                    search_keyword = st.text_input("キーワード", placeholder="例: インプラント、根管治療", key="free_keyword")
                    if search_keyword.strip():
                        gakushi_only = (target_exam == "学士")
                        keyword_results = search_questions_by_keyword(
                            search_keyword.strip(),
                            gakushi_only=gakushi_only,
                            has_gakushi_permission=has_gakushi_permission
                        )
                        questions_to_load = keyword_results if keyword_results else []

                # 出題順
                order_mode = st.selectbox("出題順", ["順番通り", "シャッフル"], key="free_order")
                if order_mode == "シャッフル" and questions_to_load:
                    import random
                    questions_to_load = questions_to_load.copy()
                    random.shuffle(questions_to_load)
                elif questions_to_load:
                    try:
                        questions_to_load = sorted(questions_to_load, key=get_natural_sort_key)
                    except Exception:
                        pass

                # 学習開始ボタン
                if st.button("🎯 この条件で演習を開始", type="primary", key="start_free_study"):
                    # セッション維持：ユーザー活動検知
                    if not ensure_valid_session():
                        st.warning("セッションが期限切れです。再度ログインしてください。")
                        st.rerun()
                        
                    if not questions_to_load:
                        st.warning("該当する問題がありません。")
                    else:
                        # 権限フィルタリング
                        filtered_questions = []
                        for q in questions_to_load:
                            question_number = q.get('number', '')
                            if question_number.startswith("G") and not has_gakushi_permission:
                                continue
                            filtered_questions.append(q)
                        
                        if not filtered_questions:
                            st.warning("権限のある問題が見つかりませんでした。")
                        else:
                            # グループ化
                            grouped_queue = []
                            processed_q_nums = set()
                            for q in filtered_questions:
                                q_num = str(q['number'])
                                if q_num in processed_q_nums:
                                    continue
                                case_id = q.get('case_id')
                                if case_id and case_id in CASES:
                                    siblings = sorted([str(sq['number']) for sq in ALL_QUESTIONS if sq.get('case_id') == case_id])
                                    if siblings not in grouped_queue:
                                        grouped_queue.append(siblings)
                                    processed_q_nums.update(siblings)
                                else:
                                    grouped_queue.append([q_num])
                                    processed_q_nums.add(q_num)
                            
                            st.session_state.main_queue = grouped_queue
                            st.session_state.short_term_review_queue = []
                            st.session_state.current_q_group = []
                            
                            # カード初期化
                            if "cards" not in st.session_state:
                                st.session_state.cards = {}
                            for q in filtered_questions:
                                if q['number'] not in st.session_state.cards:
                                    st.session_state.cards[q['number']] = {}
                            
                            # 一時状態クリア
                            for key in list(st.session_state.keys()):
                                if key.startswith(("checked_", "user_selection_", "shuffled_", "free_input_", "order_input_")):
                                    del st.session_state[key]
                            
                            save_user_data(st.session_state.get("uid"), st.session_state)
                            st.success(f"演習を開始します！（{len(grouped_queue)}グループ）")
                            st.rerun()

            # 現在の学習キュー状況表示
            st.divider()
            st.markdown("#### 📋 学習キュー状況")
            
            # 短期復習の「準備完了」件数を表示
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            ready_short = 0
            for item in st.session_state.get("short_term_review_queue", []):
                ra = item.get("ready_at")
                if isinstance(ra, str):
                    try:
                        ra = datetime.datetime.fromisoformat(ra)
                    except Exception:
                        ra = now_utc
                if not ra or ra <= now_utc:
                    ready_short += 1

            st.write(f"メインキュー: **{len(st.session_state.get('main_queue', []))}** グループ")
            st.write(f"短期復習: **{ready_short}** グループ準備完了")

            # セッション初期化
            if st.button("🔄 セッションを初期化", key="reset_session"):
                st.session_state.current_q_group = []
                for k in list(st.session_state.keys()):
                    if k.startswith(("checked_", "user_selection_", "shuffled_", "free_input_", "order_input_")):
                        del st.session_state[k]
                st.info("セッションを初期化しました")
                st.rerun()

            # 学習記録セクション
            st.divider()
            st.markdown("#### 📈 学習記録")
            if st.session_state.cards and len(st.session_state.cards) > 0:
                quality_to_mark = {1: "×", 2: "△", 4: "◯", 5: "◎"}
                mark_to_label = {"◎": "簡単", "◯": "普通", "△": "難しい", "×": "もう一度"}
                evaluated_marks = [quality_to_mark.get(card.get('quality')) for card in st.session_state.cards.values() if card.get('quality')]
                total_evaluated = len(evaluated_marks)
                counter = Counter(evaluated_marks)
                
                with st.expander("自己評価の分布", expanded=True):
                    st.markdown(f"**合計評価数：{total_evaluated}問**")
                    for mark, label in mark_to_label.items():
                        count = counter.get(mark, 0)
                        percent = int(round(count / total_evaluated * 100)) if total_evaluated else 0
                        st.markdown(f"{mark} {label}：{count}問 ({percent}％)")
                
                with st.expander("最近の評価ログ", expanded=False):
                    cards_with_history = [(q_num, card) for q_num, card in st.session_state.cards.items() if card.get('history')]
                    sorted_cards = sorted(cards_with_history, key=lambda item: item[1]['history'][-1]['timestamp'], reverse=True)
                    for q_num, card in sorted_cards[:10]:
                        last_history = card['history'][-1]
                        last_eval_mark = quality_to_mark.get(last_history.get('quality'))
                        timestamp_str = datetime.datetime.fromisoformat(last_history['timestamp']).strftime('%Y-%m-%d %H:%M')
                        jump_btn = st.button(f"{q_num}", key=f"jump_{q_num}")
                        st.markdown(f"- `{q_num}` : **{last_eval_mark}** ({timestamp_str})", unsafe_allow_html=True)
                        if jump_btn:
                            st.session_state.current_q_group = [q_num]
                            for key in list(st.session_state.keys()):
                                if key.startswith("checked_") or key.startswith("user_selection_") or key.startswith("shuffled_") or key.startswith("free_input_"):
                                    del st.session_state[key]
                            st.rerun()
            else:
                st.info("まだ評価された問題がありません。")

        else:
            # --- 検索・進捗ページのサイドバー ---
            st.markdown("### 📊 分析・検索ツール")
            
            # 検索・分析用のフィルター機能のみ
            uid = st.session_state.get("uid")
            has_gakushi_permission = check_gakushi_permission(uid)
            
            st.markdown("#### 🔍 表示フィルター")
            
            # 対象範囲
            if has_gakushi_permission:
                analysis_target = st.radio("分析対象", ["国試", "学士試験", "全体"], key="analysis_target")
            else:
                analysis_target = "国試"
            
            # 学習レベルフィルター
            level_filter = st.multiselect(
                "学習レベル",
                ["未学習", "レベル0", "レベル1", "レベル2", "レベル3", "レベル4", "レベル5", "習得済み"],
                default=["未学習", "レベル0", "レベル1", "レベル2", "レベル3", "レベル4", "レベル5", "習得済み"],
                key="level_filter"
            )
            
            # 科目フィルター（動的に設定されるため、デフォルトは空）
            if "available_subjects" in st.session_state:
                subject_filter = st.multiselect(
                    "表示する科目",
                    st.session_state.available_subjects,
                    default=st.session_state.available_subjects,
                    key="subject_filter"
                )
            else:
                subject_filter = []

        # ログアウトボタン
        st.divider()
        if st.button("ログアウト", key="logout_btn"):
            uid = st.session_state.get("uid")
            save_user_data(uid, st.session_state)
            
            # 学士権限のキャッシュをクリア
            check_gakushi_permission.clear()
            
            for k in ["user_logged_in", "id_token", "refresh_token", "name", "username", "email", "uid", "user_data_loaded", "token_timestamp"]:
                if k in st.session_state:
                    del st.session_state[k]

            cookies = get_cookies()
            if cookies:
                cookie_clear_data = {
                    "refresh_token": "",
                    "uid": "",
                    "email": ""
                }
                safe_save_cookies(cookies, cookie_clear_data)
                # 明示的な削除も試行
                try:
                    for ck in ["refresh_token", "uid", "email"]:
                        cookies.delete(ck)
                except Exception as e:
                    print(f"[DEBUG] Cookie deletion error: {e}")
            st.rerun()

    # ---------- ページ本体 ----------
    # 前回セッション復帰選択が未完了の場合、メッセージを表示
    if st.session_state.get("has_previous_session") and not st.session_state.get("session_choice_made"):
        st.info("👈 サイドバーで前回のセッションを続けるか選択してください")
        st.stop()
    
    # 検索ページから演習開始のフラグをチェック
    if st.session_state.get("start_practice_from_search", False):
        # フラグをクリアして演習ページを表示
        st.session_state.start_practice_from_search = False
        render_practice_page()
    elif st.session_state.get("page_select", "演習") == "演習":
        render_practice_page()
    else:
        render_search_page()

    # UI状態の変更を検知してデータを自動保存
    uid = st.session_state.get("uid")
    if uid and st.session_state.get("authenticated"):
        # 前回のUI状態と比較
        current_ui_state = {
            "page_select": st.session_state.get("page_select", "演習"),
            "learning_mode": st.session_state.get("learning_mode", "新しい問題を学習"),
            "current_filter": st.session_state.get("current_filter", "すべて"),
            "search_text": st.session_state.get("search_text", "")
        }
        
        # 前回のUI状態と比較して変更があれば保存
        prev_ui_state = st.session_state.get("_prev_ui_state", {})
        if current_ui_state != prev_ui_state:
            save_user_data(uid, st.session_state)
            st.session_state["_prev_ui_state"] = current_ui_state
            print(f"[DEBUG] UI状態変更により自動保存: {current_ui_state}")
        elif "_prev_ui_state" not in st.session_state:
            # 初回設定
            st.session_state["_prev_ui_state"] = current_ui_state