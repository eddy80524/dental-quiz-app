# scraping/scrape_dentalyouth.py

import re
import time
import os
import json
import sys
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from urllib.parse import urljoin

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from scraping.kyousei_urls import kyousei_urls
from scraping.shouni_urls import shouni_urls
from scraping.targets import kuraburi_urls

# 「回数は2～3桁の数字」「領域はA～D」「あとは連番」をキャッチする正規表現
HEADER_PAT = re.compile(r"^(\d{2,3}[A-D]\d+)\s*(.*)", re.DOTALL)

# 選択肢行をキャッチするパターン（ａ～ｅ／A～E + 任意の区切り記号）
CHOICE_PAT = re.compile(r"^[ａ-ｅa-eＡ-ＥA-E][\s　\.\)．、,]*(.+)")

def to_fullsize_url(url):
    # サムネイル除去
    url = re.sub(r'(-\d+x\d+)(\.\w+)$', r'\2', url)
    # jpg/jpeg/webp→pngに変換（高画質化目的）
    url = re.sub(r'\.(jpg|jpeg|webp)$', '.png', url, flags=re.IGNORECASE)
    # ?resize=...や?ssl=1などのクエリを除去し、必ず.pngで終わるように
    url = re.sub(r'\.png\?.*$', '.png', url, flags=re.IGNORECASE)
    return url

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
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div[id^='text-button']"))
        )
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

            elif elem.name == "img":
                src = urljoin(url, elem["src"])
                src = to_fullsize_url(src)  # ★必ず元画像URLに変換
                img_urls.append(src)
                question_parts.append(f"[Image: {src}]")

            elif elem.name == "figure":
                img = elem.find("img")
                if img and img.get("src"):
                    src = urljoin(url, img["src"])
                    src = to_fullsize_url(src)  # ★必ず元画像URLに変換
                    img_urls.append(src)
                    question_parts.append(f"[Image: {src}]")

            elif elem.name in ("ul", "ol"):
                state = 'choice' # リストは常に選択肢とみなす
                for li in elem.find_all("li"):
                    choices.append(li.get_text(strip=True))
        
        # ★修正点: 不要になったフォールバックロジックを削除

        # 問題文を整形 (元の関数をそのまま使用)
        def clean_question(text: str, image_urls=None) -> str:
            text = re.sub(r"[\u3000\n]+", " ", text)
            text = re.sub(r"\bあ\b", "", text) # 「あ」の削除機能を維持
            # 画像URLがテキストに混入している場合は除去
            if image_urls:
                for url in image_urls:
                    # サムネイルやクエリ付きも除去
                    url_pattern = re.escape(url)
                    url_pattern = url_pattern.replace(r'\\?', r'\\?')
                    text = re.sub(url_pattern + r'(\?[^\s\]]*)?', '', text)
                # [Image: ...] のような表記も除去
                text = re.sub(r'\[Image: [^\]]+\]', '', text)
            return re.sub(r"\s+", " ", text).strip()

        raw_q = " ".join(question_parts)
        question_clean = clean_question(raw_q, img_urls)

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

def scrape_and_save_shouni():
    MAX_RETRY = 3
    all_questions = []
    for url in shouni_urls:
        print(f"スクレイピング中: {url}")
        for attempt in range(1, MAX_RETRY + 1):
            try:
                questions = scrape_questions_from(url)
                if questions:
                    all_questions.extend(questions)
                break
            except Exception as e:
                print(f"  エラー発生 (試行{attempt}/{MAX_RETRY}): {e}")
                if attempt == MAX_RETRY:
                    print(f"  スキップします: {url}")
                else:
                    time.sleep(3)
    save_questions_to_json(all_questions, "dental_shouni.json")

def scrape_and_save_kuraburi():
    MAX_RETRY = 3
    all_questions = []
    for url in kuraburi_urls:
        print(f"スクレイピング中: {url}")
        for attempt in range(1, MAX_RETRY + 1):
            try:
                questions = scrape_questions_from(url)
                if questions:
                    all_questions.extend(questions)
                break
            except Exception as e:
                print(f"  エラー発生 (試行{attempt}/{MAX_RETRY}): {e}")
                if attempt == MAX_RETRY:
                    print(f"  スキップします: {url}")
                else:
                    time.sleep(3)
    save_questions_to_json(all_questions, "../data/科目別/dental_kuraburi.json")

# 例：scrape_questions_fromの利用後に保存
if __name__ == "__main__":
    from scraping.shouni_urls import shouni_urls
    MAX_RETRY = 3
    all_questions = []
    for url in shouni_urls:
        print(f"スクレイピング中: {url}")
        for attempt in range(1, MAX_RETRY + 1):
            try:
                questions = scrape_questions_from(url)
                if questions:
                    all_questions.extend(questions)
                break  # 成功したらリトライループを抜ける
            except Exception as e:
                print(f"  エラー発生 (試行{attempt}/{MAX_RETRY}): {e}")
                if attempt == MAX_RETRY:
                    print(f"  スキップします: {url}")
                else:
                    time.sleep(3)  # 少し待ってリトライ
    # すべての小児歯科学問題を1ファイルにまとめて保存
    save_questions_to_json(all_questions, "dental_shouni.json")
    
    # クラウンブリッジ学もスクレイピング
    from scraping.targets import kuraburi_urls
    scrape_and_save_kuraburi()