import streamlit as st
import json
import os
import random
import time
import datetime
import re
from collections import Counter
import firebase_admin
from firebase_admin import credentials, firestore
import requests
import tempfile
import collections.abc
import pandas as pd

# plotlyインポート（未インストール時の案内付き）
# 必ずこの場所（利用する場所より前）で定義します
try:
    import plotly.express as px
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

# --- ページ設定 (スクリプトの最初に一度だけ呼び出す) ---
st.set_page_config(layout="wide")

# --- Firebase初期化 ---
# .streamlit/secrets.toml の内容を直接利用します。
def to_dict(obj):
    if isinstance(obj, collections.abc.Mapping):
        return {k: to_dict(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [to_dict(i) for i in obj]
    else:
        return obj

# --- デバッグ用: secretsの内容を画面に表示 ---
#with st.expander("[DEBUG] st.secrets の内容 (本番運用時は削除)"):
    #st.write(dict(st.secrets))
    #st.write("firebase_api_key:", st.secrets.get("firebase_api_key"))

try:
    # secretsから一時ファイルに書き出してパスを渡す（AttrDict→dict変換）
    firebase_creds = to_dict(st.secrets["firebase_credentials"])
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        json.dump(firebase_creds, f)
        temp_path = f.name
    creds = credentials.Certificate(temp_path)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(creds)
    db = firestore.client()
except Exception as e:
    st.error(f"Firebaseの認証情報が正しく設定されていません。.streamlit/secrets.tomlファイルを確認してください。\n詳細: {e}")
    # st.secretsが存在しない場合はデバッグ出力を省略
    st.stop()

# --- Firebase Authentication REST APIエンドポイント ---
FIREBASE_API_KEY = st.secrets["firebase_api_key"]
FIREBASE_AUTH_SIGNUP_URL = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
FIREBASE_AUTH_SIGNIN_URL = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"

def firebase_signup(email, password):
    payload = {"email": email, "password": password, "returnSecureToken": True}
    r = requests.post(FIREBASE_AUTH_SIGNUP_URL, json=payload)
    return r.json()

def firebase_signin(email, password):
    payload = {"email": email, "password": password, "returnSecureToken": True}
    r = requests.post(FIREBASE_AUTH_SIGNIN_URL, json=payload)
    return r.json()

# --- Firestore連携関数 ---
def load_user_data(user_id):
    if db and user_id:
        doc_ref = db.collection("user_progress").document(user_id)
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict()
            # ▼▼▼ キューの読み込みロジックを追加 ▼▼▼
            main_queue_str_list = data.get("main_queue", [])
            short_term_review_queue_str_list = data.get("short_term_review_queue", [])
            current_q_group_str = data.get("current_q_group", "")

            main_queue = [item.split(',') for item in main_queue_str_list if item]
            short_term_review_queue = [item.split(',') for item in short_term_review_queue_str_list if item]
            current_q_group = current_q_group_str.split(',') if current_q_group_str else []
            # ▲▲▲ ここまで追加 ▲▲▲
            return {
                "cards": data.get("cards", {}),
                "main_queue": main_queue,
                "short_term_review_queue": short_term_review_queue,
                "current_q_group": current_q_group
            }
    return {"cards": {}, "main_queue": [], "short_term_review_queue": [], "current_q_group": []}

def save_user_data(user_id, cards_data, main_queue=None, short_term_review_queue=None, current_q_group=None):
    def flatten_and_str(obj):
        # 再帰的にlist/setをフラット化しstr型のみ返す
        if isinstance(obj, (list, set)):
            result = []
            for item in obj:
                result.extend(flatten_and_str(item))
            return result
        elif isinstance(obj, dict):
            # dictはキーのみstr化
            return [str(k) for k in obj.keys()]
        elif obj is None:
            return []
        else:
            return [str(obj)]
    if db and user_id:
        doc_ref = db.collection("user_progress").document(user_id)
        payload = {"cards": cards_data}
        if main_queue is not None:
            # 各グループをカンマ区切り文字列に変換
            payload["main_queue"] = [','.join(flatten_and_str(group)) for group in main_queue]
        if short_term_review_queue is not None:
            payload["short_term_review_queue"] = [','.join(flatten_and_str(group)) for group in short_term_review_queue]
        if current_q_group is not None:
            payload["current_q_group"] = ','.join(flatten_and_str(current_q_group))
        # デバッグ: 型チェック（dict/setが混入していないか）
        for k, v in payload.items():
            if k != "cards" and isinstance(v, (dict, set)):
                print(f"[ERROR] Firestore保存前: {k}が不正な型: {type(v)}")
                return
        doc_ref.set(payload)

# --- 認証フローの統合 ---
if not st.session_state.get("user_logged_in"):
    st.title("ログイン／新規登録")
    tab_login, tab_signup = st.tabs(["ログイン", "新規登録"])
    with tab_login:
        login_email = st.text_input("メールアドレス", key="login_email")
        login_password = st.text_input("パスワード", type="password", key="login_password")
        if st.button("ログイン", key="login_btn"):
            result = firebase_signin(login_email, login_password)
            if "idToken" in result:
                st.session_state["name"] = login_email.split("@")[0]
                st.session_state["username"] = login_email
                st.session_state["id_token"] = result["idToken"]
                st.session_state["user_logged_in"] = login_email
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
    # --- ログイン済みユーザー情報の取得 ---
    name = st.session_state["name"]
    username = st.session_state["username"]
    # --- ログアウトボタン ---
    with st.sidebar:
        if st.button("ログアウト", key="logout_btn"):
            save_user_data(
                username,
                st.session_state.cards,
                st.session_state.main_queue,
                st.session_state.short_term_review_queue,
                st.session_state.current_q_group
            )
            for k in ["user_logged_in", "id_token", "refresh_token", "name", "username"]:
                if k in st.session_state:
                    del st.session_state[k]
            st.rerun()
# --- 以降、認証済みユーザーのみアプリ本体が動作 ---

# --- ログインユーザー情報の取得 ---
name = st.session_state["name"]
username = st.session_state["username"]

# --- Firestore連携関数 ---
def load_user_data(user_id):
    if db and user_id:
        doc_ref = db.collection("user_progress").document(user_id)
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict()
            # ▼▼▼ キューの読み込みロジックを追加 ▼▼▼
            main_queue_str_list = data.get("main_queue", [])
            short_term_review_queue_str_list = data.get("short_term_review_queue", [])
            current_q_group_str = data.get("current_q_group", "")

            main_queue = [item.split(',') for item in main_queue_str_list if item]
            short_term_review_queue = [item.split(',') for item in short_term_review_queue_str_list if item]
            current_q_group = current_q_group_str.split(',') if current_q_group_str else []
            # ▲▲▲ ここまで追加 ▲▲▲
            return {
                "cards": data.get("cards", {}),
                "main_queue": main_queue,
                "short_term_review_queue": short_term_review_queue,
                "current_q_group": current_q_group
            }
    return {"cards": {}, "main_queue": [], "short_term_review_queue": [], "current_q_group": []}

def save_user_data(user_id, cards_data, main_queue=None, short_term_review_queue=None, current_q_group=None):
    def flatten_and_str(obj):
        # 再帰的にlist/setをフラット化しstr型のみ返す
        if isinstance(obj, (list, set)):
            result = []
            for item in obj:
                result.extend(flatten_and_str(item))
            return result
        elif isinstance(obj, dict):
            # dictはキーのみstr化
            return [str(k) for k in obj.keys()]
        elif obj is None:
            return []
        else:
            return [str(obj)]
    if db and user_id:
        doc_ref = db.collection("user_progress").document(user_id)
        payload = {"cards": cards_data}
        if main_queue is not None:
            # 各グループをカンマ区切り文字列に変換
            payload["main_queue"] = [','.join(flatten_and_str(group)) for group in main_queue]
        if short_term_review_queue is not None:
            payload["short_term_review_queue"] = [','.join(flatten_and_str(group)) for group in short_term_review_queue]
        if current_q_group is not None:
            payload["current_q_group"] = ','.join(flatten_and_str(current_q_group))
        # デバッグ: 型チェック（dict/setが混入していないか）
        for k, v in payload.items():
            if k != "cards" and isinstance(v, (dict, set)):
                print(f"[ERROR] Firestore保存前: {k}が不正な型: {type(v)}")
                return
        doc_ref.set(payload)

# --- データ読み込み関数 ---
@st.cache_data
def load_master_data():
    # デプロイ環境によってはパスの指定方法の調整が必要になる場合があります
    master_file_path = os.path.join('data', 'master_questions_final.json')
    if os.path.exists(master_file_path):
        with open(master_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('cases', {}), data.get('questions', [])
    st.error(f"マスターファイルが見つかりません: {master_file_path}")
    return {}, []

# --- データ準備 ---
CASES, ALL_QUESTIONS = load_master_data()
if not ALL_QUESTIONS:
    st.error("問題データの読み込みに失敗したため、アプリケーションを開始できません。")
    st.stop()

ALL_QUESTIONS_DICT = {q['number']: q for q in ALL_QUESTIONS}
ALL_SUBJECTS = sorted(list(set(q['subject'] for q in ALL_QUESTIONS if q.get('subject') and q.get('subject') != '（未分類）')))
ALL_EXAM_NUMBERS = sorted(list(set(re.match(r'(\d+)', q['number']).group(1) for q in ALL_QUESTIONS if re.match(r'(\d+)', q['number']))), key=int, reverse=True)
ALL_EXAM_SESSIONS = sorted(list(set(re.match(r'(\d+[A-D])', q['number']).group(1) for q in ALL_QUESTIONS if re.match(r'(\d+[A-D])', q['number']))))


# --- ヘルパー関数群 ---
def get_shuffled_choices(q):
    key = f"shuffled_{q['number']}"
    if key not in st.session_state or len(st.session_state.get(key, [])) != len(q.get("choices", [])):
        indices = list(range(len(q.get("choices", []))))
        random.shuffle(indices)
        st.session_state[key] = indices
    return [q["choices"][i] for i in st.session_state[key]], st.session_state[key]

def chem_latex(text):
    # re.subのreplacementでバックスラッシュが問題になるためstr.replaceで十分
    return text.replace('Ca2+', '$\\mathrm{Ca^{2+}}$')

def is_ordering_question(q):
    # 「順番に並べよ」「正しい順序」「適切な順序」「正しい順番」などを検出
    text = q.get("question", "")
    keywords = ["順番に並べよ", "正しい順序", "適切な順序", "正しい順番", "順序で"]
    return any(k in text for k in keywords)

def sm2_update(card, quality, now=None):
    if now is None: now = datetime.datetime.now(datetime.timezone.utc)
    EF, n, I = card.get("EF", 2.5), card.get("n", 0), card.get("I", 0)
    # Anki方式に忠実な分岐
    if quality == 1:  # もう一度（完全失敗）
        n = 0
        EF = max(EF - 0.3, 1.3)  # EF大幅減少
        I = 10 / 1440  # 10分
    elif quality == 2:  # 難しい（部分的失敗）
        EF = max(EF - 0.15, 1.3)  # EF少し減少
        I = max(card.get("I", 1) * 0.5, 10 / 1440)  # 前回間隔の半分、最短10分
        # nは維持
    elif quality == 4 or quality == 5:  # 普通・簡単（成功）
        if n == 0:
            I = 1  # 1日
        elif n == 1:
            I = 4  # 4日
        else:
            EF = max(EF + (0.1 - (5-quality)*(0.08 + (5-quality)*0.02)), 1.3)
            I = card.get("I", 1) * EF
        n += 1
        if quality == 5:
            I *= 1.3  # "簡単"はさらに間隔拡大
    else:
        # 万が一その他の値
        n = 0
        I = 10 / 1440
    next_review_dt = now + datetime.timedelta(days=I)
    card["history"] = card.get("history", []) + [{"timestamp": now.isoformat(), "quality": quality, "interval": I, "EF": EF}]
    card.update({"EF": EF, "n": n, "I": I, "next_review": next_review_dt.isoformat(), "quality": quality})
    return card

# --- セッションステート初期化 ---
if "user_logged_in" not in st.session_state or st.session_state.user_logged_in != username:
    user_data = load_user_data(username)
    st.session_state.cards = user_data.get("cards", {})
    st.session_state.main_queue = user_data.get("main_queue", [])
    st.session_state.short_term_review_queue = user_data.get("short_term_review_queue", [])
    st.session_state.current_q_group = user_data.get("current_q_group", [])
    st.session_state.result_log = {}
    st.session_state.user_logged_in = username
    st.rerun()

# result_logの初期化を保証
if "result_log" not in st.session_state:
    st.session_state.result_log = {}

# --- サイドバー（1か所だけで描画） ---
with st.sidebar:
    st.success(f"{name} としてログイン中")
    # ページ切り替えUI
    page = st.radio("ページ選択", ["演習", "検索"], key="page_select")

    if page == "演習":
        # 新規カード/日 入力UI（演習ページのみ表示）
        DEFAULT_NEW_CARDS_PER_DAY = 10
        if "new_cards_per_day" not in st.session_state:
            user_data = load_user_data(username)
            st.session_state["new_cards_per_day"] = user_data.get("new_cards_per_day", DEFAULT_NEW_CARDS_PER_DAY)
        new_cards_per_day = st.number_input("新規カード/日", min_value=1, max_value=100, value=st.session_state["new_cards_per_day"], step=1, key="new_cards_per_day_input")
        if new_cards_per_day != st.session_state["new_cards_per_day"]:
            st.session_state["new_cards_per_day"] = new_cards_per_day
            user_data = load_user_data(username)
            user_data["new_cards_per_day"] = new_cards_per_day
            db.collection("user_progress").document(username).set(user_data, merge=True)

        # --- 進捗が残っている場合は「前回の続きから再開」ボタンを表示 ---
        has_progress = (
            st.session_state.get("main_queue") or
            st.session_state.get("short_term_review_queue") or
            st.session_state.get("current_q_group")
        )
        if has_progress and st.session_state.get("current_q_group"):
            if st.button("前回の続きから再開", key="resume_btn", type="primary"):
                st.session_state["resume_requested"] = True
                st.rerun()
            # --- 「演習を終了」ボタンを追加 ---
            if st.button("演習を終了", key="end_session_btn", type="secondary"):
                # ▼▼▼ 進捗保存を追加 ▼▼▼
                save_user_data(
                    username,
                    st.session_state.cards,
                    st.session_state.main_queue,
                    st.session_state.short_term_review_queue,
                    st.session_state.current_q_group
                )
                # ▲▲▲ ここまで追加 ▲▲▲
                st.session_state["main_queue"] = []
                st.session_state["short_term_review_queue"] = []
                st.session_state["current_q_group"] = []
                st.session_state.pop("resume_requested", None)
                # checked_やuser_selection_などの状態もクリア
                for key in list(st.session_state.keys()):
                    if key.startswith("checked_") or key.startswith("user_selection_") or key.startswith("shuffled_") or key.startswith("free_input_"):
                        del st.session_state[key]
                st.rerun()
            st.markdown("---")
        # 出題設定UIは常に表示
        st.header("出題設定")
        # --- 既存の出題設定 ---
        mode = st.radio("出題形式を選択", ["回数別", "科目別", "CBTモード（写真問題のみ）"], key=f"mode_radio_{st.session_state.get('page_select', 'default')}")
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
        elif mode == "CBTモード（写真問題のみ）":
            # 写真問題のみ抽出
            questions_to_load = [q for q in ALL_QUESTIONS if q.get("image_urls")]
        order_mode = st.selectbox("出題順", ["順番通り", "シャッフル"])
        if order_mode == "シャッフル":
            random.shuffle(questions_to_load)
        else:
            questions_to_load = sorted(questions_to_load, key=lambda q: q.get('number', ''))

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
                # 古い解答結果をクリア
                for key in list(st.session_state.keys()):
                    if key.startswith("checked_") or key.startswith("user_selection_") or key.startswith("shuffled_"):
                        del st.session_state[key]
                st.session_state.pop("resume_requested", None)
                # cardsも選択した問題だけで初期化 → 既存cardsを残しつつ未登録のみ追加
                if "cards" not in st.session_state:
                    st.session_state.cards = {}
                for q in questions_to_load:
                    if q['number'] not in st.session_state.cards:
                        st.session_state.cards[q['number']] = {}
                # today_due_cardsとcurrent_q_numもリセット
                st.session_state.pop("today_due_cards", None)
                st.session_state.pop("current_q_num", None)
                st.rerun()

        # cardsの初期化を保証
        if "cards" not in st.session_state:
            st.session_state.cards = {}

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
                    # 問題ジャンプ機能
                    jump_btn = st.button(f"{q_num}", key=f"jump_{q_num}")
                    st.markdown(f"- `{q_num}` : **{last_eval_mark}** ({timestamp_str})", unsafe_allow_html=True)
                    if jump_btn:
                        st.session_state.current_q_group = [q_num]
                        # checked_などの状態をクリア
                        for key in list(st.session_state.keys()):
                            if key.startswith("checked_") or key.startswith("user_selection_") or key.startswith("shuffled_") or key.startswith("free_input_"):
                                del st.session_state[key]
                        st.rerun()


# --- メインロジック ---
def render_practice_page():
    # --- 「演習」ページのロジック ---
    def get_next_q_group():
        if st.session_state.get("short_term_review_queue"):
            return st.session_state.short_term_review_queue.pop(0)
        if st.session_state.get("main_queue"):
            return st.session_state.main_queue.pop(0)
        return []

    if not st.session_state.get("current_q_group"):
        st.session_state.current_q_group = get_next_q_group()

    current_q_group = st.session_state.get("current_q_group", [])
    if not current_q_group and not st.session_state.get("main_queue") and not st.session_state.get("short_term_review_queue"):
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
        # --- 解答フォーム ---
        with st.form(key=f"answer_form_{group_id}"):
            for q in q_objects:
                st.markdown(f"#### {q['number']}")
                st.markdown(chem_latex(q.get('question', '')))
                if is_ordering_question(q):
                    st.markdown("##### 選択肢")
                    for choice in q.get("choices", []):
                        st.markdown(f"- {choice}")
                    st.text_input("解答を順番に入力してください（例: CBEAD）", key=f"order_input_{q['number']}")
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
                        user_input = st.session_state.get(f"order_input_{q['number']}", "").strip().upper().replace(" ", "")
                        correct_answer = answer_str.strip().upper().replace(" ", "")
                        st.session_state.result_log[q['number']] = (user_input == correct_answer)
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
    else: # --- 解答チェック後の表示 ---
        for q in q_objects:
            st.markdown(f"#### {q['number']}")
            st.markdown(chem_latex(q.get('question', '')))
            is_correct = st.session_state.result_log.get(q['number'], False)
            if is_ordering_question(q):
                st.text_input("あなたの解答", value=st.session_state.get(f"order_input_{q['number']}", ""), disabled=True)
                if is_correct:
                    st.markdown("<span style='font-size:1.5em; color:green;'>✓ 正解！</span>", unsafe_allow_html=True)
                else:
                    st.markdown("<span style='font-size:1.5em; color:red;'>× 不正解</span>", unsafe_allow_html=True)
                    st.markdown(f"<span style='color:blue;'>正解: {q.get('answer', '')}</span>", unsafe_allow_html=True)
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
                    add_to_short_term_review = False
                    for q_num_str in current_q_group:
                        card = st.session_state.cards.get(q_num_str, {})
                        updated_card = sm2_update(card, quality)
                        st.session_state.cards[q_num_str] = updated_card
                        if quality < 4 and updated_card.get("I", 1) < 0.015:
                            add_to_short_term_review = True
                    if add_to_short_term_review and current_q_group not in st.session_state.short_term_review_queue:
                        st.session_state.short_term_review_queue.append(current_q_group)
                    save_user_data(
                        username,
                        st.session_state.cards,
                        st.session_state.main_queue,
                        st.session_state.short_term_review_queue,
                        get_next_q_group() if st.session_state.main_queue or st.session_state.short_term_review_queue else []
                    )
                st.session_state.current_q_group = get_next_q_group()
                for key in list(st.session_state.keys()):
                    if key.startswith(("checked_", "user_selection_", "shuffled_", "free_input_", "order_input_")):
                        del st.session_state[key]
                st.rerun()

    # 画像表示をフォームや結果表示の「後」に移動
    display_images = case_data.get('image_urls') if case_data else first_q.get('image_urls')
    if display_images:
        st.image(display_images, use_container_width=True)

def render_search_page():
    # --- 「検索」ページのロジックをすべてここに移動 ---
    st.title("検索・進捗ページ")
    questions_data = []
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    for q in ALL_QUESTIONS:
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
            "id": q_num,
            "year": int(q_num[:3]) if q_num[:3].isdigit() else None,
            "region": q_num[3] if len(q_num) >= 4 and q_num[3] in "ABCD" else None,
            "category": q.get("category", ""),
            "subject": q.get("subject", ""),
            "level": level,
            "ef": card.get("EF"),
            "interval": card.get("I"),
            "repetitions": card.get("n"),
            "history": card.get("history", []),
            "days_until_due": days_until_due
        })
    df = pd.DataFrame(questions_data)
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype('Int64')
    with st.sidebar:
        st.header("絞り込み条件")
        years_sorted = sorted([int(x) for x in ALL_EXAM_NUMBERS if str(x).isdigit()])
        regions_sorted = sorted([r for r in df["region"].dropna().unique() if r in ["A","B","C","D"]])
        subjects_sorted = sorted(df["subject"].dropna().unique())
        levels_sorted = ["未学習", "レベル0", "レベル1", "レベル2", "レベル3", "レベル4", "習得済み"]
        years = st.multiselect("回数", years_sorted, default=years_sorted)
        regions = st.multiselect("領域", regions_sorted, default=regions_sorted)
        subjects = st.multiselect("科目", subjects_sorted, default=subjects_sorted)
        levels = st.multiselect("習熟度", levels_sorted, default=levels_sorted)
    filtered_df = df.copy()
    if years: filtered_df = filtered_df[filtered_df["year"].isin(years)]
    if regions: filtered_df = filtered_df[filtered_df["region"].isin(regions)]
    if subjects: filtered_df = filtered_df[filtered_df["subject"].isin(subjects)]
    if levels: filtered_df = filtered_df[filtered_df["level"].isin(levels)]
    tab1, tab2, tab3 = st.tabs(["概要", "グラフ分析", "問題リスト検索"])
    with tab1:
        st.subheader("学習状況サマリー")
        if filtered_df.empty:
            st.warning("選択された条件に一致する問題がありません。")
        else:
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("##### カード習熟度分布")
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
                m = re.match(r"(\d+)([A-D])(\d+)", str(row_id))
                return (int(m.group(1)), m.group(2), int(m.group(3))) if m else (0, '', 0)
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

if page == "演習":
    render_practice_page()
elif page == "検索":
    render_search_page()