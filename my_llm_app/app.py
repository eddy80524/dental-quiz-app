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

@st.cache_resource
def initialize_firebase():
    firebase_creds = to_dict(st.secrets["firebase_credentials"])
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        json.dump(firebase_creds, f)
        temp_path = f.name
    creds = credentials.Certificate(temp_path)
    
    # 既存のアプリがあれば削除して再初期化（辞書の変更中エラーを回避）
    apps_to_delete = list(firebase_admin._apps.values())
    for app in apps_to_delete:
        firebase_admin.delete_app(app)
    firebase_admin._apps.clear()
    
    # 正しいFirebase Storageバケット名で初期化
    firebase_admin.initialize_app(
        creds,
        {'storageBucket': 'dent-ai-4d8d8.firebasestorage.app'}
    )
    print(f"Firebase initialized with bucket: dent-ai-4d8d8.firebasestorage.app")
    
    # FirestoreクライアントとStorageバケットもここで初期化
    db = firestore.client()
    bucket = storage.bucket()
    return db, bucket

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

def get_cookies():
    """Cookieを安全に取得（CookiesNotReadyエラー完全対応）"""
    # 初期化フラグで重複実行を防止
    if st.session_state.get("cookie_init_attempted"):
        cookies = st.session_state.get("cookie_manager")
        if cookies is not None:  # Noneチェックのみ
            # Cookie readiness チェックは一切行わない（エラー回避）
            return cookies
        else:
            return None
    
    # 初回のみ初期化を試行
    st.session_state.cookie_init_attempted = True
    try:
        cookies = get_cookie_manager()
        if cookies is not None:  # Noneチェックのみ
            # Cookie readiness チェックは行わず、直接セッションに保存
            st.session_state.cookie_manager = cookies
            return cookies
        else:
            print("[DEBUG] Cookie manager is None")
            return None
    except Exception as e:
        print(f"[DEBUG] Cookie access error: {e}")
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
            try:
                cookies["refresh_token"] = ""
                cookies.save()
            except:
                pass
            return False
        
        # 高速セッション復元（emailベース管理）
        # email, uidは上で既に取得済み
        if not uid:
            uid = result.get("user_id")
        
        if not email:
            print(f"[DEBUG] try_auto_login_from_cookie - emailなし")
            return False
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
def load_master_data():
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
        'gakushi-2022-1再.json',  # 追加
        'gakushi-2022-2.json', 
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
        m = re.match(r'^G(\d{2})-.*-([A-D])-\d+$', qn)
        if m:
            y2 = int(m.group(1))
            year = 2000 + y2 if y2 <= 30 else 1900 + y2
            area = m.group(2)
            years.add(year)
            areas_by_year[year].add(area)
        s = (q.get("subject") or "").strip()
        if qn.startswith("G") and s:
            subjects.add(s)
    years_sorted = sorted(years, reverse=True)
    areas_map = {y: sorted(list(areas_by_year[y])) for y in years_sorted}
    gakushi_subjects = sorted(list(subjects))
    return years_sorted, areas_map, gakushi_subjects

def filter_gakushi_by_year_area(all_questions, year, area):
    yy = str(year)[2:]  # 2024 -> "24"
    pat = re.compile(rf'^G{yy}-.*-{area}-\d+$')
    res = []
    for q in all_questions:
        qn = q.get("number", "")
        if qn.startswith("G") and pat.match(qn):
            res.append(q)
    return res

