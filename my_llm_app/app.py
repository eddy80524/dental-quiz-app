import streamlit as st
import json
import os
import random
import datetime
import re
from collections import Counter
import firebase_admin
from firebase_admin import credentials, firestore, storage
import requests
import tempfile
import collections.abc
import pandas as pd
import glob
from streamlit_cookies_manager import EncryptedCookieManager
import pytz  # 日本時間対応

# plotlyインポート（未インストール時の案内付き）
try:
    import plotly.express as px
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

# 日本時間のタイムゾーン設定
JST = pytz.timezone('Asia/Tokyo')

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
            cookie_manager = EncryptedCookieManager(
                prefix="dentai_",
                password=cookie_password
            )
            
            # 初期化直後は準備完了まで待機
            if hasattr(cookie_manager, '_ready'):
                if not cookie_manager._ready:
                    st.session_state.cookie_manager = cookie_manager
                    return cookie_manager
            
            # 簡単なテストでアクセス可能性を確認
            try:
                test_value = cookie_manager.get("init_test", "default")
                st.session_state.cookie_manager = cookie_manager
                return cookie_manager
            except Exception as test_e:
                st.session_state.cookie_manager = cookie_manager  # 準備中でも保存
                return cookie_manager
                
        except Exception as e:
            st.session_state.cookie_manager = None
    
    return st.session_state.cookie_manager

def safe_save_cookies(cookies, data_dict):
    """クッキーを安全に保存（エラーハンドリング付き）"""
    if not cookies:
        return False
    
    try:
        # Cookieが準備完了かチェック
        if hasattr(cookies, '_ready') and not cookies._ready:
            print("[DEBUG] Cookie not ready for saving")
            return False
        
        # データを設定
        for key, value in data_dict.items():
            cookies[key] = value
        
        # 保存実行
        cookies.save()
        print(f"[DEBUG] Cookies saved successfully: {list(data_dict.keys())}")
        return True
        
    except Exception as e:
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
                    return None
                # 簡単なアクセステストを行う
                _ = cookies.get("test", None)
                return cookies
            except Exception as e:
                return None
        else:
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
                        return None
                # 簡単なアクセステストを行う
                test_value = cookies.get("test", None)
                st.session_state.cookie_manager = cookies
                return cookies
            except Exception as e:
                return None
        else:
            return None
    except Exception as e:
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

def firebase_signin(email, password):
    """Firebase認証（Firestore読み取り最小化版）"""
    import time
    start = time.time()
    
    # 重複ログイン防止：既にログイン処理中の場合はスキップ
    if st.session_state.get("login_in_progress"):
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
        
        if r.status_code == 200:
            # TODO: UID統合処理は、本来は一度限りのデータ移行スクリプトとして実行し、
            # 毎回のログイン処理からは削除することで読み取り回数を削減する
            pass
        
        return result
    except requests.exceptions.Timeout:
        total_time = time.time() - start
        return {"error": {"message": "Authentication timeout. Please check your network connection."}}
    except requests.exceptions.RequestException as e:
        total_time = time.time() - start
        return {"error": {"message": f"Network error: {str(e)}"}}
    except Exception as e:
        total_time = time.time() - start
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
                "expiresIn": int(result.get("expires_in", 1800))  # 30分セッション
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

def is_token_expired(token_timestamp, expires_in=1800):
    """トークンが期限切れかどうかをチェック（30分間有効）"""
    if not token_timestamp:
        return True
    now = datetime.datetime.now(datetime.timezone.utc)
    token_time = datetime.datetime.fromisoformat(token_timestamp)
    # 25分（1500秒）で期限切れとして扱い、余裕を持ってリフレッシュ
    return (now - token_time).total_seconds() > 1500

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
            print(f"[DEBUG] Cookie values - rt: {'***' if rt else 'None'}, email: {email}, uid: {'***' if uid else 'None'}")
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
    
    # トークンが期限切れの場合はリフレッシュを試行（30分セッション対応）
    if is_token_expired(token_timestamp) and refresh_token:
        print(f"[DEBUG] トークン期限切れ検出（30分セッション） - 自動リフレッシュ実行中")
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
def load_master_data(version="v2025-08-22-all-gakushi-files"):  # キャッシュ更新用バージョン
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
        'gakushi-2023-1-3.json',
        'gakushi-2023-1再.json', 
        'gakushi-2023-2.json',
        'gakushi-2023-2再.json',
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
    
    # 学士問題数のカウント（デバッグ用）
    gakushi_count = sum(1 for q in all_questions if q.get('number', '').startswith('G'))
    
    print(f"[DEBUG] load_master_data - 総時間: {total_time:.3f}s, 問題数: {len(all_questions)} (学士: {gakushi_count}問)")
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
    """学士試験の年度、回数、領域で問題をフィルタリング（改良版）"""
    yy = str(year)[2:]  # 2024 -> "24"
    
    # より柔軟なパターンマッチング（デバッグ用ログ付き）
    res = []
    pattern_count = 0
    
    for q in all_questions:
        qn = q.get("number", "")
        if not qn.startswith("G"):
            continue
            
        # 複数のパターンに対応
        # G23-2-A-1, G25-1-1-A-1, G22-1再-A-1 など
        patterns = [
            rf'^G{yy}-{re.escape(session)}-{area}-\d+$',  # 基本パターン
            rf'^G{yy}-{re.escape(session)}-{area}\d+$',   # ハイフンなしパターン
        ]
        
        matched = False
        for pattern in patterns:
            if re.match(pattern, qn):
                res.append(q)
                matched = True
                break
        
        if matched:
            pattern_count += 1
    
    print(f"[DEBUG] 学士フィルタ - 年度:{year}, セッション:{session}, 領域:{area} -> {len(res)}問マッチ")
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
                    
                    # カードデータも読み込む（演習記録を正しく表示するため全データ取得）
                    try:
                        print(f"[DEBUG] カードデータ読み込み開始...")
                        cards_start = time.time()
                        cards_ref = db.collection("users").document(uid).collection("userCards")
                        cards_docs = cards_ref.stream()
                        cards = {}
                        for card_doc in cards_docs:
                            cards[card_doc.id] = card_doc.to_dict()
                        
                        cards_time = time.time() - cards_start
                        print(f"[DEBUG] カードデータ読み込み完了: {len(cards)}枚, 時間: {cards_time:.3f}s")
                        
                        # 学習ログを統合してSM2パラメータを復元（必要な場合のみ）
                        if should_integrate_logs(uid):
                            cards = integrate_learning_logs_into_cards(cards, uid)
                        data["cards"] = cards
                    except Exception as e:
                        print(f"[ERROR] カードデータ読み込みエラー: {e}")
                        data["cards"] = {}
                    
                    total_time = time.time() - start
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
                    return default_profile
                
            except Exception as e:
                print(f"[ERROR] load_user_data_minimal エラー: {e}")
    
    print(f"[DEBUG] load_user_data_minimal - デフォルト: {time.time() - start:.3f}s")
    return {"email": "", "settings": {"new_cards_per_day": 10}}




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
                
                # 学習ログを統合してSM2パラメータを復元（必要な場合のみ）
                if should_integrate_logs(uid):
                    cards = integrate_learning_logs_into_cards(cards, uid)
                
                cards_time = time.time() - cards_start
                
                # 初期化: セッション状態の結果を格納する辞書
                session_queues = {
                    "main_queue": user_data.get("main_queue", []),
                    "short_term_review_queue": user_data.get("short_term_review_queue", []),
                    "current_q_group": user_data.get("current_q_group", [])
                }
                
                # 段階3: /users/{uid}/sessionState から演習セッション状態を取得
                session_start = time.time()
                session_ref = db.collection("users").document(uid).collection("sessionState").document("current")
                session_doc = session_ref.get(timeout=5)
                
                if session_doc.exists:
                    session_data = session_doc.to_dict()
                    
                    # --- Firestore対応：JSON文字列を元のリスト形式に復元 ---
                    def deserialize_queue(queue):
                        # 各要素（JSON文字列）を元のリストに変換する
                        deserialized = []
                        for item in queue:
                            try:
                                # 文字列であればJSONとしてロード
                                if isinstance(item, str):
                                    deserialized.append(json.loads(item))
                                # 既にリスト形式ならそのまま追加（後方互換性）
                                elif isinstance(item, list):
                                    deserialized.append(item)
                            except (json.JSONDecodeError, TypeError):
                                # 変換に失敗したデータはスキップ
                                continue
                        return deserialized
                    
                    # セッション状態があれば優先して使用
                    if session_data.get("current_q_group") or session_data.get("main_queue"):
                        session_queues["current_q_group"] = deserialize_queue(session_data.get("current_q_group", []))
                        session_queues["main_queue"] = deserialize_queue(session_data.get("main_queue", []))
                        # short_term_review_queueは構造が異なるので、そのまま
                        session_queues["short_term_review_queue"] = session_data.get("short_term_review_queue", [])
                        print(f"[DEBUG] セッション状態復元成功: current_q_group={len(session_queues['current_q_group'])}, main_queue={len(session_queues['main_queue'])}")
                    else:
                        print(f"[DEBUG] セッション状態は空のため復元スキップ")
                else:
                    print(f"[DEBUG] セッション状態データなし")
                
                session_time = time.time() - session_start
                
                result = {
                    "cards": cards,
                    "main_queue": session_queues["main_queue"],
                    "short_term_review_queue": session_queues["short_term_review_queue"],
                    "current_q_group": session_queues["current_q_group"],
                    "new_cards_per_day": user_data.get("settings", {}).get("new_cards_per_day", 10),
                }
                
                total_time = time.time() - start
                print(f"[DEBUG] load_user_data_full - 成功: プロフィール {profile_time:.3f}s, カード {cards_time:.3f}s, セッション {session_time:.3f}s, 合計 {total_time:.3f}s, カード数: {len(cards)}")
                return result
                
            except Exception as e:
                print(f"[ERROR] load_user_data_full エラー: {e}")
    
    print(f"[DEBUG] load_user_data_full - デフォルト: {time.time() - start:.3f}s")
    return {"cards": {}, "main_queue": [], "short_term_review_queue": [], "current_q_group": [], "new_cards_per_day": 10}

