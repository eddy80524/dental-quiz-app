import json
import re

# ファイルパス
file_path = "my_llm_app/data/master_questions_final.json"

with open(file_path, encoding="utf-8") as f:
    data = json.load(f)

pattern = re.compile(r"別冊No\.[^）]+）を別に示す。")

# casesチェック
cases_no_image = []
for case_id, case in data.get("cases", {}).items():
    scenario = case.get("scenario_text", "")
    if pattern.search(scenario):
        # image_urlsキーが存在しない、または空
        if "image_urls" not in case or not case.get("image_urls", []):
            cases_no_image.append({"case_id": case_id, "scenario_text": scenario})

# questionsチェック
questions_no_image = []
for q in data.get("questions", []):
    qtext = q.get("question", "")
    if pattern.search(qtext):
        # image_urlsキーが存在しない、または空
        if "image_urls" not in q or not q.get("image_urls", []):
            questions_no_image.append({"number": q.get("number"), "question": qtext})

print("casesで画像記載あるがURLなし:")
for c in cases_no_image:
    print(c)

print("\nquestionsで画像記載あるがURLなしの問題番号:")
for q in questions_no_image:
    print(q["number"])
