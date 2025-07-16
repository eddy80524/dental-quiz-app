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
    st.error(f"[DEBUG] st.secrets: {dict(st.secrets)}")
    st.stop()

# --- Firebase Authentication REST APIエンドポイント ---
#st.write("[DEBUG] st.secrets keys:", list(st.secrets.keys()))
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

# --- 認証UI ---
if not st.session_state.get("user_logged_in"):
    login_tab, register_tab = st.tabs(["ログイン", "新規登録"])

    with login_tab:
        st.subheader("メールアドレスでログイン")
        login_email = st.text_input("メールアドレス", key="login_email")
        login_password = st.text_input("パスワード", type="password", key="login_password")
        login_btn = st.button("ログイン", key="login_btn")
        login_error = ""
        if login_btn:
            if not login_email or not login_password:
                login_error = "メールアドレスとパスワードを入力してください。"
            else:
                result = firebase_signin(login_email, login_password)
                if "idToken" in result:
                    st.session_state["user_logged_in"] = login_email
                    st.session_state["id_token"] = result["idToken"]
                    st.session_state["refresh_token"] = result["refreshToken"]
                    st.session_state["name"] = login_email.split("@")[0]
                    st.session_state["username"] = login_email
                    st.success("ログインに成功しました！")
                    st.rerun()
                else:
                    login_error = result.get("error", {}).get("message", "ログインに失敗しました。")
        if login_error:
            st.error(login_error)

    with register_tab:
        st.subheader("新規ユーザー登録")
        reg_email = st.text_input("メールアドレス", key="reg_email")
        reg_password = st.text_input("パスワード（6文字以上）", type="password", key="reg_password")
        reg_btn = st.button("登録", key="reg_btn")
        reg_error = ""
        if reg_btn:
            if not reg_email or not reg_password:
                reg_error = "メールアドレスとパスワードを入力してください。"
            elif len(reg_password) < 6:
                reg_error = "パスワードは6文字以上で入力してください。"
            else:
                result = firebase_signup(reg_email, reg_password)
                if "idToken" in result:
                    st.success("ユーザー登録が完了しました。ログインしてください。")
                else:
                    reg_error = result.get("error", {}).get("message", "登録に失敗しました。")
        if reg_error:
            st.error(reg_error)
    st.stop()

# --- ログアウトボタン ---
with st.sidebar:
    if st.button("ログアウト", key="logout_btn"):
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
        return doc.to_dict().get("cards", {}) if doc.exists else {}
    return {}

def save_user_data(user_id, cards_data):
    if db and user_id:
        doc_ref = db.collection("user_progress").document(user_id)
        doc_ref.set({"cards": cards_data})

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
    return re.sub(r'Ca2\+', '$\\\\mathrm{Ca^{2+}}$', text)

def sm2_update(card, quality, now=None):
    if now is None: now = datetime.datetime.now(datetime.timezone.utc)
    EF, n, I = card.get("EF", 2.5), card.get("n", 0), card.get("I", 0)
    if quality < 3:
        n = 0
        I = 10 / 1440 # 10分
    else:
        if n == 0: I = 1
        elif n == 1: I = 4
        else:
            EF = max(EF + (0.1 - (5-quality)*(0.08 + (5-quality)*0.02)), 1.3)
            I = round(I * EF)
        n += 1
    next_review_dt = now + datetime.timedelta(days=I)
    card["history"] = card.get("history", []) + [{"timestamp": now.isoformat(), "quality": quality, "interval": I, "EF": EF}]
    card.update({"EF": EF, "n": n, "I": I, "next_review": next_review_dt.isoformat(), "quality": quality})
    return card

# --- セッションステート初期化 ---
if "user_logged_in" not in st.session_state or st.session_state.user_logged_in != username:
    st.session_state.cards = load_user_data(username)
    st.session_state.main_queue = []
    st.session_state.short_term_review_queue = []
    st.session_state.current_q_group = []
    st.session_state.result_log = {}
    st.session_state.user_logged_in = username
    st.rerun()

# result_logの初期化を保証
if "result_log" not in st.session_state:
    st.session_state.result_log = {}

# --- サイドバー ---
with st.sidebar:
    st.success(f"{name} としてログイン中")
    st.header("出題設定")
    mode = st.radio("出題形式を選択", ["回数別", "科目別"])
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
                st.markdown(f"- `{q_num}` : **{last_eval_mark}** ({timestamp_str})")



# --- メインロジック ---
def get_next_q_group():
    if st.session_state.get("short_term_review_queue"):
        return st.session_state.short_term_review_queue.pop(0)
    if st.session_state.get("main_queue"):
        return st.session_state.main_queue.pop(0)
    return []

if not st.session_state.get("current_q_group"):
    st.session_state.current_q_group = get_next_q_group()

current_q_group = st.session_state.get("current_q_group", [])
if not current_q_group:
    st.info("学習を開始するには、サイドバーで問題を選択してください。")
    st.stop()

