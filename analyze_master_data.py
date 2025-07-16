import json
from collections import Counter
import re

# --- 設定 ---
MASTER_FILE_PATH = 'data/master_questions.json'

# 正解の科目リスト
VALID_SUBJECT_NAMES = {
    "歯科理工学", "保存修復学", "歯内治療学", "歯周病学", "解剖学",
    "組織学", "生理学", "クラウンブリッジ学", "病理学", "薬理学","生化学",
    "微生物学・免疫学", "衛生学", "発生学・加齢老年学", "部分床義歯学",
    "全部床義歯学", "インプラント学", "口腔外科学", "歯科放射線学",
    "歯科麻酔学", "矯正歯科学", "小児歯科学", "（未分類）"
}

# --- スクリプト本体 ---

try:
    with open(MASTER_FILE_PATH, 'r', encoding='utf-8') as f:
        questions = json.load(f)
except FileNotFoundError:
    print(f"エラー: {MASTER_FILE_PATH} が見つかりません。")
    exit()
except json.JSONDecodeError:
    print(f"エラー: {MASTER_FILE_PATH} は有効なJSONファイルではありません。")
    exit()

print(f"✅ {MASTER_FILE_PATH} を読み込みました。総問題数: {len(questions)}件")

# --- 各種エラーを格納するリスト ---
missing_text_errors = []
choice_mismatch_errors = []
unexpected_subjects = set()

# --- 全問題をループしてチェック ---
for q in questions:
    q_num = q.get("number", "番号不明")
    
    # 1. 問題文の欠損チェック
    if not q.get("question", "").strip():
        missing_text_errors.append(q_num)
        
    # 2. 選択肢の数と設問の矛盾チェック (修正済み)
    question_text = q.get("question", "")
    choices = q.get("choices", [])
    
    # 「1つ選べ」で選択肢が5つでない場合のみチェック
    if "1つ選べ" in question_text and len(choices) != 5:
        choice_mismatch_errors.append(f"{q_num} (1つ選べ/選択肢{len(choices)}個)")
        
    # 3. 科目名のチェック
    subject = q.get("subject", "（未分類）")
    if subject not in VALID_SUBJECT_NAMES:
        unexpected_subjects.add(subject)

# --- 結果レポートの表示 ---
print("\n" + "="*50)
print("📊 データ品質総合レポート")
print("="*50)

# 1. 科目構成レポート
print("\n--- 1. 科目構成 ---")
subject_counts = Counter(q.get("subject", "（未分類）") for q in questions)
for subject, count in sorted(subject_counts.items()):
    print(f"{subject:<20} | {count:>5} 問")

if unexpected_subjects:
    print(f"🚨 警告: 予期せぬ科目名: {unexpected_subjects}")
else:
    print("👍 科目構成は正常です。")
    
# 2. 問題文欠損レポート
print("\n--- 2. 問題文の欠損 ---")
if missing_text_errors:
    print(f"🚨 {len(missing_text_errors)}件の問題で問題文が欠損しています:")
    print(", ".join(sorted(missing_text_errors)))
else:
    print("👍 問題文の欠損はありません。")

# 3. 選択肢の矛盾レポート
print("\n--- 3. 設問と選択肢の数の矛盾 ---")
if choice_mismatch_errors:
    print(f"🚨 {len(choice_mismatch_errors)}件の問題で矛盾が見つかりました:")
    print(", ".join(sorted(choice_mismatch_errors)))
else:
    print("👍 設問と選択肢の数の矛盾はありません。")
    
print("\n" + "="*50)
print("レポート終了")