import json
from collections import Counter

# --- 設定 ---
MASTER_FILE_PATH = '/Users/utsueito/kokushi-dx-poc/dental-DX-PoC/data/master_questions.json'

# あなたが定義した「正解の科目リスト」
VALID_SUBJECT_NAMES = {
    "歯科理工学", "保存修復学", "歯内治療学", "歯周病学", "解剖学",
    "組織学", "生理学","生化学", "クラウンブリッジ学", "病理学", "薬理学",
    "微生物学・免疫学", "衛生学", "発生学・加齢老年学", "部分床義歯学",
    "全部床義歯学", "インプラント学", "口腔外科学", "歯科放射線学",
    "歯科麻酔学", "矯正歯科学", "小児歯科学",
}
# 「未分類」も分析対象に含める
VALID_SUBJECT_NAMES.add("（未分類）")


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
print("-" * 50)

# 科目ごとの問題数をカウント
subject_counts = Counter(q.get("subject", "（未分類）") for q in questions)

# 予期せぬ科目名がないかチェック
unexpected_subjects = set(subject_counts.keys()) - VALID_SUBJECT_NAMES

# --- 結果レポートの表示 ---
print("📊 科目別 問題数レポート")
print("-" * 50)

for subject, count in sorted(subject_counts.items(), key=lambda item: item[1], reverse=True):
    print(f"{subject:<20} | {count:>5} 問")

print("-" * 50)
if subject_counts["（未分類）"]:
    print(f"⚠️ 未分類の問題が {subject_counts['（未分類）']} 件あります。")

if unexpected_subjects:
    print(f"🚨 警告: 予期せぬ科目名が見つかりました: {unexpected_subjects}")
else:
    print("👍 データの科目構成は正常です。")