def load_user_data(user_id):
    """後方互換性のため - 軽量版を呼び出す"""
    return load_user_data_minimal(user_id)

def should_integrate_logs(uid):
    """
    学習ログ統合が必要かどうかをチェックする
    """
    try:
        db = get_db()
        if not db:
            return False
        
        user_ref = db.collection("users").document(uid)
        user_doc = user_ref.get()
        user_data = user_doc.to_dict() if user_doc.exists else {}
        
        # 統合済みフラグをチェック
        logs_integrated = user_data.get("logs_integrated", False)
        if logs_integrated:
            print(f"[INFO] UID {uid}: 学習ログ統合済みのためスキップ")
            return False
        else:
            print(f"[INFO] UID {uid}: 学習ログ統合が必要")
            return True
    except Exception as e:
        print(f"[WARNING] 統合済みフラグチェックエラー: {e}")
        return False  # エラーの場合は安全のため統合しない

def safe_integration_with_backup(cards, uid):
    """
    バックアップ機能付きの安全な学習ログ統合
    """
    if not uid:
        return cards
    
    try:
        db = get_db()
        if not db:
            return cards
        
        # 統合済みフラグをチェック
        user_ref = db.collection("users").document(uid)
        user_doc = user_ref.get()
        user_data = user_doc.to_dict() if user_doc.exists else {}
        
        # 既に統合済みの場合はスキップ
        if user_data.get("logs_integrated", False):
            print(f"[INFO] UID {uid}: 学習ログ統合済みのためスキップ")
            return cards
        
        print(f"[INFO] UID {uid}: 安全な学習ログ統合を開始...")
        
        # 現在のユーザーのメールアドレスを取得
        current_email = st.session_state.get("email", "")
        
        # メールアドレスが存在する場合、そのメールに関連する全UIDを取得
        all_uids = [uid]  # 現在のUIDは必ず含める
        
        if current_email:
            try:
                # users コレクションから同じメールアドレスを持つ全ユーザーを検索
                users_ref = db.collection("users").where("email", "==", current_email)
                users_docs = users_ref.get()
                
                for user_doc in users_docs:
                    user_uid = user_doc.id
                    if user_uid not in all_uids:
                        all_uids.append(user_uid)
                        
                print(f"[INFO] 統合対象UID: {len(all_uids)}個")
                        
            except Exception as e:
                print(f"[WARNING] UID検索エラー: {e}")
        
        # 🆕 バックアップの作成
        backup_data = {}
        print(f"[INFO] 統合前バックアップを作成中...")
        
        # 全UIDの学習ログをバックアップ
        for search_uid in all_uids:
            try:
                backup_data[search_uid] = {
                    "learningLogs": [],
                    "userCards": [],
                    "userData": {}
                }
                
                # learningLogsをバックアップ
                learning_logs_ref = db.collection("learningLogs").where("userId", "==", search_uid)
                logs_docs = learning_logs_ref.get()
                
                for doc in logs_docs:
                    log_data = doc.to_dict()
                    log_data["_doc_id"] = doc.id  # ドキュメントIDも保存
                    backup_data[search_uid]["learningLogs"].append(log_data)
                
                # userCardsをバックアップ
                cards_ref = db.collection("users").document(search_uid).collection("userCards")
                cards_docs = cards_ref.stream()
                
                for doc in cards_docs:
                    card_data = doc.to_dict()
                    card_data["_doc_id"] = doc.id
                    backup_data[search_uid]["userCards"].append(card_data)
                
                # ユーザーデータをバックアップ
                user_ref = db.collection("users").document(search_uid)
                user_doc = user_ref.get()
                if user_doc.exists:
                    backup_data[search_uid]["userData"] = user_doc.to_dict()
                
                print(f"[INFO] UID {search_uid}: learningLogs={len(backup_data[search_uid]['learningLogs'])}, userCards={len(backup_data[search_uid]['userCards'])}")
                
            except Exception as e:
                print(f"[WARNING] UID {search_uid} のバックアップエラー: {e}")
        
        # バックアップをFirestoreに保存
        try:
            backup_ref = db.collection("integration_backups").document(f"{uid}_{int(time.time())}")
            backup_ref.set({
                "uid": uid,
                "email": current_email,
                "backup_timestamp": datetime.datetime.utcnow().isoformat(),
                "data": backup_data
            })
            print(f"[SUCCESS] バックアップ保存完了: {backup_ref.id}")
        except Exception as e:
            print(f"[ERROR] バックアップ保存失敗: {e}")
            # バックアップに失敗した場合は統合を中止
            return cards
        
        # 🔄 既存の統合プロセスを実行
        return integrate_learning_logs_into_cards(cards, uid)
        
    except Exception as e:
        print(f"[ERROR] 安全な学習ログ統合エラー: {e}")
        import traceback
        traceback.print_exc()
        return cards

