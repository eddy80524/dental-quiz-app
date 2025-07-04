import sys
import os
import json

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import scraping.targets
verbose = True  # Set to False in production

if verbose:
    print("scraping.targets file:", scraping.targets.__file__)
    print("scraping.targets dict:", dir(scraping.targets))
from scraping.targets import targets
from scraping.scrape_dentalyouth import scrape_questions_from

# プロジェクトルートのdataディレクトリを絶対パスで指定
project_root = os.path.dirname(os.path.abspath(__file__))
data_dir = os.path.join(project_root, "data")
os.makedirs(data_dir, exist_ok=True)

def validate_questions(questions):
    # エラー内容を格納するリスト
    errors = []
    if not isinstance(questions, list):
        errors.append("questionsがlist型ではありません")
        return False, errors
    if len(questions) < 10:
        errors.append(f"問題数が少なすぎます: {len(questions)}問")
    for i, q in enumerate(questions):
        if not isinstance(q, dict):
            errors.append(f"{i+1}問目がdict型ではありません")
            continue
        if 'id' not in q and 'number' not in q:
            errors.append(f"{i+1}問目に'id'または'number'がありません")
        if 'text' not in q and 'question' not in q:
            errors.append(f"{i+1}問目に'text'または'question'がありません")
        if 'choices' not in q:
            errors.append(f"{i+1}問目に'choices'がありません")
        if 'answer' not in q:
            errors.append(f"{i+1}問目に'answer'がありません")
    return len(errors) == 0, errors

for t in targets:
    year    = t["year"]
    section = t["section"]
    url     = t["url"]

    fname    = f"dental_{year}{section}.json"
    out_path = os.path.join(data_dir, fname)  # ←ここを修正

    # 既に出力済みならスキップ
    if os.path.exists(out_path):
        print(f"■ skip: {fname} already exists")
        continue

    print(f"→ fetching {year}{section} from {url}")
    questions = scrape_questions_from(url)

    # バリデーション
    is_valid, errors = validate_questions(questions)
    if not is_valid:
        print(f"× invalid data: {fname} → 保存しません")
        for err in errors:
            print(f"  - {err}")
        continue

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(questions, f, ensure_ascii=False, indent=2)
    print(f"  saved: {out_path} ({len(questions)} questions)")