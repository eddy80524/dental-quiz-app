import os
import pandas as pd
import unicodedata
from sentence_transformers import SentenceTransformer, util
import torch

print("--- スクリプトを開始します ---")


# --- 1. ファイルパスの設定 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GUIDELINES_PATH = os.path.join(BASE_DIR, '..', 'my_llm_app', 'data', 'guidelines_enriched.csv')
EXPERT_KEYWORDS_PATH = os.path.join(BASE_DIR, 'expert_keywords.txt')
# ★★★ 出力ファイル名を統一 ★★★
OUTPUT_PATH = os.path.join(BASE_DIR, '..', 'my_llm_app', 'data', 'guidelines_enriched.csv')
# --- 2. データの読み込み ---
try:
    print("--- データを読み込み中 ---")
    guidelines_df = pd.read_csv(GUIDELINES_PATH)
    with open(EXPERT_KEYWORDS_PATH, 'r', encoding='utf-8') as f:
        expert_keywords = [line.strip() for line in f if line.strip()]
    print(f"✅ ガイドライン {len(guidelines_df)}件、専門用語 {len(expert_keywords)}語を読み込みました。")
except FileNotFoundError as e:
    print(f"❌エラー: ファイルが見つかりません。 {e}")
    exit()

# --- 3. AIモデルの読み込み ---
print("--- AI言語モデルを読み込み中（初回はダウンロードに時間がかかります） ---")
# 日本語に強く、意味の類似度検索に適したモデルを選択
model = SentenceTransformer('cl-tohoku/bert-base-japanese-whole-word-masking')
print("✅ AIモデルの読み込み完了。")

# --- 4. 基準項目の「意味ベクトル」を作成 ---
print("--- 基準項目の文脈を意味ベクトルに変換中 ---")
# 各基準項目を代表する「文脈テキスト」を作成
guidelines_df['context_text'] = guidelines_df.apply(
    lambda row: ' '.join(map(str, [
        row['chapter'], row['daikoumoku'], row['chukoumoku'], 
        row['shoukoumoku'], row['remarks']
    ])).replace('nan', ''), # nan（欠損値）を空文字に置換
    axis=1
)
# 全ての文脈テキストを一度にベクトル化（高速）
guideline_embeddings = model.encode(guidelines_df['context_text'].tolist(), convert_to_tensor=True)
print("✅ 意味ベクトルの作成完了。")

# --- 5. 専門用語の分類とキーワード追加 ---
print("--- 専門用語の分類を開始します ---")
classified_count = 0
for keyword in expert_keywords:
    # 専門用語をベクトル化
    keyword_embedding = model.encode(keyword, convert_to_tensor=True)
    
    # 全ての基準項目との類似度（コサイン類似度）を計算
    cosine_scores = util.cos_sim(keyword_embedding, guideline_embeddings)
    
    # 最も類似度が高い項目のIDを取得
    best_match_index = torch.argmax(cosine_scores).item()
    
    # 該当する基準項目の既存キーワードを取得
    existing_keywords_str = guidelines_df.loc[best_match_index, 'keywords']
    existing_keywords = set(str(existing_keywords_str).split(';')) if pd.notna(existing_keywords_str) else set()
    
    # まだ登録されていなければ追加
    if keyword not in existing_keywords:
        existing_keywords.add(keyword)
        guidelines_df.loc[best_match_index, 'keywords'] = ';'.join(filter(None, sorted(list(existing_keywords))))
        print(f"  - 「{keyword}」を項目ID {best_match_index} ({guidelines_df.loc[best_match_index, 'chukoumoku']}) に分類しました。")
        classified_count += 1

print(f"✅ {classified_count}語の専門用語を分類・追加しました。")

# --- 6. 最終結果の保存 ---
guidelines_df.drop(columns=['context_text'], inplace=True)
guidelines_df.to_csv(OUTPUT_PATH, index=False)
print(f"🎉 全工程完了！ 最終版のDBを '{OUTPUT_PATH}' に保存しました。")