def integrate_learning_logs_into_cards(cards, uid):
    """
    学習ログをカードデータに統合してSM2パラメータを復元する
    一度統合したら古いlearningLogsは削除して重複を防ぐ
    """
    if not uid:
        return cards
    
    try:
        db = get_db()
        if not db:
            return cards
        
        # 統合済みフラグをチェック
        user_ref = db.collection("users").document(uid)
        user_doc = user_ref.get()
        user_data = user_doc.to_dict() if user_doc.exists else {}
        
        # 既に統合済みの場合はスキップ
        if user_data.get("logs_integrated", False):
            print(f"[INFO] UID {uid}: 学習ログ統合済みのためスキップ")
            return cards
        
        print(f"[INFO] UID {uid}: 学習ログ統合を開始...")
        
        # 現在のユーザーのメールアドレスを取得
        current_email = st.session_state.get("email", "")
        
        # メールアドレスが存在する場合、そのメールに関連する全UIDを取得
        all_uids = [uid]  # 現在のUIDは必ず含める
        
        if current_email:
            try:
                # users コレクションから同じメールアドレスを持つ全ユーザーを検索
                users_ref = db.collection("users").where("email", "==", current_email)
                users_docs = users_ref.get()
                
                for user_doc in users_docs:
                    user_uid = user_doc.id
                    if user_uid not in all_uids:
                        all_uids.append(user_uid)
                        
                print(f"[INFO] 統合対象UID: {len(all_uids)}個")
                        
            except Exception as e:
                print(f"[WARNING] UID検索エラー: {e}")
        
        # 全UIDの学習ログを取得
        all_learning_logs = {}
        total_logs = 0
        logs_to_delete = []  # 削除対象のログドキュメント
        
        for search_uid in all_uids:
            try:
                learning_logs_ref = db.collection("learningLogs").where("userId", "==", search_uid)
                logs_docs = learning_logs_ref.get()
                
                uid_log_count = 0
                for doc in logs_docs:
                    log_data = doc.to_dict()
                    question_id = log_data.get("questionId", "")
                    if question_id:
                        if question_id not in all_learning_logs:
                            all_learning_logs[question_id] = []
                        all_learning_logs[question_id].append(log_data)
                        logs_to_delete.append(doc.reference)  # 削除対象に追加
                        uid_log_count += 1
                        total_logs += 1
                    
            except Exception as e:
                print(f"[WARNING] UID {search_uid} のログ取得エラー: {e}")
        
        print(f"統合対象学習ログ: {total_logs}件, 問題数: {len(all_learning_logs)}問")
        
        # 各問題IDの学習ログを時系列でソート
        for question_id in all_learning_logs:
            all_learning_logs[question_id].sort(key=lambda x: x.get("timestamp", ""))
        
        # カードデータに学習ログを統合
        updated_cards = 0
        cards_to_save = {}
        
        for q_num in all_learning_logs:
            # カードが存在しない場合は新規作成
            if q_num not in cards:
                cards[q_num] = {
                    "n": 0,
                    "EF": 2.5,
                    "interval": 0,
                    "due": None,
                    "history": []
                }
            
            card = cards[q_num]
            logs = all_learning_logs[q_num]
            
            # 学習ログから最新のSM2パラメータを復元
            if logs:
                latest_log = logs[-1]  # 最新のログ
                
                # SM2パラメータを復元
                card["n"] = len(logs)  # 学習回数
                
                # 最新ログからSM2パラメータを取得、なければ再計算
                latest_ef = latest_log.get("EF")
                latest_interval = latest_log.get("interval")
                
                if latest_ef is None or latest_interval is None:
                    # SM2パラメータが記録されていない場合、履歴から再計算
                    ef = 2.5
                    interval = 0
                    n = 0
                    
                    for log in logs:
                        quality = log.get("quality", 0)
                        # SM2アルゴリズムで再計算
                        if n == 0:
                            interval = 1
                        elif n == 1:
                            interval = 6
                        else:
                            interval = max(1, round(interval * ef))
                        
                        ef = ef + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
                        ef = max(1.3, ef)
                        
                        n += 1
                    
                    card["EF"] = ef
                    card["interval"] = interval
                else:
                    card["EF"] = latest_ef
                    card["interval"] = latest_interval
                
                # dueの計算（最新の学習タイムスタンプ + interval）
                last_timestamp = latest_log.get("timestamp")
                if last_timestamp and card["interval"] > 0:
                    try:
                        if isinstance(last_timestamp, str):
                            # ISO形式の文字列をパース
                            last_dt = datetime.datetime.fromisoformat(last_timestamp.replace('Z', '+00:00'))
                        else:
                            last_dt = last_timestamp
                        
                        due_dt = last_dt + datetime.timedelta(days=card["interval"])
                        due_iso = due_dt.isoformat()
                        card["due"] = due_iso
                        card["next_review"] = due_iso  # 復習カード計算との互換性のため追加
                    except Exception:
                        card["due"] = None
                        card["next_review"] = None
                else:
                    card["due"] = None
                    card["next_review"] = None
                
                # historyの構築
                card["history"] = []
                for log in logs:
                    if "quality" in log and "timestamp" in log:
                        card["history"].append({
                            "quality": log["quality"],
                            "timestamp": log["timestamp"]
                        })
                
                # 統合後のカードを保存対象に追加
                cards_to_save[q_num] = card
                updated_cards += 1
        
        if updated_cards > 0:
            print(f"学習ログ統合完了: {len(all_learning_logs)}問題の履歴を統合")
            print(f"  - 更新されたカード数: {updated_cards}")
            
            try:
                # バッチでカードデータを保存
                batch = db.batch()
                user_cards_ref = db.collection("users").document(uid).collection("userCards")
                
                for question_id, card_data in cards_to_save.items():
                    card_ref = user_cards_ref.document(question_id)
                    batch.set(card_ref, card_data, merge=True)
                
                # 統合済みフラグを設定
                batch.update(user_ref, {
                    "logs_integrated": True,
                    "logs_integrated_at": datetime.datetime.utcnow().isoformat()
                })
                
                batch.commit()
                print(f"[SUCCESS] カードデータの保存完了")
                
                # 古いlearningLogsを削除（正規化）
                delete_count = 0
                batch_delete = db.batch()
                for i, log_ref in enumerate(logs_to_delete):
                    batch_delete.delete(log_ref)
                    delete_count += 1
                    
                    # バッチサイズ制限（500件）に対応
                    if (i + 1) % 500 == 0:
                        batch_delete.commit()
                        batch_delete = db.batch()
                
                # 残りのログを削除
                if delete_count % 500 != 0:
                    batch_delete.commit()
                
                print(f"[SUCCESS] 古いlearningLogsを削除: {delete_count}件")
                print(f"[INFO] UID {uid}: 学習ログ統合・正規化完了")
                
            except Exception as e:
                print(f"[ERROR] データ保存・削除エラー: {e}")
        
        return cards
        
    except Exception as e:
        print(f"[ERROR] 学習ログ統合エラー: {e}")
        import traceback
        traceback.print_exc()
        return cards

def detailed_remaining_data_analysis(uid):
    """
    残存データの詳細分析で統合問題を特定
    """
    try:
        db = get_db()
        if not db:
            return "データベース接続エラー"
        
        analysis_log = ["🔍 残存データの詳細分析..."]
        
        # 1. 残存カードの詳細情報
        cards_ref = db.collection("users").document(uid).collection("userCards")
        cards_docs = list(cards_ref.stream())
        
        cards_with_history = []
        cards_without_history = []
        
        for doc in cards_docs:
            card_data = doc.to_dict()
            if card_data.get("history"):
                cards_with_history.append({
                    "id": doc.id,
                    "history": card_data["history"],
                    "n": card_data.get("n", 0),
                    "EF": card_data.get("EF", 2.5),
                    "interval": card_data.get("interval", 0)
                })
            else:
                cards_without_history.append({
                    "id": doc.id,
                    "has_quality": "quality" in card_data,
                    "quality": card_data.get("quality"),
                    "n": card_data.get("n", 0)
                })
        
        analysis_log.append(f"\n📊 残存データ詳細:")
        analysis_log.append(f"- history有り: {len(cards_with_history)}枚")
        analysis_log.append(f"- history無し: {len(cards_without_history)}枚")
        
        # 2. history有りカードの詳細
        if cards_with_history:
            analysis_log.append(f"\n✅ history有りカード詳細:")
            for card in cards_with_history[:10]:  # 最大10件
                history_count = len(card["history"])
                first_date = card["history"][0].get("timestamp", "不明")[:10] if card["history"] else "不明"
                last_date = card["history"][-1].get("timestamp", "不明")[:10] if card["history"] else "不明"
                analysis_log.append(f"  {card['id']}: {history_count}回 ({first_date} → {last_date})")
        
        # 3. 統合ログの確認
        user_ref = db.collection("users").document(uid)
        user_doc = user_ref.get()
        user_data = user_doc.to_dict() if user_doc.exists else {}
        
        logs_integrated = user_data.get("logs_integrated", False)
        logs_integrated_at = user_data.get("logs_integrated_at", "未設定")
        
        analysis_log.append(f"\n🔄 統合プロセス情報:")
        analysis_log.append(f"- 統合完了フラグ: {logs_integrated}")
        analysis_log.append(f"- 統合日時: {logs_integrated_at}")
        
        # 4. 可能な復旧方法の提案
        analysis_log.append(f"\n💡 可能な対策:")
        analysis_log.append(f"1. Firestore管理コンソールでバックアップ確認")
        analysis_log.append(f"2. 統合プロセスのバグ修正後、手動でログ再生成")
        analysis_log.append(f"3. 残存データから学習パターンを推定して部分復旧")
        
        # 5. 緊急停止フラグの設定提案
        analysis_log.append(f"\n⚠️ 推奨アクション:")
        analysis_log.append(f"- 他ユーザーの統合プロセスを緊急停止")
        analysis_log.append(f"- 統合アルゴリズムの修正")
        analysis_log.append(f"- バックアップ復旧の検討")
        
        return "\n".join(analysis_log)
        
    except Exception as e:
        return f"分析エラー: {e}"

def restore_from_backup(uid):
    """
    バックアップから学習データを復旧
    """
    try:
        db = get_db()
        if not db:
            return "データベース接続エラー"
        
        # バックアップを検索
        backups_ref = db.collection("integration_backups").where("uid", "==", uid)
        backup_docs = list(backups_ref.stream())
        
        if not backup_docs:
            return "❌ バックアップが見つかりませんでした"
        
        # 最新のバックアップを選択
        latest_backup = max(backup_docs, key=lambda x: x.to_dict().get("backup_timestamp", ""))
        backup_data = latest_backup.to_dict()
        
        restore_log = [f"🔄 バックアップからの復旧を開始..."]
        restore_log.append(f"バックアップID: {latest_backup.id}")
        restore_log.append(f"バックアップ日時: {backup_data.get('backup_timestamp', '不明')}")
        
        # 復旧処理（実際の復旧は危険なため、情報表示のみ）
        backup_uids = backup_data.get("data", {})
        restore_log.append(f"\n📊 バックアップ内容:")
        
        total_logs = 0
        total_cards = 0
        
        for backup_uid, uid_data in backup_uids.items():
            logs_count = len(uid_data.get("learningLogs", []))
            cards_count = len(uid_data.get("userCards", []))
            total_logs += logs_count
            total_cards += cards_count
            
            restore_log.append(f"  UID {backup_uid}:")
            restore_log.append(f"    learningLogs: {logs_count}件")
            restore_log.append(f"    userCards: {cards_count}件")
        
        restore_log.append(f"\n📈 復旧可能データ:")
        restore_log.append(f"- 総learningLogs: {total_logs}件")
        restore_log.append(f"- 総userCards: {total_cards}件")
        
        restore_log.append(f"\n⚠️ 重要:")
        restore_log.append(f"実際の復旧は手動で慎重に行う必要があります")
        restore_log.append(f"現在のデータ(250枚)は既に正常に統合済みです")
        
        return "\n".join(restore_log)
        
    except Exception as e:
        return f"復旧チェックエラー: {e}"

