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
    
    # 既存のアプリがあれば削除して再初期化
    if firebase_admin._apps:
        for app in firebase_admin._apps.values():
            firebase_admin.delete_app(app)
        firebase_admin._apps.clear()
    
    # 正しいFirebase Storageバケット名で初期化
    firebase_admin.initialize_app(
        creds,
        {'storageBucket': 'dent-ai-4d8d8.firebasestorage.app'}
    )
    print(f"Firebase initialized with bucket: dent-ai-4d8d8.firebasestorage.app")
    return None

initialize_firebase()
db = firestore.client()
bucket = storage.bucket()

# バケット情報をデバッグ表示
print(f"Firebase Storage bucket name: {bucket.name}")
print(f"Firebase Storage bucket configured: {bucket is not None}")

# --- Cookies（自動ログイン用） ---
try:
    cookie_password = st.secrets.get("cookie_password", "default_insecure_password_change_in_production")
    cookies = EncryptedCookieManager(
        prefix="dentai_",
        password=cookie_password
    )
    if not cookies.ready():
        st.stop()  # 初回レンダ時に初期化、以降は通る
except Exception as e:
    # secrets.tomlにcookie_passwordがない場合のフォールバック
    st.error("⚠️ 自動ログイン機能を有効にするには、secrets.tomlに'cookie_password'を追加してください。")
    cookies = None

FIREBASE_API_KEY = st.secrets["firebase_api_key"]
FIREBASE_AUTH_SIGNUP_URL = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
FIREBASE_AUTH_SIGNIN_URL = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
FIREBASE_REFRESH_TOKEN_URL = f"https://securetoken.googleapis.com/v1/token?key={FIREBASE_API_KEY}"

def firebase_signup(email, password):
    payload = {"email": email, "password": password, "returnSecureToken": True}
    r = requests.post(FIREBASE_AUTH_SIGNUP_URL, json=payload)
    return r.json()

def firebase_signin(email, password):
    payload = {"email": email, "password": password, "returnSecureToken": True}
    r = requests.post(FIREBASE_AUTH_SIGNIN_URL, json=payload)
    return r.json()