# --- 問題表示と解答・評価 ---
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
    # 解答フォーム
    with st.form(key=f"answer_form_{group_id}"):
        for q in q_objects:
            st.markdown(f"#### {q['number']}")
            st.markdown(chem_latex(q.get('question', '')))
            if "choices" in q and q["choices"]:
                shuffled_choices, _ = get_shuffled_choices(q)
                for i, choice_item in enumerate(shuffled_choices):
                    if isinstance(choice_item, dict):
                        label = f"{chr(65 + i)}. {chem_latex(choice_item.get('text', str(choice_item)))}"
                    else:
                        label = f"{chr(65 + i)}. {chem_latex(str(choice_item))}"
                    st.checkbox(label, key=f"user_selection_{q['number']}_{i}")
            else:
                st.text_input("回答を入力", key=f"free_input_{q['number']}")
        submitted_check = st.form_submit_button("回答をチェック", type="primary")
        skipped = st.form_submit_button("スキップ", type="secondary")
        if submitted_check:
            for q in q_objects:
                if "choices" in q and q["choices"]:
                    user_answers = []
                    shuffled_choices, shuffle_indices = get_shuffled_choices(q)
                    for i, choice_item in enumerate(shuffled_choices):
                        if st.session_state.get(f"user_selection_{q['number']}_{i}"):
                            original_index = shuffle_indices[i]
                            user_answers.append(chr(65 + original_index))
                    correct_answers = sorted(list(q.get("answer", "")))
                    st.session_state.result_log[q['number']] = (sorted(user_answers) == correct_answers)
                else:
                    user_input = st.session_state.get(f"free_input_{q['number']}", "").strip()
                    correct_answer = str(q.get("answer", "")).strip()
                    st.session_state.result_log[q['number']] = (user_input == correct_answer)
            st.session_state[f"checked_{group_id}"] = True
            st.rerun()
        elif skipped:
            st.session_state.current_q_group = get_next_q_group()
            for key in list(st.session_state.keys()):
                if key.startswith("checked_") or key.startswith("user_selection_") or key.startswith("shuffled_") or key.startswith("free_input_"):
                    del st.session_state[key]
            st.rerun()
    # フォームの外で画像を表示
    display_images = case_data.get('image_urls') if case_data else first_q.get('image_urls')
    if display_images:
        st.image(display_images, use_column_width=True)
else:
    # 回答フォーム（選択内容・入力内容はそのまま表示）
    for q in q_objects:
        st.markdown(f"#### {q['number']}")
        st.markdown(chem_latex(q.get('question', '')))
        if "choices" in q and q["choices"]:
            shuffled_choices, shuffle_indices = get_shuffled_choices(q)
            correct_indices = [ord(l) - 65 for l in q.get("answer", "") if l.isalpha()]
            correct_labels = [chr(65 + shuffle_indices.index(i)) for i in correct_indices if i < len(shuffle_indices)]
            for i, choice_item in enumerate(shuffled_choices):
                if isinstance(choice_item, dict):
                    label = f"{chr(65 + i)}. {chem_latex(choice_item.get('text', str(choice_item)))}"
                else:
                    label = f"{chr(65 + i)}. {chem_latex(str(choice_item))}"
                st.checkbox(label, key=f"user_selection_{q['number']}_{i}", disabled=True)
            # --- ここからUX改善 ---
            is_correct = st.session_state.result_log.get(q['number'], False)
            if is_correct:
                st.markdown("<span style='font-size:1.5em; color:green;'>✓ 正解！</span>", unsafe_allow_html=True)
            else:
                st.markdown("<span style='font-size:1.5em; color:red;'>× 不正解</span>", unsafe_allow_html=True)
                st.markdown(f"<span style='color:blue;'>正解: {'・'.join(correct_labels)}</span>", unsafe_allow_html=True)
        else:
            st.text_input("回答を入力", key=f"free_input_{q['number']}", disabled=True)
            is_correct = st.session_state.result_log.get(q['number'], False)
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
            quality = eval_map[selected_eval_label]
            add_to_short_term_review = False
            for q_num_str in current_q_group:
                card = st.session_state.cards.get(q_num_str, {})
                updated_card = sm2_update(card, quality)
                st.session_state.cards[q_num_str] = updated_card
                # --- 短期復習キュー追加ロジック ---
                if quality < 4 and updated_card.get("I", 1) < 0.015:
                    add_to_short_term_review = True
            if add_to_short_term_review and current_q_group not in st.session_state.short_term_review_queue:
                st.session_state.short_term_review_queue.append(current_q_group)
            save_user_data(username, st.session_state.cards)
            st.session_state.current_q_group = get_next_q_group()
            for key in list(st.session_state.keys()):
                if key.startswith("checked_") or key.startswith("user_selection_") or key.startswith("shuffled_") or key.startswith("free_input_"):
                    del st.session_state[key]
            st.rerun()
    # フォームの外で画像を表示
    display_images = case_data.get('image_urls') if case_data else first_q.get('image_urls')
    if display_images:
        st.image(display_images, use_column_width=True)