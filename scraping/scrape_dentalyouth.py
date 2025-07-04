# scraping/scrape_dentalyouth.py

import re
import time
import os
import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# 「回数は2～3桁の数字」「領域はA～D」「あとは連番」をキャッチする正規表現
HEADER_PAT = re.compile(r"^(\d{2,3}[A-D]\d+)\s*(.*)", re.DOTALL)

# 選択肢行をキャッチするパターン（ａ～ｅ／A～E + 任意の区切り記号）
CHOICE_PAT = re.compile(r"^[ａ-ｅa-eＡ-ＥA-E][\s　\.\)．、,]*(.+)")

def scrape_questions_from(url: str) -> list[dict]:
    """
    指定 URL の dentalyouth.blog 記事から
    国家試験問題リストを取得して返す。
    各要素は {
        "number": "118A1",
        "question": "...",
        "choices": [...],
        "image_urls": [...],
        "answer": "A"
    } の形式。
    """

    # --- 1. Selenium で「解答」ボタンをクリックして全文取得 ---
    # (このセクションは変更なし)
    options = webdriver.ChromeOptions()
    # options.add_argument('--headless')
    options.add_argument(
        "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/114.0.0.0 Safari/537.36"
    )
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        time.sleep(5)
        buttons = driver.find_elements(By.CSS_SELECTOR, "div[id^='text-button']")
        answers = []
        for btn in buttons:
            try:
                WebDriverWait(driver, 10).until(EC.element_to_be_clickable(btn))
                btn.click()
                WebDriverWait(driver, 5).until(
                    lambda d: btn.text.strip() != "解答：表示"
                )
                text = btn.text.strip()
                m = re.search(r"解答[:：]?\s*(.*)", text)
                answers.append(m.group(1).strip() if m else text)
            except Exception:
                answers.append("")
        html = driver.page_source
    finally:
        driver.quit()

    # --- 2. BeautifulSoup で問題文と選択肢をパース ---
    # (このセクションは変更なし)
    soup = BeautifulSoup(html, "html.parser")
    content = (
        soup.select_one(".entry-content")
        or soup.select_one(".post-content")
        or soup.find("article")
    )
    if content is None:
        raise RuntimeError("記事本文コンテナが見つかりません")

    elements = content.find_all(["p", "img", "figure", "ul", "ol"], recursive=True)

    blocks = []
    current = []
    for el in elements:
        txt = el.get_text(strip=True)
        if el.name == "p" and HEADER_PAT.match(txt):
            if current:
                blocks.append(current)
            current = [el]
        elif current:
            current.append(el)
    if current:
        blocks.append(current)

    questions = []
    for bi, block in enumerate(blocks):
        header = block[0].get_text(separator="\n", strip=True)
        m = HEADER_PAT.match(header)
        if not m:
            continue
        number, rest = m.groups()

        # ★修正点: 質問文と選択肢の分離ロジックを改善
        question_parts = []
        choices = []
        img_urls = []
        state = 'question'  # 'question'か'choice'かを判断する状態変数

        # 処理を関数化し、ヘッダ行と後続のpタグで共通利用する
        def process_line(line):
            nonlocal state
            clean_line = line.strip()
            if not clean_line:
                return

            cm = CHOICE_PAT.match(clean_line)
            if cm:
                state = 'choice'
                choices.append(cm.group(1).strip())
            elif state == 'question':
                question_parts.append(clean_line)
        
        # ヘッダ行のテキスト(rest)を処理
        for line in rest.splitlines():
            process_line(line)

        # 続く要素を順に解析 (元のループ構造を維持)
        for elem in block[1:]:
            if elem.name == "p":
                for line in elem.get_text(separator="\n", strip=True).splitlines():
                    process_line(line)

            # 画像とリストの処理は元のコードのまま
            elif elem.name == "img":
                src = urljoin(url, elem["src"])
                img_urls.append(src)
                question_parts.append(f"[Image: {src}]")

            elif elem.name == "figure":
                img = elem.find("img")
                if img and img.get("src"):
                    src = urljoin(url, img["src"])
                    img_urls.append(src)
                    question_parts.append(f"[Image: {src}]")

            elif elem.name in ("ul", "ol"):
                state = 'choice' # リストは常に選択肢とみなす
                for li in elem.find_all("li"):
                    choices.append(li.get_text(strip=True))
        
        # ★修正点: 不要になったフォールバックロジックを削除

        # 問題文を整形 (元の関数をそのまま使用)
        def clean_question(text: str) -> str:
            text = re.sub(r"[\u3000\n]+", " ", text)
            text = re.sub(r"\bあ\b", "", text) # 「あ」の削除機能を維持
            return re.sub(r"\s+", " ", text).strip()

        raw_q = " ".join(question_parts)
        question_clean = clean_question(raw_q)

        questions.append({
            "number":     number,
            "question":   question_clean,
            "choices":    choices,
            "image_urls": list(dict.fromkeys(img_urls)) or None, # ★修正点: 重複するURLを削除
            "answer":     answers[bi] if bi < len(answers) else ""
        })

    return questions

def save_questions_to_json(questions, filename):
    # プロジェクトルートから見たdataディレクトリの絶対パス
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(base_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    file_path = os.path.join(data_dir, filename)
    # 既にファイルが存在する場合は上書きしない
    if os.path.exists(file_path):
        print(f"既にファイルが存在するため上書きしません: {file_path}")
        return
    # ファイルがなければ保存
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(questions, f, ensure_ascii=False, indent=2)
    print(f"保存しました: {file_path}")

# 例：scrape_questions_fromの利用後に保存
if __name__ == "__main__":
    url = "https://..."  # 取得したいURL
    questions = scrape_questions_from(url)
    # ファイル名例: dental_118A.json など
    if questions and "number" in questions[0]:
        filename = f"dental_{questions[0]['number'][:5]}.json"
    else:
        filename = "dental_unknown.json"
    save_questions_to_json(questions, filename)