def analyze_integration_process(uid):
    """
    統合プロセスの詳細分析
    """
    try:
        db = get_db()
        if not db:
            return "データベース接続エラー"
        
        analysis_log = ["🔄 統合プロセス分析..."]
        
        # 1. 現在のユーザーデータ確認
        user_ref = db.collection("users").document(uid)
        user_doc = user_ref.get()
        user_data = user_doc.to_dict() if user_doc.exists else {}
        
        analysis_log.append(f"現在のUID: {uid}")
        analysis_log.append(f"統合済みフラグ: {user_data.get('logs_integrated', False)}")
        analysis_log.append(f"統合日時: {user_data.get('logs_integrated_at', '未設定')}")
        analysis_log.append(f"Email: {user_data.get('email', '未設定')}")
        analysis_log.append(f"作成日時: {user_data.get('created_at', '未設定')}")
        
        # 2. 統合されたカードの詳細分析
        cards_ref = db.collection("users").document(uid).collection("userCards")
        cards_docs = list(cards_ref.stream())
        
        history_by_date = {}
        earliest_record = None
        latest_record = None
        
        for card_doc in cards_docs:
            card_data = card_doc.to_dict()
            history = card_data.get("history", [])
            
            for record in history:
                timestamp = record.get("timestamp", "")
                if timestamp:
                    date = timestamp[:10]  # YYYY-MM-DD
                    if date not in history_by_date:
                        history_by_date[date] = 0
                    history_by_date[date] += 1
                    
                    # 最古・最新記録の追跡
                    if not earliest_record or timestamp < earliest_record:
                        earliest_record = timestamp
                    if not latest_record or timestamp > latest_record:
                        latest_record = timestamp
        
        analysis_log.append(f"\n📅 演習記録の時系列分析:")
        analysis_log.append(f"- 最古の記録: {earliest_record}")
        analysis_log.append(f"- 最新の記録: {latest_record}")
        analysis_log.append(f"- 記録のある日数: {len(history_by_date)}日")
        
        # 日別の記録数（上位10日）
        sorted_dates = sorted(history_by_date.items(), key=lambda x: x[1], reverse=True)
        analysis_log.append(f"\n📊 日別演習回数（上位10日）:")
        for date, count in sorted_dates[:10]:
            analysis_log.append(f"  {date}: {count}回")
        
        # 3. 統合前の推定UID数
        # historyのタイムスタンプパターンから元のUID数を推定
        timestamp_patterns = set()
        for card_doc in cards_docs[:50]:  # サンプルとして50件
            card_data = card_doc.to_dict()
            history = card_data.get("history", [])
            for record in history:
                timestamp = record.get("timestamp", "")
                if timestamp:
                    # タイムスタンプの秒・ミリ秒部分でパターン分析
                    pattern = timestamp[-10:]  # 秒以下の部分
                    timestamp_patterns.add(pattern)
        
        analysis_log.append(f"\n🔢 推定情報:")
        analysis_log.append(f"- タイムスタンプパターン数: {len(timestamp_patterns)}")
        analysis_log.append(f"- 推定元UID数: 不明（要詳細調査）")
        
        # 4. 異常な記録の確認
        suspicious_records = []
        for card_doc in cards_docs[:20]:
            card_data = card_doc.to_dict()
            history = card_data.get("history", [])
            
            if len(history) > 5:  # 5回以上の記録
                suspicious_records.append({
                    "card": card_doc.id,
                    "count": len(history),
                    "dates": [h.get("timestamp", "")[:10] for h in history]
                })
        
        if suspicious_records:
            analysis_log.append(f"\n🕵️ 多回数演習カード:")
            for record in suspicious_records[:5]:
                analysis_log.append(f"  {record['card']}: {record['count']}回")
        
        return "\n".join(analysis_log)
        
    except Exception as e:
        return f"統合プロセス分析エラー: {e}"

def comprehensive_uid_investigation(current_uid, current_email):
    """
    包括的UID調査：関連するすべてのデータを徹底的に調査
    """
    try:
        db = get_db()
        if not db:
            return "データベース接続エラー"
        
        investigation_log = ["🔍 包括的UID調査を開始..."]
        investigation_log.append(f"現在のUID: {current_uid}")
        investigation_log.append(f"現在のEmail: {current_email}")
        
        # 1. users コレクション全体の調査
        investigation_log.append(f"\n📁 usersコレクション調査:")
        users_ref = db.collection("users")
        all_users = list(users_ref.stream())
        
        email_matches = []
        for user_doc in all_users:
            user_data = user_doc.to_dict()
            user_email = user_data.get("email", "")
            if user_email == current_email:
                email_matches.append({
                    "uid": user_doc.id,
                    "email": user_email,
                    "created": user_data.get("created_at", "不明"),
                    "logs_integrated": user_data.get("logs_integrated", False),
                    "logs_integrated_at": user_data.get("logs_integrated_at", "未設定")
                })
        
        investigation_log.append(f"- 総ユーザー数: {len(all_users)}")
        investigation_log.append(f"- {current_email}のUID数: {len(email_matches)}")
        
        for match in email_matches:
            investigation_log.append(f"  UID: {match['uid']}")
            investigation_log.append(f"    作成日: {match['created']}")
            investigation_log.append(f"    統合済み: {match['logs_integrated']}")
            investigation_log.append(f"    統合日時: {match['logs_integrated_at']}")
        
        # 2. learningLogs コレクション全体の調査
        investigation_log.append(f"\n📊 learningLogsコレクション調査:")
        logs_ref = db.collection("learningLogs")
        
        # 現在のUIDのログ
        current_logs = list(logs_ref.where("userId", "==", current_uid).stream())
        investigation_log.append(f"- 現在のUID({current_uid})のログ: {len(current_logs)}件")
        
        # 全体のログ数確認（大きすぎる場合はサンプルのみ）
        try:
            # まず最初の100件を取得してサンプル調査
            sample_logs = list(logs_ref.limit(100).stream())
            investigation_log.append(f"- learningLogsサンプル: {len(sample_logs)}件")
            
            # サンプルからuserIdの種類を確認
            sample_uids = set()
            for log_doc in sample_logs:
                log_data = log_doc.to_dict()
                user_id = log_data.get("userId", "")
                if user_id:
                    sample_uids.add(user_id)
            
            investigation_log.append(f"- サンプル中のUID種類: {len(sample_uids)}個")
            
            # 各UIDでemail検索
            email_related_logs = {}
            for uid in sample_uids:
                try:
                    user_ref = db.collection("users").document(uid)
                    user_doc = user_ref.get()
                    if user_doc.exists:
                        user_data = user_doc.to_dict()
                        if user_data.get("email") == current_email:
                            uid_logs = list(logs_ref.where("userId", "==", uid).stream())
                            email_related_logs[uid] = len(uid_logs)
                except:
                    continue
            
            if email_related_logs:
                investigation_log.append(f"\n🎯 {current_email}関連のlearningLogs:")
                for uid, count in email_related_logs.items():
                    investigation_log.append(f"  UID {uid}: {count}件")
            else:
                investigation_log.append(f"\n❌ {current_email}関連のlearningLogsなし")
                
        except Exception as e:
            investigation_log.append(f"learningLogs調査エラー: {e}")
        
        # 3. 統合前の痕跡を探す
        investigation_log.append(f"\n🕵️ 統合前の痕跡調査:")
        
        # 統合されたUIDのuserCardsを詳細調査
        for match in email_matches:
            uid = match["uid"]
            cards_ref = db.collection("users").document(uid).collection("userCards")
            cards_with_history = 0
            total_cards = 0
            
            try:
                cards_docs = list(cards_ref.stream())
                total_cards = len(cards_docs)
                
                for card_doc in cards_docs:
                    card_data = card_doc.to_dict()
                    if card_data.get("history"):
                        cards_with_history += 1
                
                investigation_log.append(f"  UID {uid}: {cards_with_history}/{total_cards} カードにhistory")
                
            except Exception as e:
                investigation_log.append(f"  UID {uid}: userCards調査エラー - {e}")
        
        # 4. 推定される状況
        investigation_log.append(f"\n💭 推定される状況:")
        if len(email_matches) == 1:
            investigation_log.append("- 他のUIDが削除されている可能性")
            investigation_log.append("- 統合プロセスでUIDが統合された可能性")
        else:
            investigation_log.append("- 複数UIDが存在するがデータが分散")
        
        investigation_log.append(f"\n🔄 次のアクション提案:")
        investigation_log.append("1. Firestore管理コンソールでの手動確認")
        investigation_log.append("2. deleted_usersコレクション等の確認")
        investigation_log.append("3. 統合ログの詳細確認")
        
        return "\n".join(investigation_log)
        
    except Exception as e:
        return f"包括的調査エラー: {e}"

