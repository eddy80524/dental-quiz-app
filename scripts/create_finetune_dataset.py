import pandas as pd
import json
import os
import random

print("--- ファインチューニング用データセットの作成を開始します ---")

# --- ファイルパスの設定 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GUIDELINES_PATH = os.path.join(BASE_DIR, '..', 'my_llm_app', 'data', 'guidelines_enriched.csv')
QUESTIONS_PATH = os.path.join(BASE_DIR, '..', 'my_llm_app', 'data', 'master_questions_final.json')
MAPPING_PATH = os.path.join(BASE_DIR, '..', 'my_llm_app', 'data', 'mapping_result_v2.json') # 最新のマッピング結果
OUTPUT_PATH = os.path.join(BASE_DIR, '..', 'my_llm_app', 'data', 'finetune_dataset.csv')

# --- データの読み込み ---
guidelines_df = pd.read_csv(GUIDELINES_PATH)
with open(QUESTIONS_PATH, 'r', encoding='utf-8') as f:
    q_data = json.load(f)
with open(MAPPING_PATH, 'r', encoding='utf-8') as f:
    mapping_data = json.load(f)

questions_df = pd.DataFrame(q_data.get('questions', []))
questions_df['full_text'] = questions_df.apply(
    lambda row: str(row.get('question', '')) + ' ' + ' '.join(map(str, row.get('choices', []) or [])),
    axis=1
)

# --- 学習ペアの作成 ---
# ガイドラインIDをキーとし、問題テキストのリストを値とする辞書を作成
guideline_to_questions = {}
for q_num, g_id in mapping_data.items():
    if g_id != -1:
        if g_id not in guideline_to_questions:
            guideline_to_questions[g_id] = []
        # 問題番号から問題テキストを検索
        question_text = questions_df[questions_df['number'] == q_num]['full_text'].iloc[0]
        guideline_to_questions[g_id].append(question_text)

# 学習ペア（anchor, positive）を作成
training_pairs = []
for g_id, texts in guideline_to_questions.items():
    if len(texts) > 1:
        # 同じグループ内のテキスト同士でペアを作成
        for i in range(len(texts)):
            for j in range(i + 1, len(texts)):
                training_pairs.append({'anchor': texts[i], 'positive': texts[j]})

if not training_pairs:
    print("❌ マッピング結果から学習ペアを作成できませんでした。マッピングデータを確認してください。")
else:
    # DataFrameに変換して保存
    finetune_df = pd.DataFrame(training_pairs)
    finetune_df.to_csv(OUTPUT_PATH, index=False)
    print(f"✅ {len(finetune_df)}ペアの学習データを作成し、'{OUTPUT_PATH}'に保存しました。")