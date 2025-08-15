import streamlit as st
import json
import os
import random
import datetime
import re
from collections import Counter
import firebase_admin
from firebase_admin import credentials, firestore
from firebase_admin import storage
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
            st.session_state.cookie_manager = EncryptedCookieManager(
                prefix="dentai_",
                password=cookie_password
            )
            print(f"[DEBUG] Cookie manager作成完了")
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
                return cookies
            except Exception as e:
                print(f"[DEBUG] Cookie access error during get: {str(e)}")
                return None
        else:
            return None
    
    # 初回のみ初期化を試行
    st.session_state.cookie_init_attempted = True
    try:
        cookies = get_cookie_manager()
        if cookies is not None:
            # 準備完了まで待機
            try:
                if hasattr(cookies, '_ready'):
                    if not cookies._ready:
                        print("[DEBUG] Cookie manager created but not ready")
                        return None
                # 簡単なアクセステストを行う
                _ = cookies.get("test", None)
                st.session_state.cookie_manager = cookies
                print("[DEBUG] Cookie manager ready and functional")
                return cookies
            except Exception as e:
                print(f"[DEBUG] Cookie readiness test failed: {str(e)}")
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

def is_token_expired(token_timestamp, expires_in=3600):
    """トークンが期限切れかどうかをチェック（デフォルト1時間だが、30分でリフレッシュ）"""
    if not token_timestamp:
        return True
    now = datetime.datetime.now(datetime.timezone.utc)
    token_time = datetime.datetime.fromisoformat(token_timestamp)
    # 30分（1800秒）で期限切れとして扱い、余裕を持ってリフレッシュ
    return (now - token_time).total_seconds() > 1800