def firebase_refresh_token(refresh_token):
    """リフレッシュトークンを使って新しいidTokenを取得"""
    payload = {"grant_type": "refresh_token", "refresh_token": refresh_token}
    try:
        # 修正：JSONではなくx-www-form-urlencoded
        r = requests.post(FIREBASE_REFRESH_TOKEN_URL, data=payload)
        result = r.json()
        if "id_token" in result:
            return {
                "idToken": result["id_token"],
                "refreshToken": result["refresh_token"],
                "expiresIn": int(result.get("expires_in", 3600))
            }
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
    """クッキーに refresh_token があれば自動でトークン更新し、セッションを復元する。"""
    if not cookies or st.session_state.get("user_logged_in"):
        return False
    
    rt = cookies.get("refresh_token")
    if not rt:
        return False
    
    result = firebase_refresh_token(rt)
    if not result:
        return False
    
    uid = cookies.get("uid") or result.get("user_id")
    email = cookies.get("email") or ""
    
    st.session_state["name"] = (email.split("@")[0] if email else "user")
    st.session_state["username"] = email or uid
    st.session_state["email"] = email
    st.session_state["uid"] = uid
    st.session_state["id_token"] = result["idToken"]
    st.session_state["refresh_token"] = result["refreshToken"]
    st.session_state["token_timestamp"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    st.session_state["user_logged_in"] = uid
    
    return True

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

@st.cache_data
def load_master_data():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    master_dir = os.path.join(script_dir, 'data')
    
    # 読み込むファイルを直接指定する
    files_to_load = ['master_questions_final.json', 'gakushi-2022-1-1.json', 'gakushi-2022-1-2.json', 'gakushi-2022-1-3.json', 'gakushi-2022-2.json', 'gakushi-2024-1-1.json', 'gakushi-2024-2.json', 'gakushi-2025-1-1.json']
    target_files = [os.path.join(master_dir, f) for f in files_to_load]

    all_cases = {}
    all_questions = []
    seen_numbers = set()
    missing_files = []

    for file_path in target_files:
        # ファイルが存在するか念のため確認
        if not os.path.exists(file_path):
            missing_files.append(file_path)
            continue
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

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
    
    # ファイルが足りない場合は警告をUIに出さない
    return all_cases, all_questions

CASES, ALL_QUESTIONS = load_master_data()
ALL_QUESTIONS_DICT = {q['number']: q for q in ALL_QUESTIONS}
ALL_SUBJECTS = sorted(list(set(q['subject'] for q in ALL_QUESTIONS if q.get('subject') and q.get('subject') != '（未分類）')))
ALL_EXAM_NUMBERS = sorted(list(set(re.match(r'(\d+)', q['number']).group(1) for q in ALL_QUESTIONS if re.match(r'(\d+)', q['number']))), key=int, reverse=True)
ALL_EXAM_SESSIONS = sorted(list(set(re.match(r'(\d+[A-D])', q['number']).group(1) for q in ALL_QUESTIONS if re.match(r'(\d+[A-D])', q['number']))))

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

HISSHU_Q_NUMBERS_SET = {q['number'] for q in ALL_QUESTIONS if is_hisshu(q['number'])}

# --- Firestore連携 ---
def load_user_data(user_id):
    """user_id には UID を渡す"""
    if not ensure_valid_session():
        return {"cards": {}, "main_queue": [], "short_term_review_queue": [], "current_q_group": [], "new_cards_per_day": 10}

    if db and user_id:
        doc_ref = db.collection("user_progress").document(user_id)  # uid
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict()
            main_queue_str_list = data.get("main_queue", [])
            current_q_group_str = data.get("current_q_group", "")
            main_queue = [item.split(',') for item in main_queue_str_list if item]
            current_q_group = current_q_group_str.split(',') if current_q_group_str else []
            
            # ★ 短期復習キューの新形式対応（ready_at付き）
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
            
            return {
                "cards": data.get("cards", {}),
                "main_queue": main_queue,
                "short_term_review_queue": short_term_review_queue,
                "current_q_group": current_q_group,
                "new_cards_per_day": data.get("new_cards_per_day", 10),
            }
    return {"cards": {}, "main_queue": [], "short_term_review_queue": [], "current_q_group": [], "new_cards_per_day": 10}

def save_user_data(user_id, session_state):
    """user_id には UID を渡す"""
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
        doc_ref = db.collection("user_progress").document(user_id)  # uid
        payload = {"cards": session_state.get("cards", {})}
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
    if not db or not uid or not email:
        return
    
    uid_ref = db.collection("user_progress").document(uid)
    if uid_ref.get().exists:
        return
        
    email_ref = db.collection("user_progress").document(email)
    snap = email_ref.get()
    
    if snap.exists:
        uid_ref.set(snap.to_dict(), merge=True)
        # 旧ドキュメントに移行メタ（必要なら後で削除可能）
        email_ref.set({
            "__migrated_to": uid,
            "__migrated_at": datetime.datetime.utcnow().isoformat()
        }, merge=True)

def migrate_permission_if_needed(uid: str, email: str):
    """user_permissions も email → uid を一度だけ複製（冪等）"""
    if not db or not uid or not email:
        return
    src = db.collection("user_permissions").document(email).get()
    if src.exists:
        dst = db.collection("user_permissions").document(uid)
        if not dst.get().exists:
            dst.set(src.to_dict(), merge=True)

# --- ヘルパー関数 ---
# @st.cache_data # ← キャッシュが問題の可能性があるため、一時的に無効化
def check_gakushi_permission(user_id):
    """
    Firestoreのuser_permissionsコレクションから権限を判定。
    can_access_gakushi: trueならTrue, それ以外はFalse
    uidとemailの両方でチェックする（移行期間対応）
    """
    if not db or not user_id:
        return False
    
    # まずuidでチェック
    doc_ref = db.collection("user_permissions").document(user_id)
    doc = doc_ref.get()
    if doc.exists:
        data = doc.to_dict()
        if bool(data.get("can_access_gakushi", False)):
            return True
    
    # uidで見つからない場合、emailでもチェック（後方互換性）
    username = st.session_state.get("username")  # email
    if username and username != user_id:
        doc_ref_email = db.collection("user_permissions").document(username)
        doc_email = doc_ref_email.get()
        if doc_email.exists:
            data_email = doc_email.to_dict()
            return bool(data_email.get("can_access_gakushi", False))
    
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
            blob = bucket.blob(path)
            # ファイルが存在するかチェック
            if not blob.exists():
                st.warning(f"⚠️ ファイルが存在しません: {path}")
                print(f"File does not exist in Firebase Storage: {path}")
                return None
            
            url = blob.generate_signed_url(expiration=datetime.timedelta(minutes=15))
            print(f"Generated signed URL for {path}: {url[:100]}...")
            return url
    except Exception as e:
        # デバッグ用: エラーの詳細を表示
        st.error(f"画像URL生成エラー - パス: {path}, エラー: {str(e)}")
        print(f"Image URL generation error - Path: {path}, Error: {str(e)}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
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
    if is_hisshu(q_num_str) and quality == 2:
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
        uid = st.session_state.get("uid")
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
        # ▼▼▼ 学士試験モードの処理（科目リスト固定） ▼▼▼
        GAKUSHI_SUBJECTS = [
            "歯科矯正学", "歯科保存学", "口腔外科学1", "口腔外科学2", "小児歯科学", "口腔インプラント", "歯科麻酔学", "障がい者歯科", "歯科放射線学",
            "有歯補綴咬合学", "欠損歯列補綴咬合学", "高齢者歯科学", "生物学", "化学", "歯周病学", "法医学教室", "内科学", "口腔病理学",
            "口腔解剖学", "生理学", "生化学", "解剖学", "薬理学", "歯科理工学", "細菌学"
        ]
        with st.sidebar:
            st.header("絞り込み条件")
            gakushi_years = ["2025", "2024", "2023", "2022", "2021"]
            gakushi_types = ["1-1", "1-2", "1-3", "1再", "2", "2再"]
            gakushi_areas = ["A", "B", "C", "D"]
            selected_year = st.selectbox("年度", gakushi_years, key="search_gakushi_year")
            selected_type = st.selectbox("試験種別", gakushi_types, key="search_gakushi_type")
            selected_area = st.selectbox("領域", gakushi_areas, key="search_gakushi_area")
        prefix = f"G{selected_year[-2:]}-{selected_type}-{selected_area}-"
        questions_data = []
        for q in ALL_QUESTIONS:
            if q.get("number", "").startswith(prefix):
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
                # 必修判定: 1〜20番が必修
                m = re.match(r'^G\d{2}[–\-][\d–\-再]+[–\-][A-D][–\-](\d+)$', q_num)
                is_hisshu = False
                if m:
                    try:
                        num = int(m.group(1))
                        if 1 <= num <= 20:
                            is_hisshu = True
                    except Exception:
                        pass
                subject = q.get("subject", "")
                if subject not in GAKUSHI_SUBJECTS:
                    subject = "その他"
                questions_data.append({
                    "id": q_num, "year": selected_year, "type": selected_type,
                    "area": selected_area, "subject": subject, "level": level,
                    "ef": card.get("EF"), "interval": card.get("I"), "repetitions": card.get("n"),
                    "history": card.get("history", []), "days_until_due": days_until_due,
                    "is_hisshu": is_hisshu
                })
        with st.sidebar:
            selected_subjects = st.multiselect("科目", GAKUSHI_SUBJECTS + ["その他"], default=GAKUSHI_SUBJECTS + ["その他"])
            hisshu_only = st.checkbox("必修問題のみ", value=False)
        filtered_df = pd.DataFrame(questions_data)
        if not filtered_df.empty:
            if selected_subjects:
                filtered_df = filtered_df[filtered_df["subject"].isin(selected_subjects)]
            if hisshu_only:
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
                hisshu_df = filtered_df[filtered_df["id"].isin(HISSHU_Q_NUMBERS_SET)]
                hisshu_total_reviews = 0
                hisshu_correct_reviews = 0
                for history_list in hisshu_df["history"]:
                    for review in history_list:
                        if isinstance(review, dict) and "quality" in review:
                            hisshu_total_reviews += 1
                            if review["quality"] >= 4:
                                hisshu_correct_reviews += 1
                hisshu_retention_rate = (hisshu_correct_reviews / hisshu_total_reviews * 100) if hisshu_total_reviews > 0 else 0
                st.metric(label="【必修問題】の正解率 (目標: 80%以上)", value=f"{hisshu_retention_rate:.1f}%", delta=f"{hisshu_correct_reviews} / {hisshu_total_reviews} 回")

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
                st.bar_chart(chart_df.set_index("Date"))
            else:
                st.info("選択された範囲にレビュー履歴がまだありません。")
            st.markdown("##### カードの「易しさ」分布")
            ease_df = filtered_df[filtered_df['ef'].notna()]
            if not ease_df.empty and PLOTLY_AVAILABLE:
                fig = px.histogram(ease_df, x="ef", nbins=20, title="Easiness Factor (EF) の分布")
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

                    save_user_data(st.session_state.get("uid"), st.session_state)
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

    # デバッグ情報を表示
    if display_images:
        st.write(f"🔍 デバッグ: 検出された画像パス: {display_images}")
        # 重複を除去して、万が一同じパスが複数あってもエラーを防ぐ
        unique_images = list(dict.fromkeys(display_images))
        st.write(f"🔍 デバッグ: ユニーク化後: {unique_images}")
        
        secure_urls = []
        for path in unique_images:
            if path:
                url = get_secure_image_url(path)
                if url:
                    secure_urls.append(url)
                    st.write(f"✅ 成功: {path} -> URL生成成功")
                    # URLの詳細を表示（デバッグ用）
                    st.code(f"生成されたURL: {url[:100]}..." if len(url) > 100 else f"生成されたURL: {url}")
                else:
                    st.write(f"❌ 失敗: {path} -> URL生成失敗")
        
        if secure_urls:
            st.write(f"🖼️ 表示する画像数: {len(secure_urls)}")
            try:
                st.image(secure_urls, use_container_width=True)
                st.success("画像表示処理が正常に実行されました")
            except Exception as e:
                st.error(f"画像表示エラー: {str(e)}")
                # 個別に画像を表示してみる
                st.write("個別表示を試行中...")
                for i, url in enumerate(secure_urls):
                    try:
                        st.image(url, caption=f"画像 {i+1}", use_container_width=True)
                        st.write(f"画像 {i+1} 表示成功")
                    except Exception as img_err:
                        st.error(f"画像 {i+1} 表示失敗: {str(img_err)}")
        else:
            st.warning("⚠️ 表示可能な画像がありません")
    else:
        st.write("🔍 デバッグ: 画像パスが見つかりませんでした")

# --- メイン ---
# 自動ログインを試行
_ = try_auto_login_from_cookie()

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
        if st.button("ログイン", key="login_btn"):
            result = firebase_signin(login_email, login_password)
            if "idToken" in result:
                st.session_state["name"] = login_email.split("@")[0]
                st.session_state["username"] = login_email
                st.session_state["email"] = login_email  # ★ 追加：email をセッションに保存
                st.session_state["uid"] = result.get("localId")  # ★ 追加：UID
                st.session_state["id_token"] = result["idToken"]
                st.session_state["refresh_token"] = result.get("refreshToken", "")
                st.session_state["token_timestamp"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                st.session_state["user_logged_in"] = st.session_state["uid"]
                
                # 既存の移行処理を必ず呼ぶ
                migrate_progress_doc_if_needed(st.session_state["uid"], login_email)
                migrate_permission_if_needed(st.session_state["uid"], login_email)
                
                # Remember me: クッキー保存
                if remember_me and cookies and st.session_state.get("refresh_token"):
                    try:
                        cookies["refresh_token"] = st.session_state["refresh_token"]
                        cookies["uid"] = st.session_state["uid"]
                        cookies["email"] = login_email
                        # 30日保持（必要なら調整）
                        cookies.set("refresh_token", cookies["refresh_token"], max_age=60*60*24*30, same_site="Lax", secure=True)
                        cookies.set("uid", cookies["uid"], max_age=60*60*24*30, same_site="Lax", secure=True)
                        cookies.set("email", cookies["email"], max_age=60*60*24*30, same_site="Lax", secure=True)
                        cookies.save()
                    except Exception as e:
                        st.warning(f"自動ログイン設定の保存に失敗しました: {e}")
                
                st.success(f"ログイン成功: {login_email}")
                st.rerun()
            else:
                st.error("ログインに失敗しました。メールアドレスまたはパスワードを確認してください。")
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
    name = st.session_state.get("name")
    username = st.session_state.get("username")
    uid = st.session_state.get("uid")  # ★ 追加
    if not name or not username:
        st.warning("ログイン情報が見つかりません。再度ログインしてください。")
        st.stop()
    if "user_data_loaded" not in st.session_state:
        user_data = load_user_data(uid)  # ★ uid で読む
        st.session_state.cards = user_data.get("cards", {})
        st.session_state.main_queue = user_data.get("main_queue", [])
        st.session_state.short_term_review_queue = user_data.get("short_term_review_queue", [])
        st.session_state.current_q_group = user_data.get("current_q_group", [])
        st.session_state.result_log = {}
        st.session_state.user_data_loaded = True
    if "result_log" not in st.session_state:
        st.session_state.result_log = {}
    with st.sidebar:
        # セッション状態の表示
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
            save_user_data(uid, st.session_state)  # ★ username ではなく uid
            for k in ["user_logged_in", "id_token", "refresh_token", "name", "username", "email", "uid", "user_data_loaded", "token_timestamp"]:
                if k in st.session_state:
                    del st.session_state[k]
            
            # クッキー破棄
            if cookies:
                try:
                    for ck in ["refresh_token", "uid", "email"]:
                        cookies[ck] = ""
                        cookies.delete(ck)
                    cookies.save()
                except Exception as e:
                    print(f"Cookie deletion error: {e}")
            
            st.rerun()
        if page == "演習":
            DEFAULT_NEW_CARDS_PER_DAY = 10
            if "new_cards_per_day" not in st.session_state:
                user_data = load_user_data(uid)  # ★ uid で読む
                st.session_state["new_cards_per_day"] = user_data.get("new_cards_per_day", DEFAULT_NEW_CARDS_PER_DAY)
            new_cards_per_day = st.number_input("新規カード/日", min_value=1, max_value=100, value=st.session_state["new_cards_per_day"], step=1, key="new_cards_per_day_input")
            if new_cards_per_day != st.session_state["new_cards_per_day"]:
                st.session_state["new_cards_per_day"] = new_cards_per_day
                user_data = load_user_data(uid)  # ★ uid で読む
                user_data["new_cards_per_day"] = new_cards_per_day
                db.collection("user_progress").document(uid).set(user_data, merge=True)  # ★ uid
            
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
                    save_user_data(uid, st.session_state)  # ★ username ではなく uid
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
            uid = st.session_state.get("uid")
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
            has_gakushi_permission = check_gakushi_permission(uid)
            mode_choices = ["回数別", "科目別","必修問題のみ"]
            if has_gakushi_permission:
                mode_choices.append("学士試験")
            mode = st.radio("出題形式を選択", mode_choices, key=f"mode_radio_{st.session_state.get('page_select', 'default')}")
            questions_to_load = []
            if mode == "回数別":
                selected_exam_num = st.selectbox("回数", ALL_EXAM_NUMBERS)
                if selected_exam_num:
                    available_sections = sorted([s[-1] for s in ALL_EXAM_SESSIONS if s.startswith(selected_exam_num)])
                    selected_section_char = st.selectbox("領域", available_sections)
                    if selected_section_char:
                        selected_session = f"{selected_exam_num}{selected_section_char}"
                        questions_to_load = [q for q in ALL_QUESTIONS if q.get("number", "").startswith(selected_session)]
            elif mode == "科目別":
                KISO_SUBJECTS = ["解剖学", "歯科理工学", "組織学", "生理学", "病理学", "薬理学", "微生物学・免疫学", "衛生学", "発生学・加齢老年学", "生化学"]
                RINSHOU_SUBJECTS = ["保存修復学", "歯周病学", "歯内治療学", "クラウンブリッジ学", "部分床義歯学", "全部床義歯学", "インプラント学", "口腔外科学", "歯科放射線学", "歯科麻酔学", "矯正歯科学", "小児歯科学"]
                group = st.radio("科目グループ", ["基礎系科目", "臨床系科目"])
                subjects_to_display = KISO_SUBJECTS if group == "基礎系科目" else RINSHOU_SUBJECTS
                available_subjects = [s for s in ALL_SUBJECTS if s in subjects_to_display]
                selected_subject = st.selectbox("科目", available_subjects)
                if selected_subject: questions_to_load = [q for q in ALL_QUESTIONS if q.get("subject") == selected_subject]
            elif mode == "必修問題のみ":
                questions_to_load = [q for q in ALL_QUESTIONS if q.get("number") in HISSHU_Q_NUMBERS_SET]
            elif mode == "学士試験":
                # 年度・試験種別・領域の選択肢
                gakushi_years = ["2025", "2024", "2023", "2022", "2021"]
                # 正しい6種類のリストに修正
                gakushi_types = ["1-1", "1-2", "1-3", "1再", "2", "2再"]
                gakushi_areas = ["A", "B", "C", "D"]
                selected_year = st.selectbox("年度", gakushi_years, key="gakushi_year_select")
                selected_type = st.selectbox("試験種別", gakushi_types, key="gakushi_type_select")
                selected_area = st.selectbox("領域", gakushi_areas, key="gakushi_area_select")
                prefix = f"G{selected_year[-2:]}-{selected_type}-{selected_area}-"
                questions_to_load = [q for q in ALL_QUESTIONS if q.get("number", "").startswith(prefix)]
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
                    st.success("Firebase接続もリセットしました")
                except Exception as e:
                    st.warning(f"Firebase接続リセット中にエラー: {e}")
                
                # セッション状態の問題データをクリア
                if 'questions_loaded' in st.session_state:
                    del st.session_state['questions_loaded']
                
                st.success("キャッシュをクリアしました。ページを再読み込みします...")
                st.rerun()
            
            # Firebase Storageデバッグ機能
            if st.button("🔍 Firebase Storage確認", help="画像ファイルの存在確認"):
                try:
                    # gakushi/2025/1-1/ フォルダの内容を確認
                    prefix = "gakushi/2025/1-1/"
                    blobs = list(bucket.list_blobs(prefix=prefix, max_results=10))
                    
                    if blobs:
                        st.success(f"✅ {prefix} フォルダに {len(blobs)} 個のファイルが見つかりました:")
                        for blob in blobs:
                            st.write(f"  - {blob.name} (サイズ: {blob.size} bytes)")
                            # 特定のファイルをチェック
                            if "G25-1-1-A-68a.jpg" in blob.name:
                                st.success(f"🎯 対象ファイル発見: {blob.name}")
                    else:
                        st.warning(f"⚠️ {prefix} フォルダにファイルが見つかりません")
                        
                    # バケット全体の情報も表示
                    st.write(f"バケット名: {bucket.name}")
                    
                except Exception as e:
                    st.error(f"Firebase Storage確認エラー: {str(e)}")
                    import traceback
                    st.code(traceback.format_exc())
            
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