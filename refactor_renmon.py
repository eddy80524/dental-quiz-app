import json
import re
from collections import defaultdict

# --- 設定 ---
MASTER_FILE_PATH = 'data/master_questions.json'
OUTPUT_FILE_PATH = 'data/master_questions_final.json' # 最終成果物のファイル名

# 最終版の正規表現
renmon_intro_pattern = re.compile(r"^((?:次の文により|【症例】).+?(?:の問い|の問題)に答えよ。)")

# --- スクリプト本体 ---
print("最終データ構造へのリファクタリングを開始します...")

try:
    with open(MASTER_FILE_PATH, 'r', encoding='utf-8') as f:
        questions = json.load(f)
except FileNotFoundError:
    print(f"エラー: {MASTER_FILE_PATH} が見つかりません。")
    exit()

# Part 1: 連問を先に検出し、グループ化する
renmon_groups = defaultdict(list)
processed_renmon_numbers = set()

for q in questions:
    q_text = q.get("question", "")
    q_num = q.get("number")
    
    match = renmon_intro_pattern.search(q_text)
    
    if match:
        intro_sentence = match.group(1)
        exam_block_match = re.match(r'(\d+[A-D])', q_num)
        numbers_in_intro = re.findall(r'\d+', intro_sentence)
        
        if len(numbers_in_intro) >= 2 and exam_block_match:
            exam_block = exam_block_match.group(1)
            case_id = f"case-{exam_block}-" + "-".join(sorted(list(set(numbers_in_intro))))
            renmon_groups[case_id].append(q)
            processed_renmon_numbers.add(q_num)

# Part 2: 新しいデータ構造を構築する
new_cases = {}
new_questions = []

print(f"検出した{len(renmon_groups)}個の連問グループを処理中...")
for case_id, grouped_questions in renmon_groups.items():
    # グループ内の最初の問題を使って症例データを作成
    first_q = grouped_questions[0]
    first_q_text = first_q.get("question", "")
    
    # 共通の症例文を抽出
    match = renmon_intro_pattern.search(first_q_text)
    # 症例文から設問を分離するロジック（一番最後の句点までを症例とする）
    parts = re.split(r'。(?!$)', first_q_text)
    if len(parts) > 1:
        scenario_text = "。".join(parts[:-1]) + "。"
    else: # 念のため
        scenario_text = first_q_text

    # 新しい症例を登録
    new_cases[case_id] = {
        "scenario_text": scenario_text,
        "image_urls": first_q.get("image_urls", [])
    }
    
    # グループ内の各問題を処理
    for q in grouped_questions:
        q_text = q.get("question", "")
        # 共通文（scenario_text）を問題文から削除し、個別設問だけを残す
        individual_question_text = q_text.replace(scenario_text, "", 1).strip()
        
        q['case_id'] = case_id
        q['question'] = individual_question_text
        if 'image_urls' in q:
            del q['image_urls']
        
        new_questions.append(q)

# Part 3: 連問以外の通常の問題を追加する
print("連問以外の通常問題を処理中...")
for q in questions:
    if q.get("number") not in processed_renmon_numbers:
        new_questions.append(q)

# 最終的なデータ構造を作成
final_data = {
    "cases": new_cases,
    "questions": sorted(new_questions, key=lambda x: x['number'])
}

# 新しいファイルに保存
with open(OUTPUT_FILE_PATH, 'w', encoding='utf-8') as f:
    json.dump(final_data, f, ensure_ascii=False, indent=2)

print("\n" + "="*50)
print("✅ 全ての処理が完了しました！")
print(f"  - 症例数: {len(new_cases)}件")
print(f"  - 総問題数: {len(new_questions)}件")
print(f"  - 最終データが {OUTPUT_FILE_PATH} に保存されました。")
print("="*50)