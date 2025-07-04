# app.py
import streamlit as st
import json
import os
from glob import glob
import random
import re
import pandas as pd
import time

def label_choices(choices):
    labels = []
    for i in range(len(choices)):
        label = ""
        n = i
        while True:
            label = chr(65 + n % 26) + label
            n = n // 26 - 1
            if n < 0:
                break
        labels.append(label)
    return [f"{labels[i]}. {c}" for i, c in enumerate(choices)]

def get_correct_label(answer, choices):
    labels = ["A", "B", "C", "D", "E", "F", "G", "H"]
    if isinstance(answer, list):
        return [f"{labels[i]}. {choices[i]}" for i, label in enumerate(labels) if label in answer and i < len(choices)]
    for i, label in enumerate(labels):
        if label == answer or str(label) == str(answer):
            if i < len(choices):
                return f"{label}. {choices[i]}"
            else:
                return label
    return answer

@st.cache_data
def load_all_quizzes(data_dir="data"):
    quizzes = {}
    for path in glob(os.path.join(data_dir, "dental_*.json")):
        print("読み込んでいるファイル:", path)
        fname = os.path.basename(path)
        key = fname.replace("dental_", "").replace(".json", "")
        with open(path, encoding="utf-8") as f:
            quizzes[key] = json.load(f)
    return quizzes

def get_num_choices(question_text):
    m = re.search(r'(\d+)つ選べ', question_text)
    if m:
        return int(m.group(1))
    return 1

def chem_latex(text):
    text = re.sub(r'Ca2\+', '$\\\\mathrm{Ca^{2+}}$', text)
    text = re.sub(r'Na\+', '$\\\\mathrm{Na^+}$', text)
    # 必要に応じて他のイオンも追加
    return text

# --- Streamlit App ---

quizzes = load_all_quizzes()

# 1. 回数（年度）リストを作成
years = sorted(set(k[:-1] for k in quizzes.keys()), reverse=True)

# 2. サイドバーで回数を選択
selected_year = st.sidebar.selectbox("回数を選んでください", years)

# 3. 選択した回数に対応する区分リストを作成
kubun_list = sorted([k[-1] for k in quizzes.keys() if k.startswith(selected_year)])

# 4. サイドバーで区分を選択
selected_kubun = st.sidebar.selectbox("区分を選んでください", kubun_list)

# 5. 選択された回数＋区分でデータ取得
selected_key = f"{selected_year}{selected_kubun}"
questions = quizzes[selected_key]

# --- 既存のサイドバー設定の直後に追加 ---

# キーワード検索ボックスをサイドバーに追加
search_keyword = st.sidebar.text_input("キーワードで検索", "")

# 検索キーワードが入力されている場合、該当する問題だけに絞り込む
if search_keyword:
    questions = [
        q for q in questions
        if search_keyword in q.get("question", "")
        or any(search_keyword in c for c in q.get("choices", []))
    ]
    # 問題がなければダミーを表示
    if not questions:
        st.warning("該当する問題がありません。")
        st.stop()

st.sidebar.title("設定")
st.sidebar.write(f"全 {len(questions)} 問題")

# 出題順の設定を追加
order_mode = st.sidebar.selectbox("出題順", ["順番通り", "シャッフル"], key="order_mode")

# ここでquestionsが空なら以降の処理を止める
if not questions:
    st.warning("該当する問題がありません。")
    st.stop()

# ここから下はquestionsが1つ以上ある前提でOK
question_numbers = [q_["number"] for q_ in questions]

if "idx" not in st.session_state:
    st.session_state.idx = 0

# indexがquestions数未満かつ0以上になるようにガード
index = st.session_state.idx if st.session_state.idx < len(question_numbers) else 0

selected_number = st.sidebar.selectbox(
    "問題番号で選択",
    options=question_numbers,
    index=index
)

for idx, q_ in enumerate(questions):
    if q_["number"] == selected_number:
        st.session_state.idx = idx
        break

q = questions[st.session_state.idx]