def try_auto_login_from_cookie():
    """クッキーからの自動ログイン（超高速版）"""
    import time
    start = time.time()
    
    # Cookie取得（安全に）
    cookies = get_cookies()
    
    # 早期リターン条件（Noneチェック）
    if cookies is None or st.session_state.get("user_logged_in"):
        print(f"[DEBUG] try_auto_login_from_cookie - 早期リターン: {time.time() - start:.3f}s")
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
            print(f"[DEBUG] Cookie access error during get: {e}")
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
    """セッションが有効かチェックし、必要に応じてトークンをリフレッシュ"""
    if not st.session_state.get("user_logged_in"):
        return False
    
    token_timestamp = st.session_state.get("token_timestamp")
    refresh_token = st.session_state.get("refresh_token")
    
    # トークンが期限切れの場合はリフレッシュを試行
    if is_token_expired(token_timestamp) and refresh_token:
        refresh_result = firebase_refresh_token(refresh_token)
        if refresh_result:
            # トークンの更新
            st.session_state["id_token"] = refresh_result["idToken"]
            st.session_state["refresh_token"] = refresh_result["refreshToken"]
            st.session_state["token_timestamp"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            return True
        else:
            # リフレッシュに失敗した場合はログアウト
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
    """ログイン時に必要最小限のデータのみ読み込む軽量版（UIDベース＋emailメタデータ）"""
    import time
    start = time.time()
    
    if not ensure_valid_session():
        print(f"[DEBUG] load_user_data_minimal - セッション無効: {time.time() - start:.3f}s")
        return {"cards": {}, "new_cards_per_day": 10}

    # UIDを主キーとして使用（Firebase推奨方式）
    uid = st.session_state.get("uid")
    email = st.session_state.get("email")
    
    if uid:
        db = get_db()  # 安全にDB取得
        if db:
            try:
                # デバッグ: Firebaseプロジェクト情報を表示
                project_id = getattr(db, "project", "unknown")
                print(f"[DEBUG] Firebase接続先プロジェクト: {project_id}")
                print(f"[DEBUG] UID: {uid}, Email: {email}")
                
                # UIDベースでデータ検索
                doc_ref = db.collection("user_progress").document(uid)
                doc = doc_ref.get(timeout=10)
                
                if doc.exists:
                    data = doc.to_dict()
                    # emailメタデータを更新（管理のため）
                    if email and data.get("email") != email:
                        doc_ref.update({"email": email, "last_login": datetime.datetime.now(datetime.timezone.utc).isoformat()})
                        print(f"[DEBUG] emailメタデータ更新: {email}")
                    
                    result = {
                        "cards": data.get("cards", {}),
                        "new_cards_per_day": data.get("new_cards_per_day", 10),
                    }
                    print(f"[DEBUG] load_user_data_minimal - 成功: {time.time() - start:.3f}s, カード数: {len(result['cards'])}")
                    return result
                else:
                    # UIDでデータが見つからない場合、emailベースの旧データを検索・移行
                    print(f"[DEBUG] load_user_data_minimal - UIDでデータなし、emailベース旧データを検索: {email}")
                    print(f"[DEBUG] 検索対象UID: {uid}")
                    
                    # 既にマイグレーション済みかチェック
                    if email:
                        email_doc_ref = db.collection("user_progress").document(email)
                        email_doc = email_doc_ref.get(timeout=10)
                        if email_doc.exists:
                            email_data = email_doc.to_dict()
                            if email_data.get("migrated_to_uid") == uid:
                                print(f"[DEBUG] マイグレーション済みだが、UIDドキュメントが見つからない。再作成を試行。")
                                # マイグレーション済みだが、UIDドキュメントが消失している場合の対処
                                new_data = {
                                    "cards": email_data.get("cards", {}),
                                    "new_cards_per_day": email_data.get("new_cards_per_day", 10),
                                    "email": email,
                                    "migrated_from": email,
                                    "migrated_at": email_data.get("migrated_at", datetime.datetime.now(datetime.timezone.utc).isoformat()),
                                    "last_login": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                    "recreated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                                }
                                
                                # その他のフィールドも復元
                                for key in ["main_queue", "short_term_review_queue", "current_q_group"]:
                                    if key in email_data:
                                        new_data[key] = email_data[key]
                                
                                doc_ref.set(new_data)
                                print(f"[DEBUG] UIDドキュメント再作成完了: {len(new_data.get('cards', {}))}カード")
                                return {
                                    "cards": new_data.get("cards", {}),
                                    "new_cards_per_day": new_data.get("new_cards_per_day", 10),
                                }
                    
                    if email:
                        migrated_data = migrate_email_based_data_to_uid(db, email, uid)
                        if migrated_data:
                            print(f"[DEBUG] 旧データマイグレーション成功: {len(migrated_data.get('cards', {}))}カード")
                            return migrated_data
                        else:
                            print(f"[DEBUG] emailベース旧データ見つからず: {email}")
                    else:
                        print(f"[DEBUG] email情報なし、マイグレーション不可")
                    
                    # 新規ユーザーの場合、emailメタデータ付きで初期化
                    if email:
                        initial_data = {
                            "cards": {},
                            "new_cards_per_day": 10,
                            "email": email,
                            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                            "last_login": datetime.datetime.now(datetime.timezone.utc).isoformat()
                        }
                        doc_ref.set(initial_data)
                        print(f"[DEBUG] 新規ユーザー初期化: {email}")
                        return {"cards": {}, "new_cards_per_day": 10}
                        
            except Exception as e:
                print(f"[DEBUG] load_user_data_minimal - エラー: {e}, 時間: {time.time() - start:.3f}s")
    
    print(f"[DEBUG] load_user_data_minimal - デフォルト: {time.time() - start:.3f}s")
    return {"cards": {}, "new_cards_per_day": 10}

def migrate_email_based_data_to_uid(db, email, uid):
    """emailベースの旧データをUIDベースに移行する"""
    try:
        print(f"[DEBUG] マイグレーション開始: {email} -> {uid}")
        
        # emailをドキュメントIDとして使用していた旧データを検索
        email_doc_ref = db.collection("user_progress").document(email)
        email_doc = email_doc_ref.get(timeout=10)
        
        if email_doc.exists:
            old_data = email_doc.to_dict()
            print(f"[DEBUG] 旧emailベースデータ発見:")
            print(f"[DEBUG]   - カード数: {len(old_data.get('cards', {}))}")
            print(f"[DEBUG]   - main_queue: {len(old_data.get('main_queue', []))}")
            print(f"[DEBUG]   - 新規カード/日: {old_data.get('new_cards_per_day', 10)}")
            print(f"[DEBUG]   - その他のキー: {list(old_data.keys())}")
            
            # UIDベースの新しいドキュメントに移行
            new_data = {
                "cards": old_data.get("cards", {}),
                "new_cards_per_day": old_data.get("new_cards_per_day", 10),
                "email": email,
                "migrated_from": email,
                "migrated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "last_login": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }
            
            # その他のフィールドも移行
            for key in ["main_queue", "short_term_review_queue", "current_q_group"]:
                if key in old_data:
                    new_data[key] = old_data[key]
                    print(f"[DEBUG]   - {key} を移行: {type(old_data[key])}")
            
            # 新しいUIDドキュメントに保存
            uid_doc_ref = db.collection("user_progress").document(uid)
            uid_doc_ref.set(new_data)
            print(f"[DEBUG] UIDドキュメント作成完了: {uid}")
            
            # 旧データに移行済みマークを付けて保持（バックアップとして）
            email_doc_ref.update({
                "migrated_to_uid": uid,
                "migrated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "migration_status": "completed"
            })
            
            print(f"[DEBUG] データマイグレーション完了: {email} -> {uid}")
            return {
                "cards": new_data.get("cards", {}),
                "new_cards_per_day": new_data.get("new_cards_per_day", 10),
            }
        else:
            # emailでもemailを正規化した形（ドット、@マーク変換など）での検索を試行
            normalized_email = email.replace(".", "_").replace("@", "_at_")
            print(f"[DEBUG] 正規化email検索: {normalized_email}")
            normalized_doc_ref = db.collection("user_progress").document(normalized_email)
            normalized_doc = normalized_doc_ref.get(timeout=10)
            
            if normalized_doc.exists:
                old_data = normalized_doc.to_dict()
                print(f"[DEBUG] 正規化email旧データ発見:")
                print(f"[DEBUG]   - カード数: {len(old_data.get('cards', {}))}")
                print(f"[DEBUG]   - その他のキー: {list(old_data.keys())}")
                
                # 同様の移行処理
                new_data = {
                    "cards": old_data.get("cards", {}),
                    "new_cards_per_day": old_data.get("new_cards_per_day", 10),
                    "email": email,
                    "migrated_from": normalized_email,
                    "migrated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "last_login": datetime.datetime.now(datetime.timezone.utc).isoformat()
                }
                
                # その他のフィールドも移行
                for key in ["main_queue", "short_term_review_queue", "current_q_group"]:
                    if key in old_data:
                        new_data[key] = old_data[key]
                
                uid_doc_ref = db.collection("user_progress").document(uid)
                uid_doc_ref.set(new_data)
                
                normalized_doc_ref.update({
                    "migrated_to_uid": uid,
                    "migrated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "migration_status": "completed"
                })
                
                print(f"[DEBUG] 正規化データマイグレーション完了: {normalized_email} -> {uid}")
                return {
                    "cards": new_data.get("cards", {}),
                    "new_cards_per_day": new_data.get("new_cards_per_day", 10),
                }
            
        print(f"[DEBUG] emailベース旧データなし: {email}")
        return None
        
    except Exception as e:
        print(f"[DEBUG] データマイグレーションエラー: {e}")
        return None

@st.cache_data(ttl=900)
def load_user_data_full(user_id, cache_buster: int = 0):
    """演習開始時に全データを読み込む完全版（UIDベース＋emailメタデータ）"""
    import time
    start = time.time()
    
    if not ensure_valid_session():
        print(f"[DEBUG] load_user_data_full - セッション無効: {time.time() - start:.3f}s")
        return {"cards": {}, "main_queue": [], "short_term_review_queue": [], "current_q_group": [], "new_cards_per_day": 10}

    # UIDを主キーとして使用
    uid = st.session_state.get("uid")
    email = st.session_state.get("email")
    
    if uid:
        db = get_db()  # 安全にDB取得
        if db:
            try:
                # UIDベースでデータ検索
                doc_ref = db.collection("user_progress").document(uid)
                doc = doc_ref.get(timeout=15)
                
                if doc.exists:
                    data = doc.to_dict()
                    main_queue_str_list = data.get("main_queue", [])
                    current_q_group_str = data.get("current_q_group", "")
                    main_queue = [item.split(',') for item in main_queue_str_list if item]
                    current_q_group = current_q_group_str.split(',') if current_q_group_str else []
                    
                    # 短期復習キューの新形式対応
                    raw = data.get("short_term_review_queue", [])
                    short_term_review_queue = []
                    now_utc = datetime.datetime.now(datetime.timezone.utc)

                    def _parse_ready_at(v):
                        if isinstance(v, datetime.datetime): return v
                        if isinstance(v, str):
                            try: return datetime.datetime.fromisoformat(v)
                            except Exception: return now_utc
                        return now_utc

                    for item in raw:
                        if isinstance(item, dict):
                            grp = item.get("group", [])
                            ra = _parse_ready_at(item.get("ready_at"))
                            short_term_review_queue.append({"group": grp, "ready_at": ra})
                        elif isinstance(item, str):
                            grp = item.split(",") if item else []
                            short_term_review_queue.append({"group": grp, "ready_at": now_utc})
                        elif isinstance(item, list):
                            short_term_review_queue.append({"group": item, "ready_at": now_utc})
                    
                    result = {
                        "cards": data.get("cards", {}),
                        "main_queue": main_queue,
                        "short_term_review_queue": short_term_review_queue,
                        "current_q_group": current_q_group,
                        "new_cards_per_day": data.get("new_cards_per_day", 10),
                    }
                    print(f"[DEBUG] load_user_data_full - 成功: {time.time() - start:.3f}s, カード数: {len(result['cards'])}")
                    return result
                else:
                    # UIDでデータが見つからない場合、emailベースの旧データを検索・移行
                    print(f"[DEBUG] load_user_data_full - UIDでデータなし、emailベース旧データを検索: {email}")
                    if email:
                        migrated_data = migrate_email_based_data_to_uid(db, email, uid)
                        if migrated_data:
                            print(f"[DEBUG] load_user_data_full - 旧データマイグレーション成功: {len(migrated_data.get('cards', {}))}カード")
                            # マイグレーションしたデータに空のキューを追加して完全版として返す
                            result = {
                                "cards": migrated_data.get("cards", {}),
                                "main_queue": [],
                                "short_term_review_queue": [],
                                "current_q_group": [],
                                "new_cards_per_day": migrated_data.get("new_cards_per_day", 10),
                            }
                            return result
                        else:
                            print(f"[DEBUG] load_user_data_full - emailベース旧データ見つからず: {email}")
                            
            except Exception as e:
                print(f"[DEBUG] load_user_data_full - エラー: {e}, 時間: {time.time() - start:.3f}s")
    
    print(f"[DEBUG] load_user_data_full - 新規ユーザー（デフォルト値を返却）: {time.time() - start:.3f}s")
    return {"cards": {}, "main_queue": [], "short_term_review_queue": [], "current_q_group": [], "new_cards_per_day": 10}

def load_user_data(user_id):
    """後方互換性のため - 軽量版を呼び出す"""
    return load_user_data_minimal(user_id)

def save_user_data(user_id, session_state):
    """user_id には UID を渡す（UIDベース＋emailメタデータ保存）"""
    def flatten_and_str(obj):
        if isinstance(obj, (list, set)):
            result = []
            for item in obj:
                result.extend(flatten_and_str(item))
            return result
        elif isinstance(obj, dict):
            return [str(k) for k in obj.keys()]
        elif obj is None:
            return []
        else:
            return [str(obj)]

    try:
        if not ensure_valid_session():
            return

        # 安全にDB取得
        db = get_db()
        if db and user_id:
            doc_ref = db.collection("user_progress").document(user_id)  # UIDを主キーとして使用
            
            payload = {
                "email": session_state.get("email"),  # emailメタデータを保存
                "last_save": datetime.datetime.now(datetime.timezone.utc).isoformat()  # 最終保存時刻
            }

            # ▼ 修正：空の cards を保存して既存を消さない
            cards_obj = session_state.get("cards", None)
            if isinstance(cards_obj, dict) and len(cards_obj) > 0:
                payload["cards"] = cards_obj
            if "main_queue" in session_state:
                payload["main_queue"] = [','.join(flatten_and_str(g)) for g in session_state.get("main_queue", [])]
            # ★ 短期復習キューの新形式保存（ready_at付きMap配列）
            if "short_term_review_queue" in session_state:
                ser = []
                for item in session_state.get("short_term_review_queue", []):
                    if isinstance(item, dict):
                        grp = item.get("group", [])
                        ra = item.get("ready_at")
                        if isinstance(ra, datetime.datetime):
                            ra = ra.isoformat()
                        ser.append({"group": [str(x) for x in grp], "ready_at": ra})
                    else:
                        # 後方互換（古い形式が残っていても壊さない）
                        grp = item if isinstance(item, list) else [str(item)]
                        ser.append({"group": grp, "ready_at": datetime.datetime.now(datetime.timezone.utc).isoformat()})
                payload["short_term_review_queue"] = ser
            if "current_q_group" in session_state:
                payload["current_q_group"] = ','.join(flatten_and_str(session_state.get("current_q_group", [])))
            if "new_cards_per_day" in session_state:
                payload["new_cards_per_day"] = session_state["new_cards_per_day"]
            doc_ref.set(payload, merge=True)
            
            # ▼ グローバル全消しは危険＆重いので削除（必要なら対象関数のキーで運用）
            # st.cache_data.clear()
            
    except Exception as e:
        print(f"[ERROR] save_user_data エラー: {e}")
        # エラーが発生してもアプリケーションを停止させない

def migrate_progress_doc_if_needed(uid: str, email: str):
    """初回ログイン時などに email Doc を UID Doc へコピー（冪等）"""
    import time
    start = time.time()

    db = get_db()  # ← 追加
    if not db or not uid or not email:
        print(f"[DEBUG] migrate_progress_doc_if_needed - 早期リターン: {time.time() - start:.3f}s")
        return
    
    # セッションで移行済みかチェック（同一セッション内での重複実行を防ぐ）
    migration_key = f"migration_done_{uid}"
    if st.session_state.get(migration_key):
        print(f"[DEBUG] migrate_progress_doc_if_needed - セッション内スキップ: {time.time() - start:.3f}s")
        return
    
    uid_check_start = time.time()
    uid_ref = db.collection("user_progress").document(uid)
    uid_exists = uid_ref.get().exists
    uid_check_time = time.time() - uid_check_start
    
    if uid_exists:
        # 移行済みマークをセッションに保存
        st.session_state[migration_key] = True
        print(f"[DEBUG] migrate_progress_doc_if_needed - UID存在確認のみ: {uid_check_time:.3f}s")
        return
    
    email_check_start = time.time()
    email_ref = db.collection("user_progress").document(email)
    snap = email_ref.get()
    email_check_time = time.time() - email_check_start
    
    if snap.exists:
        copy_start = time.time()
        uid_ref.set(snap.to_dict(), merge=True)
        copy_time = time.time() - copy_start
        
        meta_start = time.time()
        # 旧ドキュメントに移行メタ（必要なら後で削除可能）
        email_ref.set({
            "__migrated_to": uid,
            "__migrated_at": datetime.datetime.utcnow().isoformat()
        }, merge=True)
        meta_time = time.time() - meta_start
        
        total_time = time.time() - start
        print(f"[DEBUG] migrate_progress_doc_if_needed - UID確認: {uid_check_time:.3f}s, Email確認: {email_check_time:.3f}s, コピー: {copy_time:.3f}s, メタ保存: {meta_time:.3f}s, 合計: {total_time:.3f}s")
    else:
        total_time = time.time() - start
        print(f"[DEBUG] migrate_progress_doc_if_needed - データなし, 合計: {total_time:.3f}s")
    
    # 移行済みマークをセッションに保存
    st.session_state[migration_key] = True

def migrate_permission_if_needed(uid: str, email: str):
    """user_permissions も email → uid を一度だけ複製（冪等）"""
    import time
    start = time.time()

    db = get_db()  # ← 追加
    if not db or not uid or not email:
        print(f"[DEBUG] migrate_permission_if_needed - 早期リターン: {time.time() - start:.3f}s")
        return
    
    # セッションで移行済みかチェック（同一セッション内での重複実行を防ぐ）
    permission_key = f"permission_migration_done_{uid}"
    if st.session_state.get(permission_key):
        print(f"[DEBUG] migrate_permission_if_needed - セッション内スキップ: {time.time() - start:.3f}s")
        return
    
    src_check_start = time.time()
    src = db.collection("user_permissions").document(email).get()
    src_check_time = time.time() - src_check_start
    
    if src.exists:
        dst_check_start = time.time()
        dst = db.collection("user_permissions").document(uid)
        dst_exists = dst.get().exists
        dst_check_time = time.time() - dst_check_start
        
        if not dst_exists:
            copy_start = time.time()
            dst.set(src.to_dict(), merge=True)
            copy_time = time.time() - copy_start
            
            total_time = time.time() - start
            print(f"[DEBUG] migrate_permission_if_needed - Email確認: {src_check_time:.3f}s, UID確認: {dst_check_time:.3f}s, コピー: {copy_time:.3f}s, 合計: {total_time:.3f}s")
        else:
            total_time = time.time() - start
            print(f"[DEBUG] migrate_permission_if_needed - すでに存在, 合計: {total_time:.3f}s")
    else:
        total_time = time.time() - start
        print(f"[DEBUG] migrate_permission_if_needed - データなし, 合計: {total_time:.3f}s")
    
    # 移行済みマークをセッションに保存
    st.session_state[permission_key] = True

# ユーザー権限チェック（キャッシュを復活）
@st.cache_data(ttl=300)  # 5分間キャッシュ
def check_gakushi_permission(user_id):
    """
    Firestoreのuser_permissionsコレクションから権限を判定。
    can_access_gakushi: trueならTrue, それ以外はFalse
    UIDベース管理＋emailメタデータ併用＋旧データマイグレーション対応
    """
    db = get_db()  # 安全にDB取得
    if not db:
        return False
    
    # UIDを主キーとして使用
    uid = st.session_state.get("uid")
    email = st.session_state.get("email")
    
    if not uid:
        return False
    
    doc_ref = db.collection("user_permissions").document(uid)
    doc = doc_ref.get()
    if doc.exists:
        data = doc.to_dict()
        # emailメタデータも更新
        if email and data.get("email") != email:
            doc_ref.update({"email": email})
        print(f"[DEBUG] 学士権限チェック(UID): {bool(data.get('can_access_gakushi', False))}")
        return bool(data.get("can_access_gakushi", False))
    else:
        # UIDで権限が見つからない場合、emailベースの旧権限を検索・移行
        print(f"[DEBUG] UID権限なし、emailベース権限検索: {email}")
        if email:
            # 直接email検索
            email_doc_ref = db.collection("user_permissions").document(email)
            email_doc = email_doc_ref.get()
            if email_doc.exists:
                old_data = email_doc.to_dict()
                print(f"[DEBUG] 旧email権限発見:")
                print(f"[DEBUG]   - can_access_gakushi: {old_data.get('can_access_gakushi', False)}")
                print(f"[DEBUG]   - 権限データ: {old_data}")
                
                # 権限をUIDベースに移行
                new_permission_data = {
                    "can_access_gakushi": old_data.get("can_access_gakushi", False),
                    "email": email,
                    "migrated_from": email,
                    "migrated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                }
                
                # その他の権限フィールドも移行
                for key, value in old_data.items():
                    if key not in ["email", "migrated_from", "migrated_at", "migrated_to_uid"]:
                        new_permission_data[key] = value
                
                doc_ref.set(new_permission_data)
                
                # 旧データに移行済みマーク
                email_doc_ref.update({
                    "migrated_to_uid": uid,
                    "migrated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                })
                
                print(f"[DEBUG] 権限マイグレーション完了: {bool(old_data.get('can_access_gakushi', False))}")
                return bool(old_data.get("can_access_gakushi", False))
            else:
                # 正規化されたemail形式でも検索
                normalized_email = email.replace(".", "_").replace("@", "_at_")
                print(f"[DEBUG] 正規化email権限検索: {normalized_email}")
                normalized_doc_ref = db.collection("user_permissions").document(normalized_email)
                normalized_doc = normalized_doc_ref.get()
                if normalized_doc.exists:
                    old_data = normalized_doc.to_dict()
                    print(f"[DEBUG] 正規化email権限発見: {old_data}")
                    
                    new_permission_data = {
                        "can_access_gakushi": old_data.get("can_access_gakushi", False),
                        "email": email,
                        "migrated_from": normalized_email,
                        "migrated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                    }
                    
                    # その他の権限フィールドも移行
                    for key, value in old_data.items():
                        if key not in ["email", "migrated_from", "migrated_at", "migrated_to_uid"]:
                            new_permission_data[key] = value
                    
                    doc_ref.set(new_permission_data)
                    normalized_doc_ref.update({
                        "migrated_to_uid": uid,
                        "migrated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                    })
                    
                    print(f"[DEBUG] 正規化権限マイグレーション完了: {bool(old_data.get('can_access_gakushi', False))}")
                    return bool(old_data.get("can_access_gakushi", False))
    
    print(f"[DEBUG] 学士権限なし")
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
            if card.get("n") is not None or card.get("history"):
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
        bucket = storage.bucket()
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
        default_bucket = storage.bucket()
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

def export_questions_to_latex(questions):
    """
    検索結果をLaTeX形式でPDF生成可能な完全なドキュメントとして書き出す関数
    """
    header = r"""\documentclass[11pt,a4paper]{ujarticle}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{amsmath,amssymb}
\usepackage[most]{tcolorbox}
\usepackage{geometry}
\usepackage{fancyhdr}
\usepackage{lastpage}
\usepackage{enumitem}

% ページ設定
\geometry{left=20mm,right=20mm,top=25mm,bottom=25mm}

% ヘッダー・フッター設定
\pagestyle{fancy}
\fancyhf{}
\fancyhead[L]{歯科医師国家試験問題集}
\fancyhead[R]{\today}
\fancyfoot[C]{\thepage\ / \pageref{LastPage}}

% タイトル
\title{歯科医師国家試験 検索結果問題集}
\author{Dental DX PoC System}
\date{\today}

\begin{document}
\maketitle

\section{検索結果一覧}
以下の問題が検索結果として抽出されました。

"""
    
    body = []
    for i, q in enumerate(questions, 1):
        num = q.get("number", f"問題{i}")
        subject = q.get("subject", "未分類")
        question_text = (q.get("question", "") or "")
        
        # LaTeX特殊文字をエスケープ
        question_text = question_text.replace("&", r"\&")
        question_text = question_text.replace("%", r"\%")
        question_text = question_text.replace("$", r"\$")
        question_text = question_text.replace("#", r"\#")
        question_text = question_text.replace("_", r"\_")
        question_text = question_text.replace("{", r"\{")
        question_text = question_text.replace("}", r"\}")
        question_text = question_text.replace("^", r"\textasciicircum")
        question_text = question_text.replace("~", r"\textasciitilde")
        question_text = question_text.replace("\\", r"\textbackslash")
        
        body.append(rf"\subsection{{{num} - {subject}}}")
        body.append(r"\begin{tcolorbox}[colback=blue!5!white,colframe=blue!75!black,title=問題文]")
        body.append(question_text)
        body.append(r"\end{tcolorbox}")
        
        if q.get("choices"):
            body.append(r"\begin{tcolorbox}[colback=gray!5!white,colframe=gray!75!black,title=選択肢]")
            body.append(r"\begin{enumerate}[label=\Alph*.]")
            for ch in q["choices"]:
                choice_text = ch.get("text", str(ch)) if isinstance(ch, dict) else str(ch)
                # LaTeX特殊文字をエスケープ
                choice_text = choice_text.replace("&", r"\&")
                choice_text = choice_text.replace("%", r"\%")
                choice_text = choice_text.replace("$", r"\$")
                choice_text = choice_text.replace("#", r"\#")
                choice_text = choice_text.replace("_", r"\_")
                choice_text = choice_text.replace("{", r"\{")
                choice_text = choice_text.replace("}", r"\}")
                choice_text = choice_text.replace("^", r"\textasciicircum")
                choice_text = choice_text.replace("~", r"\textasciitilde")
                choice_text = choice_text.replace("\\", r"\textbackslash")
                body.append(r"\item " + choice_text)
            body.append(r"\end{enumerate}")
            body.append(r"\end{tcolorbox}")
        
        body.append(r"\vspace{1em}")
        
        # ページ区切り（5問ごと）
        if i % 5 == 0 and i < len(questions):
            body.append(r"\newpage")
    
    footer = r"""
\end{document}"""
    
    return header + "\n".join(body) + footer

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
    st.markdown("### 📊 検索・分析ツール")
    st.markdown("キーワード検索と学習状況の分析が行えます。")
    
    # サイドバーのフィルター設定を取得
    uid = st.session_state.get("uid")
    has_gakushi_permission = check_gakushi_permission(uid)
    analysis_target = st.session_state.get("analysis_target", "国試")
    level_filter = st.session_state.get("level_filter", ["未学習", "レベル0", "レベル1", "レベル2", "レベル3", "レベル4", "レベル5", "習得済み"])
    
    # 学習進捗の可視化セクションを追加
    st.subheader("📈 学習進捗の可視化")
    
    # 学習データの準備
    cards = st.session_state.get("cards", {})
    
    # 分析対象に応じたフィルタリング
    filtered_data = []
    for q in ALL_QUESTIONS:
        q_num = q.get("number", "")
        # 権限チェック
        if q_num.startswith("G") and not has_gakushi_permission:
            continue
        if analysis_target == "学士試験" and not q_num.startswith("G"):
            continue
        if analysis_target == "国試" and q_num.startswith("G"):
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
        
        # 必修問題チェック
        if analysis_target == "学士試験":
            is_hisshu = q_num in GAKUSHI_HISSHU_Q_NUMBERS_SET
        else:
            is_hisshu = q_num in HISSHU_Q_NUMBERS_SET
        
        filtered_data.append({
            "id": q_num,
            "subject": q.get("subject", "未分類"),
            "level": level,
            "ef": card.get("ef", 2.5),
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
    
    # 3タブ構成の可視化
    tab1, tab2, tab3 = st.tabs(["概要", "グラフ分析", "問題リストと絞り込み"])
    
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
            st.markdown("##### 日々の学習量（過去90日間）")
            review_history = []
            for history_list in filtered_df["history"]:
                for review in history_list:
                    if isinstance(review, dict) and "timestamp" in review:
                        review_history.append(datetime.datetime.fromisoformat(review["timestamp"]).date())
            
            if review_history:
                from collections import Counter
                review_counts = Counter(review_history)
                ninety_days_ago = datetime.date.today() - datetime.timedelta(days=90)
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
        st.subheader("問題リストと絞り込み")
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
    
    st.divider()

    # キーワード検索フォーム（独立したセクション）
    st.subheader("🔍 キーワード検索")
    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        search_keyword = st.text_input("検索キーワード", placeholder="検索したいキーワードを入力", key="search_keyword_input")
    with col2:
        search_target = st.selectbox("検索対象", ["全体", "学士試験"], key="search_target_select")
    with col3:
        shuffle_results = st.checkbox("結果をシャッフル", key="shuffle_checkbox")
    
    search_btn = st.button("検索実行", type="primary", use_container_width=True)
    
    # キーワード検索の実行と結果表示
    if search_btn and search_keyword.strip():
        gakushi_only = (analysis_target == "学士試験")
        
        # キーワード検索を実行
        search_words = [word.strip() for word in search_keyword.strip().split() if word.strip()]
        
        keyword_results = []
        for q in ALL_QUESTIONS:
            # 権限チェック：学士試験の問題で権限がない場合はスキップ
            question_number = q.get('number', '')
            if question_number.startswith("G") and not has_gakushi_permission:
                continue
            
            # 学士試験フィルタチェック
            if gakushi_only and not question_number.startswith("G"):
                continue
            if not gakushi_only and question_number.startswith("G"):
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
        st.session_state["search_page_gakushi_setting"] = gakushi_only
        st.session_state["search_page_shuffle_setting"] = shuffle_results
    
    # 検索結果の表示
    if "search_results" in st.session_state:
        results = st.session_state["search_results"]
        query = st.session_state.get("search_query", "")
        search_type = "学士試験" if st.session_state.get("search_page_gakushi_setting", False) else "全体"
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
                "未学習": "🔴",
                "レベル0": "🟠", 
                "レベル1": "🟡",
                "レベル2": "🟢",
                "レベル3": "🔵",
                "レベル4": "🟣",
                "習得済み": "⭐"
            }
            
            for i, q in enumerate(results[:20]):  # 最初の20件を表示
                # 権限チェック：学士試験の問題で権限がない場合はスキップ
                question_number = q.get('number', '')
                if question_number.startswith("G") and not has_gakushi_permission:
                    continue
                
                # 学習レベルの取得
                card = cards.get(question_number, {})
                if not card:
                    level = "未学習"
                else:
                    card_level = card.get("level", 0)
                    if card_level >= 6:
                        level = "習得済み"
                    else:
                        level = f"レベル{card_level}"
                
                # 必修問題チェック
                if search_target == "学士試験":
                    is_hisshu = question_number in GAKUSHI_HISSHU_Q_NUMBERS_SET
                else:
                    is_hisshu = question_number in HISSHU_Q_NUMBERS_SET
                
                level_icon = level_icons.get(level, "⚪")
                level_color = level_colors.get(level, "#888888")
                hisshu_mark = "🔥" if is_hisshu else ""
                    
                with st.expander(f"{level_icon} {q.get('number', 'N/A')} - {q.get('subject', '未分類')} {hisshu_mark}"):
                    # レベルを色付きで表示
                    st.markdown(f"**学習レベル:** <span style='color: {level_color}; font-weight: bold;'>{level}</span>", unsafe_allow_html=True)
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
                
            # LaTeX出力機能
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("📝 LaTeX形式で生成", key="latex_generate_btn"):
                    with st.spinner("LaTeXファイルを生成中..."):
                        latex_content = export_questions_to_latex(results)
                        st.session_state["latex_content"] = latex_content
                        st.session_state["latex_filename"] = f"dental_questions_{query}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.tex"
                    st.success("LaTeX形式のファイルが生成されました！")
            
            with col2:
                if "latex_content" in st.session_state:
                    st.download_button(
                        label="💾 LaTeXファイルをダウンロード",
                        data=st.session_state["latex_content"],
                        file_name=st.session_state.get("latex_filename", "dental_questions.tex"),
                        mime="text/plain",
                        help="生成されたLaTeXファイルをダウンロードします。uplatexでPDFにコンパイルできます。"
                    )
                else:
                    st.button("💾 LaTeXファイルをダウンロード", disabled=True, help="先にLaTeX形式で生成してください")
            
            # LaTeX使用方法の説明
            if "latex_content" in st.session_state:
                with st.expander("📖 LaTeXファイルのPDF変換方法"):
                    st.markdown("""
                    **ダウンロードしたLaTeXファイルをPDFに変換する方法：**
                    
                    1. **TeX Live等のLaTeX環境を準備**
                       - Windows: TeX Live または MiKTeX
                       - macOS: MacTeX
                       - Linux: texlive パッケージ
                    
                    2. **コマンドラインでPDF変換**
                       ```bash
                       uplatex dental_questions_YYYYMMDD_HHMMSS.tex
                       dvipdfmx dental_questions_YYYYMMDD_HHMMSS.dvi
                       ```
                    
                    3. **オンラインサービスを利用**
                       - Overleaf (https://www.overleaf.com/)
                       - Cloud LaTeX等のサービス
                    
                    ※ 日本語を含むため、uplatex + dvipdfmxの組み合わせを推奨します。
                    """)
            
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
            skipped = st.form_submit_button("スキップ", type="secondary")
            if submitted_check:
                for q in q_objects:
                    answer_str = q.get("answer", "")
                    if is_ordering_question(q):
                        # --- 修正箇所②：並び替え問題の解答判定 ---
                        try:
                            # セッションからシャッフル情報を取得
                            shuffle_indices = st.session_state.get(f"shuffled_{q['number']}", list(range(len(q.get("choices", [])))))
                            # 元のインデックス→シャッフル後のインデックスのマッピングを作成
                            reverse_shuffle_map = {orig_idx: new_idx for new_idx, orig_idx in enumerate(shuffle_indices)}
                            
                            # JSON内の元の正解順（例: "CEABD"）を取得
                            original_answer_str = q.get("answer", "").strip().upper()
                            # 元の正解順をインデックスのリストに変換
                            original_indices_correct_order = [ord(c) - 65 for c in original_answer_str]
                            
                            # 元の正解順を、シャッフル後のインデックス順に変換
                            shuffled_correct_indices = [reverse_shuffle_map[orig_idx] for orig_idx in original_indices_correct_order]
                            # シャッフル後の正解文字列を作成 (例: "BDACE")
                            correct_shuffled_answer_str = "".join([chr(65 + i) for i in shuffled_correct_indices])

                            # ユーザー入力と比較
                            user_input = st.session_state.get(f"order_input_{q['number']}", "").strip().upper().replace(" ", "")
                            st.session_state.result_log[q['number']] = (user_input == correct_shuffled_answer_str)
                        except (KeyError, TypeError, ValueError):
                             # 正解データが不正な場合などは不正解とする
                            st.session_state.result_log[q['number']] = False
                    elif "choices" in q and q["choices"]:
                        user_answers = []
                        shuffled_choices, shuffle_indices = get_shuffled_choices(q)
                        user_selection_key = f"user_selection_{q['number']}"
                        for i in range(len(shuffled_choices)):
                            if st.session_state.get(user_selection_key, [])[i]:
                                original_index = shuffle_indices[i]
                                user_answers.append(chr(65 + original_index))
                        is_correct = False
                        if "/" in answer_str or "／" in answer_str:
                            valid_options = answer_str.replace("／", "/").split("/")
                            if len(user_answers) == 1 and user_answers[0] in valid_options:
                                is_correct = True
                        else:
                            correct_answers = sorted(list(answer_str))
                            if sorted(user_answers) == correct_answers:
                                is_correct = True
                        st.session_state.result_log[q['number']] = is_correct
                    else:
                        user_input = st.session_state.get(f"free_input_{q['number']}", "").strip()
                        st.session_state.result_log[q['number']] = (user_input == answer_str.strip())
                st.session_state[f"checked_{group_id}"] = True
                st.rerun()
            elif skipped:
                st.session_state.current_q_group = get_next_q_group()
                for key in list(st.session_state.keys()):
                    if key.startswith(("checked_", "user_selection_", "shuffled_", "free_input_", "order_input_")):
                        del st.session_state[key]
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
                if is_correct:
                    st.markdown("<span style='font-size:1.5em; color:green;'>✓ 正解！</span>", unsafe_allow_html=True)
                else:
                    st.markdown("<span style='font-size:1.5em; color:red;'>× 不正解</span>", unsafe_allow_html=True)
                    st.markdown(f"<span style='color:blue;'>正解: {'・'.join(correct_labels)}</span>", unsafe_allow_html=True)
            else:
                st.text_input("あなたの解答", value=st.session_state.get(f"free_input_{q['number']}", ""), disabled=True)
                if is_correct:
                    st.markdown("<span style='font-size:1.5em; color:green;'>✓ 正解！</span>", unsafe_allow_html=True)
                else:
                    st.markdown("<span style='font-size:1.5em; color:red;'>× 不正解</span>", unsafe_allow_html=True)
                    st.markdown(f"<span style='color:blue;'>正解: {q.get('answer', '')}</span>", unsafe_allow_html=True)
        with st.form(key=f"eval_form_{group_id}"):
            st.markdown("#### この問題グループの自己評価")
            eval_map = {"もう一度": 1, "難しい": 2, "普通": 4, "簡単": 5}
            selected_eval_label = st.radio("自己評価", eval_map.keys(), horizontal=True, label_visibility="collapsed")
            if st.form_submit_button("次の問題へ", type="primary"):
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
st.title("🦷 歯科国家試験AI対策アプリ")

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
    
    st.markdown("### 🔐 ログイン／新規登録")
    tab_login, tab_signup = st.tabs(["ログイン", "新規登録"])
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
                # with st.spinner('データ移行中...'):
                #     migrate_start = time.time()
                #     migrate_progress_doc_if_needed(st.session_state["uid"], login_email)
                #     progress_time = time.time() - migrate_start
                #     st.write(f"進捗データ移行完了: {progress_time:.2f}秒")
                    
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
        signup_email = st.text_input("メールアドレス", key="signup_email")
        signup_password = st.text_input("パスワード（6文字以上）", type="password", key="signup_password")
        if st.button("新規登録", key="signup_btn"):
            result = firebase_signup(signup_email, signup_password)
            if "idToken" in result:
                st.success("新規登録に成功しました。ログインしてください。")
            else:
                st.error("新規登録に失敗しました。メールアドレスが既に使われているか、パスワードが短すぎます。")
    st.stop()
else:
    import time
    main_start = time.time()
    
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
                # Anki風の日次目標表示
                st.markdown("#### 📅 本日の学習目標")
                today = datetime.date.today()
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
                
                # 本日の学習完了数を計算
                today_reviews_done = 0
                today_new_done = 0
                
                for card in cards.values():
                    history = card.get('history', [])
                    for review in history:
                        if isinstance(review, dict):
                            review_date = review.get('timestamp', '')
                            if review_date.startswith(today_str):
                                # 本日の復習か新規かを判定
                                if len(history) == 1:  # 初回学習（新規）
                                    today_new_done += 1
                                else:  # 復習
                                    today_reviews_done += 1
                                break  # 同じカードの重複カウントを防ぐ
                
                # 新規学習目標数
                new_target = st.session_state.get("new_cards_per_day", 10)
                
                # 残り目標数を計算
                review_remaining = max(0, review_count - today_reviews_done)
                new_remaining = max(0, new_target - today_new_done)
                
                col1, col2 = st.columns(2)
                with col1:
                    if review_remaining > 0:
                        if today_reviews_done > 0:
                            st.metric("復習", review_remaining, "枚", delta=f"-{today_reviews_done}")
                        else:
                            st.metric("復習", review_remaining, "枚")
                    else:
                        st.metric("復習", "完了", "✅", delta=f"本日{today_reviews_done}枚")
                with col2:
                    if new_remaining > 0:
                        if today_new_done > 0:
                            st.metric("新規", new_remaining, "枚", delta=f"-{today_new_done}")
                        else:
                            st.metric("新規", new_remaining, "枚")
                    else:
                        st.metric("新規", "完了", "✅", delta=f"本日{today_new_done}枚")
                
                # 学習開始ボタン
                if st.button("🚀 今日の学習を開始する", type="primary", key="start_today_study"):
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
                        st.success(f"今日の学習を開始します！（{len(grouped_queue)}問）")
                        st.rerun()
                    else:
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
            st.markdown("このページは学習状況の分析と検索に特化しています。")
            
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
    # 検索ページから演習開始のフラグをチェック
    if st.session_state.get("start_practice_from_search", False):
        # フラグをクリアして演習ページを表示
        st.session_state.start_practice_from_search = False
        render_practice_page()
    elif st.session_state.get("page_select", "演習") == "演習":
        render_practice_page()
    else:
        render_search_page()