# 初期データ読み込み
CASES, ALL_QUESTIONS = load_master_data()
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
                project_id = getattr(db._client, 'project', 'unknown')
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
                    print(f"[DEBUG] UIDでデータなし、emailベース旧データを検索: {email}")
                    print(f"[DEBUG] 検索対象UID: {uid}")
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
        # emailをドキュメントIDとして使用していた旧データを検索
        email_doc_ref = db.collection("user_progress").document(email)
        email_doc = email_doc_ref.get(timeout=10)
        
        if email_doc.exists:
            old_data = email_doc.to_dict()
            print(f"[DEBUG] 旧emailベースデータ発見: {len(old_data.get('cards', {}))}カード")
            
            # UIDベースの新しいドキュメントに移行
            new_data = {
                "cards": old_data.get("cards", {}),
                "new_cards_per_day": old_data.get("new_cards_per_day", 10),
                "email": email,
                "migrated_from": email,
                "migrated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "last_login": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }
            
            # 新しいUIDドキュメントに保存
            uid_doc_ref = db.collection("user_progress").document(uid)
            uid_doc_ref.set(new_data)
            
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
            normalized_doc_ref = db.collection("user_progress").document(normalized_email)
            normalized_doc = normalized_doc_ref.get(timeout=10)
            
            if normalized_doc.exists:
                old_data = normalized_doc.to_dict()
                print(f"[DEBUG] 正規化email旧データ発見: {len(old_data.get('cards', {}))}カード")
                
                # 同様の移行処理
                new_data = {
                    "cards": old_data.get("cards", {}),
                    "new_cards_per_day": old_data.get("new_cards_per_day", 10),
                    "email": email,
                    "migrated_from": normalized_email,
                    "migrated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "last_login": datetime.datetime.now(datetime.timezone.utc).isoformat()
                }
                
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

@st.cache_data(ttl=900)  # 15分キャッシュ
def load_user_data_full(user_id):
    """演習開始時に全データを読み込む完全版（UIDベース＋emailメタデータ）"""
    import time
    start = time.time()
    
    if not ensure_valid_session():
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
                    print(f"[DEBUG] load_user_data_full - 成功: {time.time() - start:.3f}s")
                    return result
            except Exception as e:
                print(f"[DEBUG] load_user_data_full - エラー: {e}, 時間: {time.time() - start:.3f}s")
    
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

    if not ensure_valid_session():
        return

    if db and user_id:
        doc_ref = db.collection("user_progress").document(user_id)  # UIDを主キーとして使用
        payload = {
            "cards": session_state.get("cards", {}),
            "email": session_state.get("email"),  # emailメタデータを保存
            "last_save": datetime.datetime.now(datetime.timezone.utc).isoformat()  # 最終保存時刻
        }
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

def migrate_progress_doc_if_needed(uid: str, email: str):
    """初回ログイン時などに email Doc を UID Doc へコピー（冪等）"""
    import time
    start = time.time()
    
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
            email_doc_ref = db.collection("user_permissions").document(email)
            email_doc = email_doc_ref.get()
            if email_doc.exists:
                old_data = email_doc.to_dict()
                print(f"[DEBUG] 旧email権限発見、マイグレーション実行")
                
                # 権限をUIDベースに移行
                new_permission_data = {
                    "can_access_gakushi": old_data.get("can_access_gakushi", False),
                    "email": email,
                    "migrated_from": email,
                    "migrated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                }
                doc_ref.set(new_permission_data)
                
                # 旧データに移行済みマーク
                email_doc_ref.update({
                    "migrated_to_uid": uid,
                    "migrated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                })
                
                print(f"[DEBUG] 権限マイグレーション完了: {bool(old_data.get('can_access_gakushi', False))}")
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

def get_secure_image_url(path):
    """
    Firebase Storageのパスから15分有効な署名付きURLを生成。
    もしhttp(s)で始まる完全なURLなら、そのまま返す。
    """
    if isinstance(path, str) and (path.startswith('http://') or path.startswith('https://')):
        return path
    try:
        if path:
            # セッション状態で正しいバケットが指定されている場合はそれを使用
            from google.cloud import storage as cloud_storage
            project_id = st.secrets['firebase_credentials']['project_id']
            client = cloud_storage.Client(project=project_id)
            
            if "correct_bucket" in st.session_state:
                bucket_to_use = client.bucket(st.session_state["correct_bucket"])
            else:
                # デフォルトバケット名を使用
                bucket_to_use = client.bucket(f"{project_id}.appspot.com")
            
            blob = bucket_to_use.blob(path)
            # ファイルが存在するかチェック
            if not blob.exists():
                return None
            
            url = blob.generate_signed_url(expiration=datetime.timedelta(minutes=15))
            return url
    except Exception as e:
        # エラーが発生した場合は None を返す
        return None

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

def search_questions_by_keyword(keyword, gakushi_only=False):
    """
    キーワードで問題を検索する関数
    問題文、選択肢、解説などからキーワードを検索
    """
    if not keyword:
        return []
    
    keyword_lower = keyword.lower()
    matching_questions = []
    
    for q in ALL_QUESTIONS:
        # 学士試験限定の場合、学士試験の問題番号かチェック
        if gakushi_only:
            question_number = q.get("number", "")
            # 学士試験の問題番号パターン（例：G22-1-1-A-1, G24-1-1-A-1など）
            if not question_number.startswith("G"):
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
    card.update({"EF": EF, "n": n, "I": I, "next_review": next_review_dt.isoformat(), "quality": quality})
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
    st.title("検索・進捗ページ")
    
    # --- サイドバーでモード選択 ---
    with st.sidebar:
        st.header("検索モード")
        uid = st.session_state.get("uid")  # UIDベース管理
        has_gakushi_permission = check_gakushi_permission(uid)
        mode_choices = ["国試全体", "キーワード検索"]
        if has_gakushi_permission:
            mode_choices.append("学士試験")
        search_mode = st.radio("分析対象", mode_choices, key="search_mode_radio")

    # --- モード別に処理を完全に分岐 ---

    if search_mode == "キーワード検索":
        # ▼▼▼ キーワード検索モードの処理 ▼▼▼
        st.subheader("キーワード検索")
        col1, col2 = st.columns([3, 1])
        with col1:
            search_keyword = st.text_input("検索キーワード", placeholder="例: インプラント、根管治療、歯周病")
        with col2:
            search_btn = st.button("検索", type="primary")
        
        # 検索オプション
        col1, col2 = st.columns(2)
        with col1:
            if has_gakushi_permission:
                gakushi_only = st.checkbox("学士試験のみ検索", key="search_page_gakushi_setting_checkbox")
            else:
                gakushi_only = False
                # 権限がない場合は何も表示しない
        with col2:
            shuffle_results = st.checkbox("結果をシャッフル", key="search_page_shuffle_setting_checkbox", value=True)
        
        if search_btn and search_keyword.strip():
            keyword_results = search_questions_by_keyword(search_keyword.strip(), gakushi_only=gakushi_only)
            
            # シャッフルオプションが有効な場合
            if shuffle_results and keyword_results:
                import random
                keyword_results = keyword_results.copy()
                random.shuffle(keyword_results)
            
            st.session_state["search_results"] = keyword_results
            st.session_state["search_query"] = search_keyword.strip()
            st.session_state["search_page_gakushi_setting"] = gakushi_only
            st.session_state["search_page_shuffle_setting"] = shuffle_results
        
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
                        if year:
                            years.append(str(year))
                    
                    year_range = f"{min(years)}-{max(years)}" if years else "不明"
                    st.metric("年度範囲", year_range)
                
                # 検索結果の詳細表示
                st.subheader("検索結果")
                for i, q in enumerate(results[:20]):  # 最初の20件を表示
                    with st.expander(f"{q.get('number', 'N/A')} - {q.get('subject', '未分類')}"):
                        st.markdown(f"**問題:** {q.get('question', '')[:100]}...")
                        if q.get('choices'):
                            st.markdown("**選択肢:**")
                            for j, choice in enumerate(q['choices'][:3]):  # 最初の3つの選択肢
                                choice_text = choice.get('text', str(choice)) if isinstance(choice, dict) else str(choice)
                                st.markdown(f"  {chr(65+j)}. {choice_text[:50]}...")
                
                if len(results) > 20:
                    st.info(f"表示は最初の20件です。全{len(results)}件中")
            else:
                st.warning(f"「{query}」に該当する問題が見つかりませんでした")
        else:
            st.info("キーワードを入力して検索してください")
        
        # この後の処理をスキップ
        return

    elif search_mode == "学士試験":
        # ▼▼▼ 学士試験モードの処理（国試と同様のシンプルな科目別） ▼▼▼
        
        # 学士試験の全問題を科目別に整理
        questions_data = []
        for q in ALL_QUESTIONS:
            if q.get("number", "").startswith("G"):  # 学士試験問題のみ
                q_num = q["number"]
                card = st.session_state.get("cards", {}).get(q_num, {})
                
                def map_card_to_level(card_data):
                    n = card_data.get("n")
                    if not card_data or n is None: return "未学習"
                    if n == 0: return "レベル0"
                    if n == 1: return "レベル1"
                    if n == 2: return "レベル2"
                    if n == 3: return "レベル3"
                    if n == 4: return "レベル4"
                    if n >= 5: return "習得済み"
                    return "未学習"
                    
                level = map_card_to_level(card)
                days_until_due = None
                if "next_review" in card:
                    try:
                        due_date = datetime.datetime.fromisoformat(card["next_review"])
                        days_until_due = (due_date - datetime.datetime.now(datetime.timezone.utc)).days
                    except (ValueError, TypeError):
                        days_until_due = None
                
                # 問題番号から年度・試験種別・領域・番号を抽出
                match = re.match(r'^G(\d{2})[–\-]([\d–\-再]+)[–\-]([A-D])[–\-](\d+)$', q_num)
                year, test_type, area, num = None, None, None, None
                if match:
                    year = f"20{match.group(1)}"
                    test_type = match.group(2)
                    area = match.group(3)
                    num = int(match.group(4))
                
                # 必修判定: 1〜20番が必修
                is_hisshu = num and 1 <= num <= 20
                
                subject = q.get("subject", "その他")
                        
                questions_data.append({
                    "id": q_num, "year": year, "type": test_type,
                    "area": area, "number": num, "subject": subject, "level": level,
                    "ef": card.get("EF"), "interval": card.get("I"), "repetitions": card.get("n"),
                    "history": card.get("history", []), "days_until_due": days_until_due,
                    "is_hisshu": is_hisshu
                })
        
        filtered_df = pd.DataFrame(questions_data)
        
        # 学士試験モードの絞り込み条件を作成・表示（国試と同様のUIに統一）
        years_sorted = sorted([y for y in filtered_df["year"].unique() if y], reverse=True) if not filtered_df.empty else []
        areas_sorted = sorted([a for a in filtered_df["area"].unique() if a]) if not filtered_df.empty else []
        subjects_sorted = sorted([s for s in filtered_df["subject"].unique() if s]) if not filtered_df.empty else []
        levels_sorted = ["未学習", "レベル0", "レベル1", "レベル2", "レベル3", "レベル4", "習得済み"]

        with st.sidebar:
            st.header("絞り込み条件")
            # 1. session_stateに保存されているデフォルト値を取得
            applied_filters = st.session_state.get("applied_search_gakushi_filters", {})
            default_years = applied_filters.get("years", years_sorted)
            default_areas = applied_filters.get("areas", areas_sorted)
            default_subjects = applied_filters.get("subjects", subjects_sorted)
            default_levels = applied_filters.get("levels", levels_sorted)

            # 2. デフォルト値を選択肢リストに存在する値のみにサニタイズ（無害化）する
            sanitized_years = [y for y in default_years if y in years_sorted]
            sanitized_areas = [a for a in default_areas if a in areas_sorted]
            sanitized_subjects = [s for s in default_subjects if s in subjects_sorted]
            sanitized_levels = [l for l in default_levels if l in levels_sorted]

            # 3. サニタイズ済みの値をmultiselectのデフォルト値として使用する
            years = st.multiselect("年度", years_sorted, default=sanitized_years, key="search_gakushi_years_multi")
            areas = st.multiselect("領域", areas_sorted, default=sanitized_areas, key="search_gakushi_areas_multi")
            subjects = st.multiselect("科目", subjects_sorted, default=sanitized_subjects, key="search_gakushi_subjects_multi")
            levels = st.multiselect("習熟度", levels_sorted, default=sanitized_levels, key="search_gakushi_levels_multi")
            
            # 必修のみチェックボックス
            hisshu_only = st.checkbox("必修問題のみ", value=False, key="search_gakushi_hisshu_checkbox")
            
            if st.button("この条件で表示する", key="apply_search_gakushi_filters_btn"):
                # 更新された選択値をsession_stateに保存する
                st.session_state["applied_search_gakushi_filters"] = {
                    "years": years, "areas": areas, "subjects": subjects, "levels": levels, "hisshu_only": hisshu_only
                }
                # ページを再実行してフィルターを即時反映させる
                st.rerun()

        # 絞り込み処理
        if not filtered_df.empty:
            # session_stateから最新のフィルター条件を適用する
            current_filters = st.session_state.get("applied_search_gakushi_filters", {})
            if current_filters.get("years"): 
                filtered_df = filtered_df[filtered_df["year"].isin(current_filters["years"])]
            if current_filters.get("areas"): 
                filtered_df = filtered_df[filtered_df["area"].isin(current_filters["areas"])]
            if current_filters.get("subjects"): 
                filtered_df = filtered_df[filtered_df["subject"].isin(current_filters["subjects"])]
            if current_filters.get("levels"): 
                filtered_df = filtered_df[filtered_df["level"].isin(current_filters["levels"])]
            
            # 必修フィルタ
            if current_filters.get("hisshu_only"):
                filtered_df = filtered_df[filtered_df["is_hisshu"] == True]
    else:
        # ▼▼▼ 国試全体モードの処理 ▼▼▼
        
        questions_data = []
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        for q in ALL_QUESTIONS:
            if q.get("number", "").startswith("G"): continue
            q_num = q["number"]
            card = st.session_state.get("cards", {}).get(q_num, {})
            def map_card_to_level(card_data):
                n = card_data.get("n")
                if not card_data or n is None: return "未学習"
                if n == 0: return "レベル0"
                if n == 1: return "レベル1"
                if n == 2: return "レベル2"
                if n == 3: return "レベル3"
                if n == 4: return "レベル4"
                if n >= 5: return "習得済み"
                return "未学習"
            level = map_card_to_level(card)
            days_until_due = None
            if "next_review" in card:
                try:
                    due_date = datetime.datetime.fromisoformat(card["next_review"])
                    days_until_due = (due_date - now_utc).days
                except (ValueError, TypeError):
                    days_until_due = None
            questions_data.append({
                "id": q_num, "year": extract_year_from_question_number(q_num),
                "region": q_num[3] if len(q_num) >= 4 and q_num[3] in "ABCD" else None,
                "category": q.get("category", ""), "subject": q.get("subject", ""), "level": level,
                "ef": card.get("EF"), "interval": card.get("I"), "repetitions": card.get("n"),
                "history": card.get("history", []), "days_until_due": days_until_due
            })
        
        df = pd.DataFrame(questions_data)
        
        # 国試全体モードの絞り込み条件を作成・表示
        years_sorted = sorted(df["year"].dropna().unique().astype(int)) if not df.empty else []
        regions_sorted = sorted(df["region"].dropna().unique()) if not df.empty else []
        subjects_sorted = sorted(df["subject"].dropna().unique()) if not df.empty else []
        levels_sorted = ["未学習", "レベル0", "レベル1", "レベル2", "レベル3", "レベル4", "習得済み"]

        with st.sidebar:
            st.header("絞り込み条件")
            # 1. session_stateに保存されているデフォルト値を取得
            applied_filters = st.session_state.get("applied_search_filters", {})
            default_years = applied_filters.get("years", years_sorted)
            default_regions = applied_filters.get("regions", regions_sorted)
            default_subjects = applied_filters.get("subjects", subjects_sorted)
            default_levels = applied_filters.get("levels", levels_sorted)

            # 2. デフォルト値を選択肢リストに存在する値のみにサニタイズ（無害化）する
            sanitized_years = [y for y in default_years if y in years_sorted]
            sanitized_regions = [r for r in default_regions if r in regions_sorted]
            sanitized_subjects = [s for s in default_subjects if s in subjects_sorted]
            sanitized_levels = [l for l in default_levels if l in levels_sorted]

            # 3. サニタイズ済みの値をmultiselectのデフォルト値として使用する
            years = st.multiselect("回数", years_sorted, default=sanitized_years)
            regions = st.multiselect("領域", regions_sorted, default=sanitized_regions)
            subjects = st.multiselect("科目", subjects_sorted, default=sanitized_subjects)
            levels = st.multiselect("習熟度", levels_sorted, default=sanitized_levels)
            
            if st.button("この条件で表示する", key="apply_search_filters_btn"):
                # 更新された選択値をsession_stateに保存する
                st.session_state["applied_search_filters"] = {"years": years, "regions": regions, "subjects": subjects, "levels": levels}
                # ページを再実行してフィルターを即時反映させる
                st.rerun()

        # 絞り込み処理
        filtered_df = df.copy()
        if not filtered_df.empty:
            # session_stateから最新のフィルター条件を適用する
            current_filters = st.session_state.get("applied_search_filters", {})
            if current_filters.get("years"): 
                filtered_df = filtered_df[filtered_df["year"].isin(current_filters["years"])]
            if current_filters.get("regions"): 
                filtered_df = filtered_df[filtered_df["region"].isin(current_filters["regions"])]
            if current_filters.get("subjects"): 
                filtered_df = filtered_df[filtered_df["subject"].isin(current_filters["subjects"])]
            if current_filters.get("levels"): 
                filtered_df = filtered_df[filtered_df["level"].isin(current_filters["levels"])]

    # --- ▼▼▼ 以下は全モード共通の表示部分 ▼▼▼ ---
    tab1, tab2, tab3 = st.tabs(["概要", "グラフ分析", "問題リスト検索"])
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
                
                # 必修問題の正解率計算（モードに応じて適切な必修問題セットを使用）
                if search_mode == "学士試験":
                    hisshu_df = filtered_df[filtered_df["is_hisshu"] == True]  # 学士試験の必修問題
                    hisshu_label = "【学士試験・必修問題】の正解率 (目標: 80%以上)"
                else:
                    hisshu_df = filtered_df[filtered_df["id"].isin(HISSHU_Q_NUMBERS_SET)]  # 国試の必修問題
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
                review_counts = Counter(review_history)
                ninety_days_ago = datetime.date.today() - datetime.timedelta(days=90)
                dates = [ninety_days_ago + datetime.timedelta(days=i) for i in range(91)]
                counts = [review_counts.get(d, 0) for d in dates]
                chart_df = pd.DataFrame({"Date": dates, "Reviews": counts})
                
                # plotlyを使ってy軸の最小値を0に固定
                if PLOTLY_AVAILABLE:
                    import plotly.express as px
                    fig = px.bar(chart_df, x="Date", y="Reviews", 
                                title="日々の学習量（過去90日間）")
                    fig.update_layout(
                        yaxis=dict(range=[0, max(counts) * 1.1] if counts else [0, 5]),  # y軸を0以上に固定
                        showlegend=False
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    # plotlyが利用できない場合は従来のbar_chart（但し、マイナス値は発生しない）
                    st.bar_chart(chart_df.set_index("Date"))
            else:
                st.info("選択された範囲にレビュー履歴がまだありません。")
            st.markdown("##### カードの「易しさ」分布")
            ease_df = filtered_df[filtered_df['ef'].notna()]
            if not ease_df.empty and PLOTLY_AVAILABLE:
                fig = px.histogram(ease_df, x="ef", nbins=20, title="Easiness Factor (EF) の分布")
                fig.update_layout(
                    yaxis=dict(range=[0, None]),  # y軸を0以上に固定（上限は自動調整）
                    showlegend=False
                )
                st.plotly_chart(fig, use_container_width=True)

    with tab3:
        st.subheader("問題リストと絞り込み")
        level_colors = {
            "未学習": "#757575", "レベル0": "#FF9800", "レベル1": "#FFC107",
            "レベル2": "#8BC34A", "レベル3": "#9C27B0", "レベル4": "#03A9F4",
            "レベル5": "#1E88E5", "習得済み": "#4CAF50"
        }
        st.markdown(f"**{len(filtered_df)}件の問題が見つかりました**")
        if not filtered_df.empty:
            def sort_key(row_id):
                m_gakushi = re.match(r'^(G)(\d+)[–\-]([\d–\-再]+)[–\-]([A-Z])[–\-](\d+)$', str(row_id))
                if m_gakushi: return (m_gakushi.group(1), int(m_gakushi.group(2)), m_gakushi.group(3), m_gakushi.group(4), int(m_gakushi.group(5)))
                m_normal = re.match(r"(\d+)([A-D])(\d+)", str(row_id))
                if m_normal: return ('Z', int(m_normal.group(1)), m_normal.group(2), '', int(m_normal.group(3)))
                return ('Z', 0, '', '', 0)

            filtered_sorted = filtered_df.copy()
            filtered_sorted['sort_key'] = filtered_sorted['id'].apply(sort_key)
            filtered_sorted = filtered_sorted.sort_values(by='sort_key').drop(columns=['sort_key'])
            for _, row in filtered_sorted.iterrows():
                st.markdown(
                    f"<div style='margin-bottom: 5px; padding: 5px; border-left: 5px solid {level_colors.get(row.level, '#888')};'>"
                    f"<span style='display:inline-block;width:80px;font-weight:bold;color:{level_colors.get(row.level, '#888')};'>{row.level}</span>"
                    f"<span style='font-size:1.1em;'>{row.id}</span>"
                    f"</div>",
                    unsafe_allow_html=True
                )

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
        # ★ 1) 短期復習: ready_at <= now のものを優先
        stq = st.session_state.get("short_term_review_queue", [])
        for i, item in enumerate(stq):
            ra = item.get("ready_at")
            if isinstance(ra, str):
                try: ra = datetime.datetime.fromisoformat(ra)
                except Exception: ra = now
            if not ra or ra <= now:
                grp = stq.pop(i).get("group", [])
                return grp
        # ★ 2) メインキュー
        if st.session_state.get("main_queue"):
            return st.session_state.main_queue.pop(0)
        return []

    if not st.session_state.get("current_q_group"):
        st.session_state.current_q_group = get_next_q_group()

    current_q_group = st.session_state.get("current_q_group", [])
    if not current_q_group:
        st.info("学習を開始するには、サイドバーで問題を選択してください。")
        st.stop()

    q_objects = [ALL_QUESTIONS_DICT.get(q_num) for q_num in current_q_group if q_num in ALL_QUESTIONS_DICT]
    if not q_objects:
        st.success("🎉 このセッションの学習はすべて完了しました！")
        st.balloons()
        st.stop()

    first_q = q_objects[0]
    group_id = first_q['number']
    is_checked = st.session_state.get(f"checked_{group_id}", False)
    case_data = CASES.get(first_q.get('case_id')) if first_q.get('case_id') else None

    st.title("歯科医師国家試験 演習")

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
        # 重複を除去して、万が一同じパスが複数あってもエラーを防ぐ
        unique_images = list(dict.fromkeys(display_images))
        secure_urls = [url for path in unique_images if path and (url := get_secure_image_url(path))]
        if secure_urls:
            st.image(secure_urls, use_container_width=True)

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
    
    st.title("ログイン／新規登録")
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
                    try:
                        cookies["refresh_token"] = result["refreshToken"]
                        cookies["uid"] = result.get("localId")
                        cookies["email"] = login_email
                        cookies.save()
                        print(f"[DEBUG] Cookie保存完了")
                    except Exception as e:
                        print(f"[DEBUG] Cookie保存エラー: {e}")
                
                total_time = time.time() - start_time
                st.success(f"ログイン成功！ (所要時間: {total_time:.1f}秒)")
                print(f"[DEBUG] ログイン処理完了 - 総時間: {total_time:.2f}秒")
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
                    try:
                        print(f"[DEBUG] クッキー保存開始 - cookies type: {type(cookies)}")
                        cookies["refresh_token"] = st.session_state["refresh_token"]
                        cookies["uid"] = st.session_state["uid"]
                        cookies["email"] = login_email
                        print(f"[DEBUG] クッキー値設定完了")
                        # 30日保持（必要なら調整）
                        cookies.save()
                        cookie_time = time.time() - cookie_start
                        st.write(f"クッキー保存完了: {cookie_time:.3f}秒")
                        print(f"[DEBUG] クッキー保存成功: {cookie_time:.3f}秒")
                    except Exception as e:
                        print(f"[DEBUG] クッキー保存エラー: {e}")
                        import traceback
                        traceback.print_exc()
                        st.warning(f"自動ログイン設定の保存に失敗しました: {e}")
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
        st.session_state.cards = {}
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
    with st.sidebar:
        # セッション状態の表示
        # トークンタイムスタンプの確認と表示（安全なname取得）
        name = st.session_state.get("name", "ユーザー")  # デフォルト値を設定
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
        
        page = st.radio("ページ選択", ["演習", "検索"], key="page_select")
        if st.button("ログアウト", key="logout_btn"):
            uid = st.session_state.get("uid")  # UIDベース管理
            save_user_data(uid, st.session_state)  # UIDを使用
            for k in ["user_logged_in", "id_token", "refresh_token", "name", "username", "email", "uid", "user_data_loaded", "token_timestamp"]:
                if k in st.session_state:
                    del st.session_state[k]
            
            # クッキー破棄（emailベース）
            cookies = get_cookies()  # 安全にCookie取得
            if cookies is not None:  # Noneチェック
                try:
                    for ck in ["refresh_token", "uid", "email"]:
                        cookies[ck] = ""
                        cookies.delete(ck)
                    cookies.save()
                except Exception as e:
                    print(f"Cookie deletion error: {e}")
            
            st.rerun()
        if page == "演習":
            # 演習ページアクセス時に完全版データを読み込み（初回のみ）
            if not st.session_state.get("full_data_loaded"):
                with st.spinner("演習データを読み込み中..."):
                    full_data_start = time.time()
                    uid = st.session_state.get("uid")  # UIDを主キーとして使用
                    full_user_data = load_user_data_full(uid)  # UIDを使用
                    full_data_time = time.time() - full_data_start
                    
                    # 完全版データでセッション更新
                    st.session_state.cards = full_user_data.get("cards", {})
                    st.session_state.main_queue = full_user_data.get("main_queue", [])
                    st.session_state.short_term_review_queue = full_user_data.get("short_term_review_queue", [])
                    st.session_state.current_q_group = full_user_data.get("current_q_group", [])
                    st.session_state.full_data_loaded = True
                    
                    print(f"[DEBUG] 演習データ読み込み完了: {full_data_time:.3f}s")
                    st.success(f"演習データ読み込み完了: {full_data_time:.2f}秒")
            
            DEFAULT_NEW_CARDS_PER_DAY = 10
            # 初回ログイン時に設定済み。未設定ならデフォルト。
            if "new_cards_per_day" not in st.session_state:
                st.session_state["new_cards_per_day"] = DEFAULT_NEW_CARDS_PER_DAY
            new_cards_per_day = st.number_input(
                "新規カード/日", min_value=1, max_value=100,
                value=st.session_state["new_cards_per_day"], step=1,
                key="new_cards_per_day_input"
            )
            if new_cards_per_day != st.session_state["new_cards_per_day"]:
                st.session_state["new_cards_per_day"] = new_cards_per_day
                # 余計な再読込を避けて差分だけ保存
                try:
                    db = get_db()  # 安全にDB取得
                    if db:
                        db.collection("user_progress").document(uid).set({"new_cards_per_day": new_cards_per_day}, merge=True)
                except Exception as e:
                    st.warning(f"日次新規カード数の保存に失敗しました: {e}")
            
            # TODO: 新規カード自動選定機能は一時的に無効化
            # # 今日の新規カードを自動選定
            # if st.button("今日の新規カードを自動選定", key="auto_pick_new_cards_btn"):
            #     # 直近の履歴から類似抑制用に最近の出題IDを拾う（最大15件）
            #     recent_ids = []
            #     for q_num, card in sorted(st.session_state.cards.items(),
            #                               key=lambda kv: kv[1].get('history', [{}])[-1].get('timestamp', ''),
            #                               reverse=True):
            #         recent_ids.append(q_num)
            #         if len(recent_ids) >= 15: break
            # 
            #     N = int(st.session_state.get("new_cards_per_day", 10))
            #     picked_qids = pick_new_cards_for_today(ALL_QUESTIONS, st.session_state.cards, N=N, recent_qids=recent_ids)
            # 
            #     if not picked_qids:
            #         st.info("選べる未演習カードがありません。")
            #     else:
            #         grouped_queue = st.session_state.get("main_queue", [])
            #         for qid in picked_qids:
            #             grouped_queue.append([qid])
            #             if qid not in st.session_state.cards:
            #                 st.session_state.cards[qid] = {}
            #         st.session_state.main_queue = grouped_queue
            #         save_user_data(st.session_state.get("uid"), st.session_state)  # uid で保存
            #         st.success(f"{len(picked_qids)}枚の新規カードを追加しました")
            #         st.rerun()
                    
            has_progress = (
                st.session_state.get("main_queue") or
                st.session_state.get("short_term_review_queue") or
                st.session_state.get("current_q_group")
            )
            if has_progress and st.session_state.get("current_q_group"):
                if st.button("前回の続きから再開", key="resume_btn", type="primary"):
                    st.session_state["resume_requested"] = True
                    st.rerun()
                if st.button("演習を終了", key="end_session_btn", type="secondary"):
                    uid = st.session_state.get("uid")  # UIDベース管理
                    save_user_data(uid, st.session_state)  # UIDを使用
                    st.session_state["main_queue"] = []
                    st.session_state["short_term_review_queue"] = []
                    st.session_state["current_q_group"] = []
                    st.session_state.pop("resume_requested", None)
                    for key in list(st.session_state.keys()):
                        if key.startswith("checked_") or key.startswith("user_selection_") or key.startswith("shuffled_") or key.startswith("free_input_"):
                            del st.session_state[key]
                    st.rerun()
            
            # --- キーワード検索機能 ---
            st.markdown("---")
            st.header("キーワード検索")
            search_keyword = st.text_input("キーワードで問題を検索", placeholder="例: インプラント、根管治療、歯周病", key="search_keyword")
            
            # 検索オプション
            uid = st.session_state.get("uid")  # UIDベース管理
            has_gakushi_permission = check_gakushi_permission(uid)
            
            col1, col2 = st.columns(2)
            with col1:
                if has_gakushi_permission:
                    gakushi_only = st.checkbox("学士試験のみ", key="gakushi_only_checkbox")
                else:
                    gakushi_only = False
                    # 権限がない場合は何も表示しない
            with col2:
                shuffle_results = st.checkbox("シャッフル", key="shuffle_checkbox", value=True)
            
            # 検索実行ボタン
            if st.button("キーワード検索", type="secondary", key="search_btn"):
                if search_keyword.strip():
                    # キーワードで問題を検索
                    keyword_results = search_questions_by_keyword(search_keyword.strip(), gakushi_only=gakushi_only)
                    if keyword_results:
                        # シャッフルオプションが有効な場合
                        if shuffle_results:
                            import random
                            keyword_results = keyword_results.copy()
                            random.shuffle(keyword_results)
                        
                        st.session_state["keyword_search_results"] = keyword_results
                        st.session_state["current_search_keyword"] = search_keyword.strip()
                        st.session_state["search_gakushi_only"] = gakushi_only
                        st.session_state["search_shuffled"] = shuffle_results
                        
                        search_type = "学士試験" if gakushi_only else "全体"
                        shuffle_info = "（シャッフル済み）" if shuffle_results else "（順番通り）"
                        st.success(f"「{search_keyword}」で{len(keyword_results)}問見つかりました（{search_type}）{shuffle_info}")
                    else:
                        st.warning(f"「{search_keyword}」に該当する問題が見つかりませんでした")
                        st.session_state.pop("keyword_search_results", None)
                        st.session_state.pop("current_search_keyword", None)
                else:
                    st.warning("検索キーワードを入力してください")
            
            # 検索結果がある場合の表示
            if "keyword_search_results" in st.session_state:
                keyword = st.session_state.get('current_search_keyword', '')
                count = len(st.session_state['keyword_search_results'])
                search_type = "学士試験" if st.session_state.get('search_gakushi_only', False) else "全体"
                shuffle_info = "（シャッフル済み）" if st.session_state.get('search_shuffled', False) else "（順番通り）"
                
                st.info(f"検索結果: 「{keyword}」で{count}問（{search_type}）{shuffle_info}")
                if st.button("検索結果で学習開始", type="primary", key="start_keyword_search"):
                    questions_to_load = st.session_state["keyword_search_results"]
                    # 学習開始処理
                    grouped_queue = []
                    processed_q_nums = set()
                    for q in questions_to_load:
                        q_num = str(q['number'])
                        if q_num in processed_q_nums: continue
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
                    for key in list(st.session_state.keys()):
                        if key.startswith("checked_") or key.startswith("user_selection_") or key.startswith("shuffled_"):
                            del st.session_state[key]
                    st.session_state.pop("resume_requested", None)
                    if "cards" not in st.session_state:
                        st.session_state.cards = {}
                    for q in questions_to_load:
                        if q['number'] not in st.session_state.cards:
                            st.session_state.cards[q['number']] = {}
                    st.session_state.pop("today_due_cards", None)
                    st.session_state.pop("current_q_num", None)
                    st.rerun()
                
                if st.button("検索結果をクリア", key="clear_search_btn"):
                    st.session_state.pop("keyword_search_results", None)
                    st.session_state.pop("current_search_keyword", None)
                    st.rerun()

            st.markdown("---")

            # --- ここから出題形式の選択肢を権限で分岐 ---
            uid = st.session_state.get("uid")  # UIDベース管理
            has_gakushi_permission = check_gakushi_permission(uid)
            mode_choices = ["回数別", "科目別","必修問題のみ"]
            mode = st.radio("出題形式を選択", mode_choices, key=f"mode_radio_{st.session_state.get('page_select', 'default')}")

            # 追加：対象（国試/学士）セレクタ
            if has_gakushi_permission:
                target_exam = st.radio("対象", ["国試", "学士"], key="target_exam", horizontal=True)
            else:
                target_exam = "国試"
            
            questions_to_load = []

            if mode == "回数別":
                if target_exam == "国試":
                    # ★ 現状どおり
                    selected_exam_num = st.selectbox("回数", ALL_EXAM_NUMBERS)
                    if selected_exam_num:
                        available_sections = sorted([s[-1] for s in ALL_EXAM_SESSIONS if s.startswith(selected_exam_num)])
                        selected_section_char = st.selectbox("領域", available_sections)
                        if selected_section_char:
                            selected_session = f"{selected_exam_num}{selected_section_char}"
                            questions_to_load = [q for q in ALL_QUESTIONS if q.get("number", "").startswith(selected_session)]
                else:
                    # ★ 学士：年度×領域
                    g_years, g_areas_map, _ = build_gakushi_indices(ALL_QUESTIONS)
                    if not g_years:
                        st.warning("学士の年度情報が見つかりません。")
                    else:
                        g_year = st.selectbox("年度", g_years)
                        areas = g_areas_map.get(g_year, ["A", "B", "C", "D"])
                        g_area = st.selectbox("領域", areas)
                        if g_year and g_area:
                            questions_to_load = filter_gakushi_by_year_area(ALL_QUESTIONS, g_year, g_area)

            elif mode == "科目別":
                if target_exam == "国試":
                    # ★ 現状どおり
                    KISO_SUBJECTS = ["解剖学", "歯科理工学", "組織学", "生理学", "病理学", "薬理学", "微生物学・免疫学", "衛生学", "発生学・加齢老年学", "生化学"]
                    RINSHOU_SUBJECTS = ["保存修復学", "歯周病学", "歯内治療学", "クラウンブリッジ学", "部分床義歯学", "全部床義歯学", "インプラント学", "口腔外科学", "歯科放射線学", "歯科麻酔学", "矯正歯科学", "小児歯科学"]
                    group = st.radio("科目グループ", ["基礎系科目", "臨床系科目"])
                    subjects_to_display = KISO_SUBJECTS if group == "基礎系科目" else RINSHOU_SUBJECTS
                    available_subjects = [s for s in ALL_SUBJECTS if s in subjects_to_display]
                    selected_subject = st.selectbox("科目", available_subjects)
                    if selected_subject:
                        questions_to_load = [q for q in ALL_QUESTIONS if q.get("subject") == selected_subject and not str(q.get("number","")).startswith("G")]
                else:
                    # ★ 学士：科目指定（系統フィルタなし）
                    g_years, g_areas_map, g_subjects = build_gakushi_indices(ALL_QUESTIONS)
                    if not g_subjects:
                        st.warning("学士の科目が見つかりません。")
                    else:
                        selected_subject = st.selectbox("科目", g_subjects)
                        if selected_subject:
                            questions_to_load = [q for q in ALL_QUESTIONS if str(q.get("number","")).startswith("G") and (q.get("subject") == selected_subject)]

            elif mode == "必修問題のみ":
                if target_exam == "国試":
                    # 国試の必修問題
                    questions_to_load = [q for q in ALL_QUESTIONS if q.get("number") in HISSHU_Q_NUMBERS_SET]
                else:
                    # 学士試験の必修問題（1-20番）
                    questions_to_load = [q for q in ALL_QUESTIONS if q.get("number") in GAKUSHI_HISSHU_Q_NUMBERS_SET]
            order_mode = st.selectbox("出題順", ["順番通り", "シャッフル"])
            if order_mode == "シャッフル":
                random.shuffle(questions_to_load)
            else:
                try:
                    questions_to_load = sorted(questions_to_load, key=get_natural_sort_key)
                except Exception as e:
                    st.error(f"ソート中にエラーが発生しました: {str(e)}")
                    st.write(f"questions_to_load の型: {type(questions_to_load)}")
                    if questions_to_load:
                        st.write(f"最初の要素: {questions_to_load[0]}")
                        st.write(f"最初の要素の型: {type(questions_to_load[0])}")
                    # フォールバック: エラーが発生した場合はそのまま使用
                    pass
            if st.button("この条件で学習開始", type="primary"):
                if not questions_to_load:
                    st.warning("該当する問題がありません。")
                else:
                    grouped_queue = []
                    processed_q_nums = set()
                    for q in questions_to_load:
                        q_num = str(q['number'])
                        if q_num in processed_q_nums: continue
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
                    for key in list(st.session_state.keys()):
                        if key.startswith("checked_") or key.startswith("user_selection_") or key.startswith("shuffled_"):
                            del st.session_state[key]
                    st.session_state.pop("resume_requested", None)
                    if "cards" not in st.session_state:
                        st.session_state.cards = {}
                    for q in questions_to_load:
                        if q['number'] not in st.session_state.cards:
                            st.session_state.cards[q['number']] = {}
                    st.session_state.pop("today_due_cards", None)
                    st.session_state.pop("current_q_num", None)
                    st.rerun()
            if "cards" not in st.session_state:
                st.session_state.cards = {}
            
            # キャッシュクリアボタン
            st.markdown("---")
            if st.button("🔄 キャッシュをクリア", help="問題データとキャッシュをリロードします"):
                # Streamlitのキャッシュをクリア
                st.cache_data.clear()
                st.cache_resource.clear()
                
                # Firebase接続もリセット
                try:
                    if firebase_admin._apps:
                        for app in firebase_admin._apps.values():
                            firebase_admin.delete_app(app)
                        firebase_admin._apps.clear()
                except Exception as e:
                    st.warning(f"Firebase接続リセット中にエラー: {e}")
                
                # セッション状態の問題データをクリア
                if 'questions_loaded' in st.session_state:
                    del st.session_state['questions_loaded']
                
                st.success("キャッシュをクリアしました。ページを再読み込みします...")
                st.rerun()
            
            st.markdown("---"); st.header("学習記録")
            if st.session_state.cards:
                quality_to_mark = {1: "×", 2: "△", 4: "◯", 5: "◎"}
                mark_to_label = {"◎": "簡単", "◯": "普通", "△": "難しい", "×": "もう一度"}
                evaluated_marks = [quality_to_mark.get(card.get('quality')) for card in st.session_state.cards.values() if card.get('quality')]
                total_evaluated = len(evaluated_marks)
                counter = Counter(evaluated_marks)
                with st.expander("自己評価の分布", expanded=True):
                    st.markdown(f"**合計評価数：{total_evaluated}問**")
                    for mark, label in mark_to_label.items():
                        count = counter.get(mark, 0); percent = int(round(count / total_evaluated * 100)) if total_evaluated else 0
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
    if page == "演習":
        render_practice_page()
    elif page == "検索":
        render_search_page()