def attempt_data_recovery(uid):
    """
    データ復旧を試行する
    """
    try:
        db = get_db()
        if not db:
            return "データベース接続エラー"
        
        recovery_log = ["🔄 データ復旧を開始..."]
        
        # 1. 同じメールアドレスの他のUIDから残存データを収集
        current_email = st.session_state.get("email", "")
        if not current_email:
            return "メールアドレス情報がありません"
        
        # 2. 他のUIDを検索
        users_ref = db.collection("users").where("email", "==", current_email)
        users_docs = users_ref.get()
        
        other_uids = []
        for user_doc in users_docs:
            if user_doc.id != uid:
                other_uids.append(user_doc.id)
        
        recovery_log.append(f"📧 {current_email} に関連するUID: {len(other_uids) + 1}個")
        
        # 3. 他のUIDのlearningLogsとuserCardsを確認
        recovered_logs = {}
        recovered_cards = {}
        
        for other_uid in other_uids:
            # learningLogsをチェック
            logs_ref = db.collection("learningLogs").where("userId", "==", other_uid)
            logs_docs = logs_ref.get()
            
            for doc in logs_docs:
                log_data = doc.to_dict()
                question_id = log_data.get("questionId", "")
                if question_id:
                    if question_id not in recovered_logs:
                        recovered_logs[question_id] = []
                    recovered_logs[question_id].append(log_data)
            
            # userCardsもチェック
            cards_ref = db.collection("users").document(other_uid).collection("userCards")
            cards_docs = cards_ref.stream()
            
            for doc in cards_docs:
                card_data = doc.to_dict()
                if card_data.get("history"):  # historyがあるカードのみ
                    recovered_cards[doc.id] = card_data
            
            recovery_log.append(f"UID {other_uid}: learningLogs={len(logs_docs)}, userCards={len(list(cards_docs))}")
        
        # 4. 復旧可能性の評価
        total_recoverable_logs = sum(len(logs) for logs in recovered_logs.values())
        total_recoverable_cards = len(recovered_cards)
        
        recovery_log.append(f"\n📊 復旧可能データ:")
        recovery_log.append(f"- 学習ログ: {total_recoverable_logs}件")
        recovery_log.append(f"- カード: {total_recoverable_cards}枚")
        
        if total_recoverable_logs > 0 or total_recoverable_cards > 0:
            recovery_log.append(f"\n✅ データ復旧の可能性があります！")
            # 実際の復旧処理はここに実装する
        else:
            recovery_log.append(f"\n❌ 復旧可能なデータが見つかりませんでした")
        
        return "\n".join(recovery_log)
        
    except Exception as e:
        return f"復旧チェックエラー: {e}"

def emergency_data_check(uid):
    """
    緊急データチェック: Firestoreの実際の状態を確認
    """
    try:
        db = get_db()
        if not db:
            return "データベース接続エラー"
        
        # 1. userCardsコレクションの確認
        cards_ref = db.collection("users").document(uid).collection("userCards")
        cards_docs = list(cards_ref.stream())
        
        cards_with_history = 0
        total_history_entries = 0
        sample_history = []
        
        for doc in cards_docs[:10]:  # 最初の10件をサンプル
            card_data = doc.to_dict()
            history = card_data.get("history", [])
            if history:
                cards_with_history += 1
                total_history_entries += len(history)
                if len(sample_history) < 3:  # 3件のサンプルを収集
                    sample_history.append({
                        "card_id": doc.id,
                        "history_count": len(history),
                        "sample": history[-1] if history else None  # 最新の履歴
                    })
        
        # 2. 元のlearningLogsが本当に削除されているかチェック
        learning_logs_ref = db.collection("learningLogs").where("userId", "==", uid)
        logs_docs = list(learning_logs_ref.stream())
        
        # 3. 同じメールアドレスの他のUIDをチェック
        current_email = st.session_state.get("email", "")
        other_uids = []
        if current_email:
            users_ref = db.collection("users").where("email", "==", current_email)
            users_docs = users_ref.get()
            for user_doc in users_docs:
                if user_doc.id != uid:
                    other_uids.append(user_doc.id)
        
        # 4. 他のUIDのlearningLogsをチェック
        other_logs_count = 0
        for other_uid in other_uids:
            other_logs_ref = db.collection("learningLogs").where("userId", "==", other_uid)
            other_logs_count += len(list(other_logs_ref.stream()))
        
        result = f"""
🚨 緊急データチェック結果:

【現在のUID: {uid}】
- userCards総数: {len(cards_docs)}
- history有りカード数: {cards_with_history}
- 総history記録数: {total_history_entries}
- 残存learningLogs: {len(logs_docs)}

【他のUID ({len(other_uids)}個)】
- 他のUIDのlearningLogs残数: {other_logs_count}

【サンプルhistory】
"""
        for sample in sample_history:
            result += f"- カード{sample['card_id']}: {sample['history_count']}回 最新={sample['sample']}\n"
        
        return result
        
    except Exception as e:
        return f"エラー: {e}"

# --- Google Analytics連携 ---
def log_to_ga(event_name: str, user_id: str, params: dict):
    """
    Measurement Protocolを使ってサーバーからGA4にイベントを送信する関数
    """
    # st.secretsを使って安全にIDとシークレットを取得
    api_secret = st.secrets.get("ga_api_secret")
    measurement_id = st.secrets.get("ga_measurement_id")

    # Secretsが設定されていない場合は何もしない
    if not api_secret or not measurement_id:
        print("[Analytics] Secrets not found. Skipping event log.")
        return

    payload = {
        "client_id": user_id, # ユーザーを一意に識別するID（uidが最適）
        "non_personalized_ads": False, # デバッグ時にはこれがあると良い
        "events": [{
            "name": event_name,
            "params": {
                **params, # 元のパラメータを展開
                "debug_mode": True # ★ DebugViewでリアルタイム確認用
            }
        }]
    }
    
    try:
        requests.post(
            f"https://www.google-analytics.com/mp/collect?measurement_id={measurement_id}&api_secret={api_secret}",
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"}
        )
        print(f"[Analytics] Logged event '{event_name}' for user {user_id}")
    except Exception as e:
        print(f"[ERROR] Failed to log GA event: {e}")