if "start_time" not in st.session_state or st.session_state.get("reset_flag", False):
    st.session_state.start_time = time.time()

if not st.session_state.get("checked", False):
    elapsed = int(time.time() - st.session_state.start_time)
else:
    elapsed = st.session_state.get("time_log", {}).get(q["number"], int(time.time() - st.session_state.start_time))

col1, col2 = st.columns([3, 1])
with col1:
    st.title("歯科医師国家試験")
with col2:
    st.markdown(f"<div style='text-align: right; font-size: 1.2em;'>経過時間: {elapsed} 秒</div>", unsafe_allow_html=True)

st.markdown(f"### {selected_key} ")
st.subheader(f"{q['number']}")


# --- 問題タイプごとに分岐 ---
if "questions" in q:
    # --- 2連問の処理 ---
    st.write(q.get("common_question", ""))

    # 2連問用の選択状態を保持する辞書を初期化/リセット
    selections_key = f"selections_{q['number']}"
    if selections_key not in st.session_state or st.session_state.get("reset_flag", False):
        st.session_state[selections_key] = {}

    # 各サブ問題を表示
    for subq in q["questions"]:
        st.markdown(f"**{subq['sub_number']}. {subq['question']}**")
        labeled_choices = label_choices(subq["choices"])
        sub_number = subq['sub_number']

        if sub_number not in st.session_state[selections_key]:
            st.session_state[selections_key][sub_number] = []

        selected_for_subq = []
        for i, label in enumerate(labeled_choices):
            key = f"chk_{q['number']}_{sub_number}_{i}"
            checked = label in st.session_state[selections_key][sub_number]
            disabled = st.session_state.get("checked", False)
            if st.checkbox(label, value=checked, key=key, disabled=disabled):
                selected_for_subq.append(label)
        
        if not st.session_state.get("checked", False):
            st.session_state[selections_key][sub_number] = selected_for_subq

    # --- 回答チェック (2連問) ---
    if st.button("回答をチェック", key=f"check_{q['number']}"):
        st.session_state.checked = True
        if "time_log" not in st.session_state: st.session_state.time_log = {}
        st.session_state.time_log[q["number"]] = int(time.time() - st.session_state.start_time)
        if "result_log" not in st.session_state: st.session_state.result_log = {}

        # 全てのサブ問題が正解しているかをチェック
        is_all_correct = True
        for subq in q["questions"]:
            sub_number = subq['sub_number']
            selected_labels = [c.split('.')[0] for c in st.session_state[selections_key].get(sub_number, [])]
            correct_answer = subq['answer']
            if set(selected_labels) != set(correct_answer):
                is_all_correct = False
                break
        st.session_state.result_log[q['number']] = is_all_correct
        st.rerun()

    # --- 結果表示 (2連問) ---
    if st.session_state.get("checked", False):
        is_all_correct = st.session_state.result_log.get(q['number'], False)
        if is_all_correct:
            st.success("✓ 正解！ (全ての小問に正解しました)")
        else:
            st.error("× 不正解…")
        
        for subq in q["questions"]:
            st.markdown(f"--- \n**問題 {subq['sub_number']} の正解**")
            correct_label = get_correct_label(subq['answer'], subq['choices'])
            st.info(f"正解は **{correct_label}** です")

elif "順番に並べよ" in q["question"]:
    # --- 並び替え問題の処理 ---
    st.write(q["question"])
    labeled_choices = label_choices(q["choices"])
    order_key = f"order_{q['number']}"
    if order_key not in st.session_state or st.session_state.get("reset_flag", False):
        st.session_state[order_key] = []

    selected_order = st.multiselect(
        "正しい順に選んでください（左から順）",
        options=labeled_choices,
        default=st.session_state[order_key],
        key=order_key
    )

    # 回答チェック
    if st.button("回答をチェック", key=f"check_{q['number']}"):
        st.session_state.checked = True
        correct_order = list(q["answer"])
        selected_labels = [c.split('.')[0] for c in selected_order]
        is_correct = selected_labels == correct_order
        if "result_log" not in st.session_state: st.session_state.result_log = {}
        st.session_state.result_log[q['number']] = is_correct
        st.rerun()

    # 結果表示
    if st.session_state.get("checked", False):
        is_correct = st.session_state.result_log.get(q['number'], False)
        correct_answer_text = get_correct_label(list(q["answer"]), q["choices"])
        if is_correct:
            st.success("✓ 正解！")
        else:
            st.error(f"× 不正解… 正解は **{' → '.join(correct_answer_text)}** です")
