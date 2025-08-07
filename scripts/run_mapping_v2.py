import pandas as pd
import json
import os
import MeCab
import unicodedata
import subprocess
from sklearn.feature_extraction.text import TfidfVectorizer

# --- MeCabの初期化（辞書の場所を自動で探すロバストな方法） ---
print("--- MeCabの初期化を試みます ---")
try:
    cmd = 'echo `mecab-config --dicdir`"/mecab-ipadic-neologd"'
    path_neologd = subprocess.check_output(cmd, shell=True, text=True).strip()
    
    if os.path.isdir(path_neologd):
        print(f"✅ 推奨辞書(neologd)を'{path_neologd}'に発見しました。")
        mecab = MeCab.Tagger(f"-Owakati -d {path_neologd}")
    else:
        print("⚠️ 推奨辞書(neologd)が見つかりません。通常の辞書で初期化します。")
        mecab = MeCab.Tagger("-Owakati")
except Exception:
    print("⚠️ 辞書の自動検索に失敗しました。インストール済みのデフォルト辞書で試みます。")
    mecab = MeCab.Tagger("-Owakati")
print("✅ MeCabの初期化が完了しました。")


# --- ファイルパスの設定 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GUIDELINES_PATH = os.path.join(BASE_DIR, '..', 'my_llm_app', 'data', 'guidelines_enriched.csv')
QUESTIONS_PATH = os.path.join(BASE_DIR, '..', 'my_llm_app', 'data', 'master_questions_final.json')
OUTPUT_PATH = os.path.join(BASE_DIR, '..', 'my_llm_app', 'data', 'mapping_result_v2.json')
# ★★★ 出力ファイル名を統一 ★★★
UPDATED_GUIDELINES_PATH = os.path.join(BASE_DIR, '..', 'my_llm_app', 'data', 'guidelines_enriched.csv')
STOPWORDS_PATH = os.path.join(BASE_DIR, 'stopwords.txt') # ストップワードファイルのパスを追加


# --- ストップワードリストの読み込み処理を追加 ---
stopwords = set()
if os.path.exists(STOPWORDS_PATH):
    with open(STOPWORDS_PATH, 'r', encoding='utf-8') as f:
        stopwords = {line.strip().lower() for line in f if line.strip()}
print(f"✅ {len(stopwords)}語のストップワードを読み込みました。")


# --- 関数定義 ---
def normalize_text(text):
    """テキストを正規化（全角→半角、小文字化）"""
    return unicodedata.normalize('NFKC', str(text)).lower()

def tokenize(text):
    """MeCabを使って名詞・動詞・形容詞を抽出し、ストップワードを除外"""
    node = mecab.parseToNode(normalize_text(text))
    words = []
    while node:
        word = node.surface
        features = node.feature.split(',')
        # ストップワードに含まれず、品詞が対象の場合のみ追加
        if word not in stopwords and features[0] in ['名詞', '動詞', '形容詞']:
            words.append(word)
        node = node.next
    return " ".join(words)


# --- データの読み込み ---
print("--- データの読み込み中 ---")
guidelines_df = pd.read_csv(GUIDELINES_PATH)
guidelines_df['id'] = range(len(guidelines_df))

with open(QUESTIONS_PATH, 'r', encoding='utf-8') as f:
    q_data = json.load(f)
    questions_list = q_data.get('questions', [])
    cases_dict = q_data.get('cases', {})

questions_df = pd.DataFrame(questions_list)

# --- 全問題のテキストを前処理 ---
print("--- 全問題のテキストを前処理中 ---")
questions_df['full_text'] = questions_df.apply(
    lambda row: normalize_text(
        str(row.get('question', '')) + ' ' + 
        ' '.join(map(str, row.get('choices', []) if row.get('choices') is not None else []))
    ), axis=1
)

# --- 初期マッピング ---
print("--- フェーズ1a: 初期マッピングを実行中 ---")
question_to_guideline_map_initial = {}
for _, question in questions_df.iterrows():
    search_text = question['full_text']
    best_score, best_guideline_id = 0, -1
    for _, guideline in guidelines_df.iterrows():
        keywords = str(guideline['keywords']).split(';')
        score = sum(1 for kw in keywords if kw and normalize_text(kw) in search_text)
        if score > best_score:
            best_score, best_guideline_id = score, int(guideline['id'])
    question_to_guideline_map_initial[question['number']] = best_guideline_id

# --- TF-IDFによるキーワード拡張 ---
print("--- フェーズ1b: TF-IDFでキーワードを自動拡張中 ---")
mapped_questions = {k: v for k, v in question_to_guideline_map_initial.items() if v != -1}
questions_df['guideline_id'] = questions_df['number'].map(mapped_questions)

corpus_by_guideline = questions_df.dropna(subset=['guideline_id']).groupby('guideline_id')['full_text'].apply(' '.join).tolist()
guideline_ids_in_corpus = questions_df.dropna(subset=['guideline_id']).groupby('guideline_id')['full_text'].apply(' '.join).index.tolist()

if corpus_by_guideline:
    tokenized_corpus = [tokenize(doc) for doc in corpus_by_guideline]
    
    # --- パラメータ調整済み ---
    vectorizer = TfidfVectorizer(max_features=3000, max_df=0.5, min_df=1)
    tfidf_matrix = vectorizer.fit_transform(tokenized_corpus)
    feature_names = vectorizer.get_feature_names_out()

    for i, guideline_id in enumerate(guideline_ids_in_corpus):
        feature_index = tfidf_matrix[i,:].nonzero()[1]
        tfidf_scores = zip(feature_index, [tfidf_matrix[i, x] for x in feature_index])
        
        # --- 抽出キーワード数を20に増加 ---
        top_keywords = [feature_names[i] for i, s in sorted(tfidf_scores, key=lambda x: x[1], reverse=True)[:20]]
        
        existing_keywords = guidelines_df.loc[guidelines_df['id'] == guideline_id, 'keywords'].iloc[0]
        existing_set = set(str(existing_keywords).split(';')) if pd.notna(existing_keywords) else set()
        new_set = existing_set.union(set(top_keywords))
        guidelines_df.loc[guidelines_df['id'] == guideline_id, 'keywords'] = ';'.join(filter(None, new_set))

print("✅ キーワードDBを強化しました。")
guidelines_df.to_csv(UPDATED_GUIDELINES_PATH, index=False)
print(f"✅ 強化版DBを '{UPDATED_GUIDELINES_PATH}' に保存しました。")

# --- 強化済みDBで再マッピング ---
print("--- フェーズ2: 強化済みDBで再マッピングを実行中 ---")
question_to_guideline_map_final = {}
for _, question in questions_df.iterrows():
    search_text = question['full_text']
    best_score, best_guideline_id = 0, -1
    for _, guideline in guidelines_df.iterrows():
        keywords = str(guideline['keywords']).split(';')
        score = sum(1 for kw in keywords if kw and normalize_text(kw) in search_text)
        if score > best_score:
            best_score, best_guideline_id = score, int(guideline['id'])
    question_to_guideline_map_final[question['number']] = best_guideline_id

# --- 最終結果の保存 ---
with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
    json.dump(question_to_guideline_map_final, f, ensure_ascii=False, indent=2)

print(f"🎉 全工程完了！ 最終マッピング結果を '{OUTPUT_PATH}' に保存しました。")