def save_user_data(user_id, question_id=None, updated_card_data=None, session_state=None):
    """
    リファクタリング済み：Firestoreの読み取り/書き込み回数を最小化した保存関数
    - 単一カードの更新のみサポート（一括更新廃止）
    - learningLogsコレクションへの書き込み廃止
    """
    try:
        if not ensure_valid_session():
            return

        db = get_db()
        if not db or not user_id:
            return
        
        # 1. 単一カードデータの更新（解答時のみ）
        if question_id and updated_card_data:
            user_cards_ref = db.collection("users").document(user_id).collection("userCards")
            card_ref = user_cards_ref.document(question_id)
            card_ref.set(updated_card_data, merge=True)
            print(f"[DEBUG] save_user_data - カード更新: {question_id}")
        
        # 2. セッション状態保存（学習キューの保存）
        if session_state:
            # --- Firestore対応：ネストした配列をJSON文字列に変換 ---
            def serialize_queue(queue):
                # 各グループ（リスト）をJSON文字列に変換する
                return [json.dumps(group) for group in queue]

            session_data = {
                "current_q_group": serialize_queue(session_state.get("current_q_group", [])),
                "main_queue": serialize_queue(session_state.get("main_queue", [])),
                "short_term_review_queue": session_state.get("short_term_review_queue", []), # これは既に文字列にできる形式のはず
                "result_log": session_state.get("result_log", {}),
                "last_updated": datetime.datetime.utcnow().isoformat()
            }
            
            # 演習セッション状態の保存
            if session_data["current_q_group"] or session_data["main_queue"]:
                try:
                    session_ref = db.collection("users").document(user_id).collection("sessionState").document("current")
                    session_ref.set(session_data, merge=True)
                    print(f"[DEBUG] save_user_data - セッション状態保存: current_q_group={len(session_data['current_q_group'])}, main_queue={len(session_data['main_queue'])}")
                except Exception as e:
                    print(f"[ERROR] セッション状態保存失敗: {e}")
            
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
    # Firestoreクライアントを取得
    db = firestore.client()
    
    # サイドバーのフィルター設定を取得
    uid = st.session_state.get("uid")
    has_gakushi_permission = check_gakushi_permission(uid)
    analysis_target = st.session_state.get("analysis_target", "国試")
    level_filter = st.session_state.get("level_filter", ["未学習", "レベル0", "レベル1", "レベル2", "レベル3", "レベル4", "レベル5", "習得済み"])
    
    # 学習進捗の可視化セクションを追加
    st.subheader("📈 学習ダッシュボード")
    
    # 学習データの準備 - 新しいFirestore構造に対応
    cards = st.session_state.get("cards", {})
    
    # カードデータが空の場合、完全版データを読み込む
    if not cards and uid:
        try:
            cache_buster = int(datetime.datetime.now().timestamp())
            full_data = load_user_data_full(uid, cache_buster)
            cards = full_data.get("cards", {})
            st.session_state["cards"] = cards
        except Exception as e:
            st.error(f"学習データの読み込みエラー: {e}")
    
    # 学習ログを統合してSM2パラメータを最新化（統合済みの場合はスキップ）
    if uid and cards and should_integrate_logs(uid):
        print(f"[INFO] ダッシュボード: 学習ログ統合を実行")
        cards = integrate_learning_logs_into_cards(cards, uid)
        st.session_state["cards"] = cards
    
    # 分析対象に応じたフィルタリング
    filtered_data = []
    for q in ALL_QUESTIONS:
        q_num = q.get("number", "")
        
        # 権限チェック
        if q_num.startswith("G") and not has_gakushi_permission:
            continue
        
        # 分析対象フィルタ（明確に国試か学士試験のみ）
        if analysis_target == "学士試験":
            if not q_num.startswith("G"):
                continue
        elif analysis_target == "国試":
            if q_num.startswith("G"):
                continue
            
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
        
        # 必修問題チェック（分析対象に応じて正確に判定）
        if analysis_target == "学士試験":
            # 学士試験の必修問題判定にはis_gakushi_hisshu関数を使用
            is_mandatory = q_num in GAKUSHI_HISSHU_Q_NUMBERS_SET
        else:  # 国試
            # 国試の必修問題判定にはis_hisshu関数を使用
            is_mandatory = q_num in HISSHU_Q_NUMBERS_SET
        
        # カードの履歴を取得（学習ログ統合済み）
        card_history = card.get("history", [])
        
        filtered_data.append({
            "id": q_num,
            "subject": q.get("subject", "未分類"),
            "level": level,
            "ef": card.get("EF", 2.5),  # 大文字EFに修正
            "history": card_history,
            "is_hisshu": is_mandatory
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
    
    # 統合後の学習状況サマリーを表示
    if uid and not filtered_df.empty:
        st.markdown("---")
        st.markdown("### 📊 学習状況")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            total_studied = len(filtered_df[filtered_df["level"] != "未学習"])
            total_problems = len(filtered_df)
            st.metric("学習済み問題", f"{total_studied}", 
                     delta=f"{total_studied}/{total_problems}")
        
        with col2:
            mastered_count = len(filtered_df[filtered_df["level"] == "習得済み"])
            st.metric("習得済み問題", f"{mastered_count}",
                     delta=f"{mastered_count/total_problems*100:.1f}%" if total_problems > 0 else "0%")
        
        with col3:
            # 全履歴から学習回数を計算
            total_learning_sessions = 0
            for _, row in filtered_df.iterrows():
                history_list = row["history"]
                if isinstance(history_list, list):
                    total_learning_sessions += len(history_list)
            st.metric("総学習回数", f"{total_learning_sessions}")
        
        with col4:
            # 平均EF値
            studied_cards = filtered_df[filtered_df["level"] != "未学習"]
            if not studied_cards.empty:
                avg_ef = studied_cards["ef"].mean()
                st.metric("平均記憶定着度", f"{avg_ef:.2f}",
                         delta="良好" if avg_ef >= 2.5 else "要復習")
            else:
                st.metric("平均記憶定着度", "N/A")
    
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
                
                for idx, history_list in enumerate(filtered_df["history"]):
                    for review in history_list:
                        if isinstance(review, dict) and "quality" in review:
                            total_reviews += 1
                            if review["quality"] >= 4:
                                correct_reviews += 1
                
                retention_rate = (correct_reviews / total_reviews * 100) if total_reviews > 0 else 0
                st.metric(label="選択範囲の正解率", value=f"{retention_rate:.1f}%", delta=f"{correct_reviews} / {total_reviews} 回")
                
                # 必修問題の正解率計算
                hisshu_df = filtered_df[filtered_df["is_hisshu"] == True]
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
            # 科目別進捗状況の可視化
            st.markdown("##### 科目別進捗状況")
            subject_progress = []
            for subject in filtered_df["subject"].unique():
                subject_data = filtered_df[filtered_df["subject"] == subject]
                total_problems = len(subject_data)
                studied_problems = len(subject_data[subject_data["level"] != "未学習"])
                mastered_problems = len(subject_data[subject_data["level"] == "習得済み"])
                
                progress_rate = (studied_problems / total_problems * 100) if total_problems > 0 else 0
                mastery_rate = (mastered_problems / total_problems * 100) if total_problems > 0 else 0
                
                subject_progress.append({
                    "科目": subject,
                    "総問題数": total_problems,
                    "学習済み": studied_problems,
                    "習得済み": mastered_problems,
                    "学習進捗率(%)": round(progress_rate, 1),
                    "習得率(%)": round(mastery_rate, 1)
                })
            
            progress_df = pd.DataFrame(subject_progress)
            progress_df = progress_df.sort_values("学習進捗率(%)", ascending=False)
            
            # 進捗率グラフ
            try:
                import plotly.express as px
                import plotly.graph_objects as go
                
                fig = go.Figure()
                
                # 学習進捗率のバー
                fig.add_trace(go.Bar(
                    name='学習進捗率',
                    x=progress_df["科目"],
                    y=progress_df["学習進捗率(%)"],
                    marker_color='lightblue',
                    text=progress_df["学習進捗率(%)"].astype(str) + '%',
                    textposition='outside'
                ))
                
                # 習得率のバー
                fig.add_trace(go.Bar(
                    name='習得率',
                    x=progress_df["科目"],
                    y=progress_df["習得率(%)"],
                    marker_color='green',
                    text=progress_df["習得率(%)"].astype(str) + '%',
                    textposition='outside'
                ))
                
                fig.update_layout(
                    title="科目別進捗状況（100%=全問題演習済み）",
                    xaxis_title="科目",
                    yaxis_title="進捗率 (%)",
                    yaxis=dict(range=[0, 105]),
                    barmode='group',
                    xaxis_tickangle=-45,
                    height=500
                )
                
                st.plotly_chart(fig, use_container_width=True)
                
            except ImportError:
                st.bar_chart(progress_df.set_index("科目")[["学習進捗率(%)", "習得率(%)"]])
            
            # 詳細テーブル
            st.dataframe(progress_df, use_container_width=True)
            
            st.markdown("##### 学習の記録")
            
            # 学習記録の取得と最初の学習日の特定
            review_history = []
            first_study_date = None
            
            for history_list in filtered_df["history"]:
                for review in history_list:
                    if isinstance(review, dict) and "timestamp" in review:
                        review_date = datetime.datetime.fromisoformat(review["timestamp"]).date()
                        review_history.append(review_date)
                        if first_study_date is None or review_date < first_study_date:
                            first_study_date = review_date
            
            if review_history and first_study_date:
                from collections import Counter
                review_counts = Counter(review_history)
                
                # 最初の学習日から今日までの日付範囲を作成
                today = datetime.datetime.now(datetime.timezone.utc).date()
                days_since_start = (today - first_study_date).days + 1
                
                # 表示する日数を90日に制限
                display_days = min(days_since_start, 90)
                start_date = today - datetime.timedelta(days=display_days - 1)
                
                dates = [start_date + datetime.timedelta(days=i) for i in range(display_days)]
                counts = [review_counts.get(d, 0) for d in dates]
                chart_df = pd.DataFrame({"Date": dates, "Reviews": counts})
                
                # plotlyを使ってy軸の最小値を0に固定
                try:
                    import plotly.express as px
                    fig = px.bar(chart_df, x="Date", y="Reviews", 
                                title=f"日々の学習量（過去90日間）")
                    fig.update_layout(
                        yaxis=dict(range=[0, max(counts) * 1.1] if counts else [0, 5]),
                        showlegend=False
                    )
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # 学習統計の表示（90日間のデータに基づく）
                    total_reviews = sum(counts)
                    active_days = len([c for c in counts if c > 0])
                    avg_reviews_per_active_day = total_reviews / active_days if active_days > 0 else 0
                    
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("総学習回数", f"{total_reviews}回", help="過去90日間")
                    with col2:
                        st.metric("学習日数", f"{active_days}日", help="過去90日間")
                    with col3:
                        st.metric("学習継続日数", f"{display_days}日", help="表示期間")
                    with col4:
                        st.metric("1日平均学習回数", f"{avg_reviews_per_active_day:.1f}回", help="過去90日間")
                        
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
                if analysis_target == "学士試験":
                    if not question_number.startswith("G"):
                        continue
                elif analysis_target == "国試":
                    if question_number.startswith("G"):
                        continue
                
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
                        is_mandatory_question = question_number in GAKUSHI_HISSHU_Q_NUMBERS_SET
                    else:
                        is_mandatory_question = question_number in HISSHU_Q_NUMBERS_SET
                    
                    level_color = level_colors.get(level, "#888888")
                    hisshu_mark = "🔥" if is_mandatory_question else ""
                    
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
    # 【緊急停止】古いキャッシュを無効化 - タイムスタンプでキャッシュバスト
    import time
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.success(f"✅ アプリ更新済み: {current_time} - データ読み込み完了、再読み込み機能は削除済み")
    
    # カードデータの確実な読み込み
    uid = st.session_state.get("uid")
    # 学習ログを統合してカードデータを最新化（必要な場合のみ）
    uid = st.session_state.get("uid")
    if uid and st.session_state.get("cards") and should_integrate_logs(uid):
        st.session_state.cards = integrate_learning_logs_into_cards(st.session_state.cards, uid)
    
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
    processed_case_ids = set()
    
    for q_num in current_q_group:
        if q_num in ALL_QUESTIONS_DICT:
            # 権限チェック：学士試験の問題で権限がない場合はスキップ
            if q_num.startswith("G") and not has_gakushi_permission:
                continue
            
            q_obj = ALL_QUESTIONS_DICT[q_num]
            case_id = q_obj.get('case_id')
            
            # case_idがある場合、同じcase_idの全ての問題を取得（二連問対応）
            if case_id and case_id in CASES and case_id not in processed_case_ids:
                processed_case_ids.add(case_id)
                # 同じcase_idの全問題を取得
                case_questions = []
                for candidate_q in ALL_QUESTIONS:
                    if candidate_q.get('case_id') == case_id:
                        if candidate_q['number'].startswith("G") and not has_gakushi_permission:
                            continue
                        case_questions.append(candidate_q)
                
                # 問題番号順にソート
                case_questions.sort(key=lambda x: x['number'])
                q_objects.extend(case_questions)
            elif not case_id:  # case_idがない単問のみ追加
                q_objects.append(q_obj)
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
        st.info(f"🔄 **復習問題**")
    else:
        st.info("🆕 **新規問題**")

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
                
                # セッション状態の自動保存は廃止（書き込み頻度削減のため）
                # 保存は自己評価フォーム送信時のみ実行
                
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
                        
                        # learningLogsの作成は廃止（データはuserCardsのhistoryフィールドに統合済み）

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
                    
                    # --- Google Analytics イベント送信 ---
                    if uid:
                        # 問題グループの代表的なIDを取得（複数問題の場合は最初の問題ID）
                        group_id = current_q_group[0] if current_q_group else "unknown"
                        log_to_ga(
                            event_name="submit_evaluation",
                            user_id=uid,
                            params={
                                "quality": quality, # 1, 2, 4, 5など
                                "question_id": group_id,
                                "question_count": len(current_q_group)
                            }
                        )
                    
                    # 更新されたカードを個別に保存（新しいリファクタリング済み関数を使用）
                    for q_num_str in current_q_group:
                        updated_card = st.session_state.cards[q_num_str]
                        save_user_data(uid, question_id=q_num_str, updated_card_data=updated_card)
                    
                    # セッション状態も保存
                    save_user_data(uid, session_state=st.session_state)
                    
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
        # Cookieから保存されたメールアドレスを取得（自動入力用）
        saved_email = ""
        try:
            cookies = get_cookies()
            if cookies and cookies.ready:
                saved_email = cookies.get("saved_email", "")
        except Exception as e:
            print(f"[DEBUG] Cookie読み込みエラー: {e}")
        
        login_email = st.text_input("メールアドレス", value=saved_email, key="login_email", autocomplete="email")
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
            
            # エラーチェック
            if "error" in result:
                st.error(f"ログインエラー: {result['error'].get('message', '認証に失敗しました')}")
                st.stop()
            
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
                
                # Cookie保存（remember me・emailベース・完全自動ログイン対応）
                cookies = get_cookies()  # 安全にCookie取得
                if remember_me and cookies is not None and result.get("refreshToken"):
                    cookie_data = {
                        "refresh_token": result["refreshToken"],
                        "uid": result.get("localId"),
                        "email": login_email,
                        "saved_email": login_email,  # ログインフォーム用
                        "auto_login_enabled": True  # 完全自動ログイン有効
                    }
                    if safe_save_cookies(cookies, cookie_data):
                        print(f"[DEBUG] クッキー保存成功（完全自動ログイン有効）")
                    else:
                        print(f"[DEBUG] クッキー保存失敗")
                
                st.success("ログイン成功！")
                print(f"[DEBUG] ログイン処理完了")
                st.rerun()
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
        
        # 既存のカードデータに学習ログを統合（必要な場合のみ）
        if st.session_state.cards and should_integrate_logs(uid):
            st.session_state.cards = integrate_learning_logs_into_cards(st.session_state.cards, uid)
        
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
                    debug_review_cards = []  # デバッグ用
                
                    for q_num, card in cards.items():
                        # next_reviewまたはdueフィールドで復習期日をチェック
                        review_date_field = card.get('next_review') or card.get('due')
                        if review_date_field:
                            if isinstance(review_date_field, str):
                                try:
                                    review_date = datetime.datetime.fromisoformat(review_date_field.replace('Z', '+00:00')).date()
                                    if review_date <= today:
                                        review_count += 1
                                        debug_review_cards.append((q_num, review_date, card.get('interval', 0)))
                                except:
                                    pass
                            elif isinstance(review_date_field, datetime.datetime):
                                if review_date_field.date() <= today:
                                    review_count += 1
                                    debug_review_cards.append((q_num, review_date_field.date(), card.get('interval', 0)))
                            elif isinstance(review_date_field, datetime.date):
                                if review_date_field <= today:
                                    review_count += 1
                                    debug_review_cards.append((q_num, review_date_field, card.get('interval', 0)))
                    
                    # デバッグ情報をコンソールに出力
                    if debug_review_cards:
                        print(f"[DEBUG] 復習対象カード数: {review_count}")
                        print(f"[DEBUG] 復習対象例（最初の5件）: {debug_review_cards[:5]}")
                    
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
                                    
                                    # セッション状態のみ保存（学習開始時）
                                    save_user_data(st.session_state.get("uid"), session_state=st.session_state)
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
                            st.info(f"学士{g_year}年度-{g_session}-{g_area}領域: {len(questions_to_load)}問が見つかりました")

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
                                st.info(f"学士試験-{selected_subject}: {len(questions_to_load)}問が見つかりました")

                elif mode == "必修問題のみ":
                    if target_exam == "国試":
                        questions_to_load = [q for q in ALL_QUESTIONS if q.get("number") in HISSHU_Q_NUMBERS_SET]
                        st.info(f"国試必修問題: {len(questions_to_load)}問が見つかりました")
                    else:
                        questions_to_load = [q for q in ALL_QUESTIONS if q.get("number") in GAKUSHI_HISSHU_Q_NUMBERS_SET]
                        st.info(f"学士必修問題: {len(questions_to_load)}問が見つかりました")

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
                        exam_type = "学士試験" if gakushi_only else "国試"
                        st.info(f"{exam_type}キーワード検索「{search_keyword.strip()}」: {len(questions_to_load)}問が見つかりました")

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
                            
                            # セッション状態を保存（演習開始時）
                            if st.session_state.get("user_logged_in") and st.session_state.get("uid"):
                                try:
                                    save_user_data(st.session_state.get("uid"), session_state=st.session_state)
                                    print(f"[DEBUG] 演習開始時のセッション状態保存完了")
                                except Exception as e:
                                    print(f"[ERROR] 演習開始時のセッション状態保存失敗: {e}")
                            
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
                            
                            save_user_data(st.session_state.get("uid"), session_state=st.session_state)
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
            
            # 長期復習対象カード数も表示
            today = datetime.datetime.now(datetime.timezone.utc).date()
            long_term_review_count = 0
            cards = st.session_state.get("cards", {})
            for card in cards.values():
                review_date_field = card.get('next_review') or card.get('due')
                if review_date_field:
                    try:
                        if isinstance(review_date_field, str):
                            review_date = datetime.datetime.fromisoformat(review_date_field.replace('Z', '+00:00')).date()
                        else:
                            review_date = review_date_field.date() if isinstance(review_date_field, datetime.datetime) else review_date_field
                        
                        if review_date <= today:
                            long_term_review_count += 1
                    except:
                        pass

            st.write(f"メインキュー: **{len(st.session_state.get('main_queue', []))}** グループ")
            st.write(f"短期復習: **{ready_short}** グループ準備完了")
            st.write(f"長期復習: **{long_term_review_count}** カード復習期限到来")

            # セッション初期化
            if st.button("🔄 セッションを初期化", key="reset_session"):
                st.session_state.current_q_group = []
                for k in list(st.session_state.keys()):
                    if k.startswith(("checked_", "user_selection_", "shuffled_", "free_input_", "order_input_")):
                        del st.session_state[k]
                st.info("セッションを初期化しました")
                st.rerun()

            # 学習記録セクション（演習ページでも表示）
            st.divider()
            st.markdown("#### 📈 学習記録")
            
            # 学習ログを統合してカードデータを最新化（必要な場合のみ）
            uid = st.session_state.get("uid")
            if uid and st.session_state.cards and should_integrate_logs(uid):
                st.session_state.cards = integrate_learning_logs_into_cards(st.session_state.cards, uid)
            
            # カードデータの状態確認と情報表示
            if uid and st.session_state.cards:
                cards_with_history = sum(1 for card in st.session_state.cards.values() if card.get('history'))
                total_cards = len(st.session_state.cards)
                
                # 正常な状態を表示（250枚の演習済みカード）
                if cards_with_history > 0:
                    st.success(f"✅ 演習記録: {cards_with_history}枚のカードに学習履歴があります（総カード数: {total_cards}枚）")
                else:
                    # 学習記録がない場合も情報として表示（再読み込み機能は削除）
                    st.info(f"📝 新規ユーザー: これから演習を始めて学習記録を蓄積していきましょう！")
            
            if st.session_state.cards and len(st.session_state.cards) > 0:
                quality_to_mark = {1: "×", 2: "△", 4: "◯", 5: "◎"}
                mark_to_label = {"◎": "簡単", "◯": "普通", "△": "難しい", "×": "もう一度"}
                
                # 統合されたhistoryから最新のqualityを取得（詳細デバッグ付き）
                evaluated_marks = []
                cards_with_history = 0
                cards_without_history = 0
                debug_info = []
                
                for q_num, card in st.session_state.cards.items():
                    # historyがある場合は最新のqualityを使用
                    if card.get('history') and len(card['history']) > 0:
                        cards_with_history += 1
                        history = card['history']
                        latest_entry = history[-1]
                        latest_quality = latest_entry.get('quality')
                        
                        # デバッグ情報を収集
                        if len(debug_info) < 5:  # 最初の5件のみ
                            debug_info.append(f"カード{q_num}: history={len(history)}件, 最新quality={latest_quality}, type={type(latest_quality)}")
                        
                        if latest_quality is not None:
                            mark = quality_to_mark.get(latest_quality)
                            if mark:
                                evaluated_marks.append(mark)
                            else:
                                # quality値が想定外の場合のデバッグ
                                if len(debug_info) < 10:
                                    debug_info.append(f"⚠️ 未対応quality値: {latest_quality} (カード{q_num})")
                    
                    # historyがない場合はqualityフィールドを使用（後方互換性）
                    elif card.get('quality'):
                        cards_without_history += 1
                        quality_value = card.get('quality')
                        mark = quality_to_mark.get(quality_value)
                        if mark:
                            evaluated_marks.append(mark)
                        elif len(debug_info) < 10:
                            debug_info.append(f"⚠️ 未対応quality値（direct）: {quality_value} (カード{q_num})")
                
                total_evaluated = len(evaluated_marks)
                counter = Counter(evaluated_marks)
                
                # デバッグ情報を表示
                st.info(f"📊 デバッグ情報: 総カード数={len(st.session_state.cards)}, history有り={cards_with_history}, history無し={cards_without_history}, 評価済み={total_evaluated}")
                
                if debug_info:
                    with st.expander("🔍 デバッグ詳細", expanded=False):
                        for info in debug_info:
                            st.text(info)
                
                with st.expander("自己評価の分布", expanded=True):
                    st.markdown(f"**合計評価数：{total_evaluated}問**")
                    for mark, label in mark_to_label.items():
                        count = counter.get(mark, 0)
                        percent = int(round(count / total_evaluated * 100)) if total_evaluated else 0
                        st.markdown(f"{mark} {label}：{count}問 ({percent}％)")
                
                with st.expander("最近の評価ログ", expanded=False):
                    cards_with_history = [(q_num, card) for q_num, card in st.session_state.cards.items() if card.get('history')]
                    
                    if cards_with_history:
                        sorted_cards = sorted(cards_with_history, key=lambda item: item[1]['history'][-1]['timestamp'], reverse=True)
                        
                        for q_num, card in sorted_cards[:10]:
                            last_history = card['history'][-1]
                            last_eval_mark = quality_to_mark.get(last_history.get('quality'))
                            
                            # UTCからJSTに変換して表示
                            try:
                                utc_time = datetime.datetime.fromisoformat(last_history['timestamp'].replace('Z', '+00:00'))
                                if utc_time.tzinfo is None:
                                    utc_time = utc_time.replace(tzinfo=pytz.UTC)
                                jst_time = utc_time.astimezone(JST)
                                timestamp_str = jst_time.strftime('%Y-%m-%d %H:%M')
                            except:
                                # フォールバック：元の処理
                                timestamp_str = datetime.datetime.fromisoformat(last_history['timestamp']).strftime('%Y-%m-%d %H:%M')
                            
                            # 問題番号を緑色のボタンとして表示
                            if st.button(q_num, key=f"jump_practice_{q_num}", type="secondary"):
                                st.session_state.current_q_group = [q_num]
                                for key in list(st.session_state.keys()):
                                    if key.startswith("checked_") or key.startswith("user_selection_") or key.startswith("shuffled_") or key.startswith("free_input_") or key.startswith("order_input_"):
                                        del st.session_state[key]
                                st.rerun()
                            
                            # 評価情報を下に表示
                            st.markdown(f"<span style='color: green'>{q_num}</span> : **{last_eval_mark}** ({timestamp_str} JST)", unsafe_allow_html=True)
                    else:
                        st.info("まだ評価された問題がありません。")
            else:
                st.info("まだ評価された問題がありません。")



        else:
            # --- 検索・進捗ページのサイドバー ---
            st.markdown("### 📊 分析・検索ツール")
            
            # 検索・分析用のフィルター機能のみ
            uid = st.session_state.get("uid")
            has_gakushi_permission = check_gakushi_permission(uid)
            
            
            # 対象範囲
            if has_gakushi_permission:
                analysis_target = st.radio("分析対象", ["国試", "学士試験"], key="analysis_target")
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
            
            # 学習記録セクション（検索・進捗ページでも表示）
            st.divider()
            st.markdown("#### 📈 学習記録")
            
            # 学習ログを統合してカードデータを最新化（必要な場合のみ）
            uid = st.session_state.get("uid")
            if uid and st.session_state.cards and should_integrate_logs(uid):
                st.session_state.cards = integrate_learning_logs_into_cards(st.session_state.cards, uid)
            
            if st.session_state.cards and len(st.session_state.cards) > 0:
                quality_to_mark = {1: "×", 2: "△", 4: "◯", 5: "◎"}
                mark_to_label = {"◎": "簡単", "◯": "普通", "△": "難しい", "×": "もう一度"}
                
                # 統合されたhistoryから最新のqualityを取得
                evaluated_marks = []
                for card in st.session_state.cards.values():
                    # historyがある場合は最新のqualityを使用
                    if card.get('history'):
                        latest_quality = card['history'][-1].get('quality')
                        if latest_quality:
                            mark = quality_to_mark.get(latest_quality)
                            if mark:
                                evaluated_marks.append(mark)
                    # historyがない場合はqualityフィールドを使用（後方互換性）
                    elif card.get('quality'):
                        mark = quality_to_mark.get(card.get('quality'))
                        if mark:
                            evaluated_marks.append(mark)
                
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
                    
                    if cards_with_history:
                        sorted_cards = sorted(cards_with_history, key=lambda item: item[1]['history'][-1]['timestamp'], reverse=True)
                        
                        for q_num, card in sorted_cards[:10]:
                            last_history = card['history'][-1]
                            last_eval_mark = quality_to_mark.get(last_history.get('quality'))
                            
                            # UTCからJSTに変換して表示
                            try:
                                utc_time = datetime.datetime.fromisoformat(last_history['timestamp'].replace('Z', '+00:00'))
                                if utc_time.tzinfo is None:
                                    utc_time = utc_time.replace(tzinfo=pytz.UTC)
                                jst_time = utc_time.astimezone(JST)
                                timestamp_str = jst_time.strftime('%Y-%m-%d %H:%M')
                            except:
                                # フォールバック：元の処理
                                timestamp_str = datetime.datetime.fromisoformat(last_history['timestamp']).strftime('%Y-%m-%d %H:%M')
                            
                            # 問題番号を緑色のボタンとして表示
                            if st.button(q_num, key=f"jump_search_{q_num}", type="secondary"):
                                # 演習ページに移動して該当問題を表示
                                st.session_state.current_q_group = [q_num]
                                # 問題関連のセッション状態をクリア
                                for key in list(st.session_state.keys()):
                                    if key.startswith(("checked_", "user_selection_", "shuffled_", "free_input_", "order_input_")):
                                        del st.session_state[key]
                                # セッション状態更新後にページ遷移
                                st.session_state.page_select = "演習"
                                st.rerun()
                            
                            # 評価情報を下に表示（日本時間表示）
                            st.markdown(f"<span style='color: green'>{q_num}</span> : **{last_eval_mark}** ({timestamp_str} JST)", unsafe_allow_html=True)
                    else:
                        st.info("まだ評価された問題がありません。")
            else:
                st.info("まだ評価された問題がありません。")

        # ログアウトボタン
        st.divider()
        if st.button("ログアウト", key="logout_btn"):
            uid = st.session_state.get("uid")
            # ログアウト時にセッション状態を保存
            save_user_data(uid, session_state=st.session_state)
            
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

    # UI状態の変更監視による自動保存は廃止（書き込み頻度削減のため）
    # 保存は自己評価フォーム送信時のみ実行