else:
    # --- 単問の処理 ---
    # st.write(q["question"]) ← この行を削除

    # 「◯つ選べ。」を太字にして強調＋化学式変換
    import re
    question_text = chem_latex(q["question"])
    question_text = re.sub(r'([2-9]\d*つ選べ)', r'**\1**', question_text)
    st.markdown(question_text)

    # 解答が数値の場合（オッズ比など）
    if not q["choices"]:
        user_answer = st.text_input("解答を入力してください", key=f"ans_{q['number']}", disabled=st.session_state.get("checked", False))
        if "selected_choices" not in st.session_state or st.session_state.get("reset_flag", False):
            st.session_state.selected_choices = ""
        if not st.session_state.get("checked", False):
            st.session_state.selected_choices = user_answer
    else: # 選択肢がある場合
        labeled_choices = label_choices([chem_latex(c) for c in q["choices"]])
        if "selected_choices" not in st.session_state or st.session_state.get("reset_flag", False):
            st.session_state.selected_choices = []

        selected = []
        for i, label in enumerate(labeled_choices):
            key = f"chk_{q['number']}_{i}"
            checked = label in st.session_state.selected_choices
            disabled = st.session_state.get("checked", False)
            if st.checkbox(label, value=checked, key=key, disabled=disabled):
                selected.append(label)
    
        if not st.session_state.get("checked", False):
            st.session_state.selected_choices = selected

    # --- 回答チェック (単問) ---
    if st.button("回答をチェック", key=f"check_{q['number']}"):
        st.session_state.checked = True
        if "time_log" not in st.session_state: st.session_state.time_log = {}
        st.session_state.time_log[q["number"]] = int(time.time() - st.session_state.start_time)
        if "result_log" not in st.session_state: st.session_state.result_log = {}

        is_correct = False
        if not q["choices"]: # 記述式
            if str(st.session_state.selected_choices) == str(q["answer"]):
                is_correct = True
        else: # 選択式
            num_choices = get_num_choices(q["question"])
            selected_labels = [c.split('.')[0] for c in st.session_state.selected_choices]
            # --- 正解が複数組み合わせパターンの場合の判定 ---
            is_correct = False
            if isinstance(q['answer'], str) and '/' in q['answer'] and num_choices > 1:
                # 例: "ABC/ABE/BCE/ACE"
                correct_patterns = [sorted(list(ans)) for ans in q['answer'].split('/')]
                if sorted(selected_labels) in correct_patterns:
                    is_correct = True
            else:
                # 既存の1つ選べ・複数選べ判定
                if isinstance(q['answer'], str) and '/' in q['answer']:
                    correct_answer = q['answer'].split('/')
                elif isinstance(q['answer'], str) and len(q['answer']) > 1 and num_choices > 1:
                    correct_answer = list(q['answer'])
                else:
                    correct_answer = [q['answer']]
                if num_choices == 1:
                    if len(selected_labels) == 1 and selected_labels[0] in correct_answer:
                        is_correct = True
                else:
                    if set(selected_labels) == set(correct_answer):
                        is_correct = True
        st.session_state.result_log[q['number']] = is_correct
        st.rerun()

    # --- 結果表示 (単問) ---
    if st.session_state.get("checked", False):
        is_correct = st.session_state.result_log.get(q['number'], False)
        num_choices = get_num_choices(q["question"])
        selected_labels = [c.split('.')[0] for c in st.session_state.selected_choices]

        # 複数組み合わせ正解パターン
        if isinstance(q['answer'], str) and '/' in q['answer'] and num_choices > 1:
            correct_patterns = [sorted(list(ans)) for ans in q['answer'].split('/')]
            selected_sorted = sorted(selected_labels)
            # ラベルのみで正解パターンを表示
            correct_patterns_text = [
                ''.join(sorted(ans)) for ans in q['answer'].split('/')
            ]
            your_pattern_text = ''.join(sorted(selected_labels))
            if is_correct:
                st.success(f"✓ 正解！ あなたの選択（{your_pattern_text}）も正解です。\n他の正解パターン: " +
                           ' / '.join([p for p in correct_patterns_text if p != your_pattern_text]))
            else:
                st.error("× 不正解… 正解パターンは " + ' / '.join(correct_patterns_text) + " です")
        else:
            # 既存の1つ選べ・複数選べの表示
            # ここでcorrect_answerを定義
            if isinstance(q['answer'], str) and '/' in q['answer']:
                correct_answer = q['answer'].split('/')
            elif isinstance(q['answer'], str) and len(q['answer']) > 1 and num_choices > 1:
                correct_answer = list(q['answer'])
            else:
                correct_answer = [q['answer']]
            correct_answer_text = get_correct_label(correct_answer, q["choices"])
            if is_correct:
                if num_choices == 1 and len(correct_answer) > 1:
                    # 複数正解のうちどれを選んだか表示
                    selected_text = get_correct_label(selected_labels, q['choices'])
                    st.success(f"✓ 正解！ あなたの選択（{', '.join(selected_text)}）も正解です。\n他の正解: {', '.join([c for c in correct_answer_text if c not in selected_text])}")
                else:
                    st.success("✓ 正解！")
            else:
                st.error(f"× 不正解… 正解は **{', '.join(correct_answer_text)}** です")


# --- 共通の処理 ---

# リセットフラグを消費
if st.session_state.get("reset_flag", False):
    st.session_state.reset_flag = False

# 画像がある場合は表示
if q.get("image_urls"):
    for url in q["image_urls"] or []:
        if url:
            st.image(url, use_column_width=True)

# 自己評価 (回答後に表示)
if st.session_state.get("checked", False):
    st.markdown("#### この問題の自己評価")
    subjective_options = ["もう一度", "難しい", "普通", "簡単"]  # 記号なし
    subjective_key = f"subjective_{q['number']}"

    # 記号マッピング
    eval_mark = {"もう一度": "×", "難しい": "△", "普通": "◯", "簡単": "◎"}

    if "eval_log" not in st.session_state: st.session_state.eval_log = {}

    selected_eval = st.radio(
        "自己評価を選択してください",
        subjective_options,
        key=subjective_key,
        index=None,
        horizontal=True,
        label_visibility="collapsed"
    )

    if selected_eval:
        # 記号付きで保存
        st.session_state.eval_log[q['number']] = f"{eval_mark[selected_eval]} {selected_eval}"

# 「次の問題」ボタン (未回答なら常に有効、回答済みなら自己評価必須)
answered = st.session_state.get("checked", False)
evaled = st.session_state.get("eval_log", {}).get(q['number']) is not None

# 選択肢を一度でも選んだかどうかを判定
if q.get("choices"):
    has_selected = bool(st.session_state.get("selected_choices"))
else:
    has_selected = bool(st.session_state.get("selected_choices", ""))

# ボタン有効化条件
if not has_selected:
    can_next = True  # 未回答なら常に進める
else:
    can_next = answered and evaled  # 回答済みなら自己評価必須

if st.button("次の問題", disabled=not can_next, key=f"next_{q['number']}"):
    if order_mode == "順番通り":
        st.session_state.idx = (st.session_state.idx + 1) % len(questions)
    else:
        next_idx = st.session_state.idx
        while next_idx == st.session_state.idx and len(questions) > 1:
            next_idx = random.randrange(len(questions))
        st.session_state.idx = next_idx

    # 状態をリセットして再実行
    st.session_state.checked = False
    st.session_state.reset_flag = True
    st.rerun()