import re
import json
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

# 対象のURL
url = "https://dentalyouth.blog/archives/26526"

# --- 1. Seleniumによる動的コンテンツの取得 ---

# Chromeオプションの設定
options = webdriver.ChromeOptions()
# ヘッドレスモードで実行したい場合は以下のコメントを解除
# options.add_argument('--headless') 
options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36")

# WebDriverの起動
driver = webdriver.Chrome(options=options)
print(f"アクセス中: {url}")
driver.get(url)

# JavaScriptのレンダリングやコンテンツの読み込みを待つ
print("ページ読み込み待機中... (10秒)")
time.sleep(10)

# ページ内のすべての解答ボタンを取得
buttons = driver.find_elements(By.CSS_SELECTOR, "div[id^='text-button']")
print(f"解答ボタンを{len(buttons)}個見つけました。")

answers = []
# 各ボタンをクリックして解答を抽出
for i, btn in enumerate(buttons):
    try:
        # ボタンがクリック可能になるまで待機
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable(btn))
        # JavaScriptでクリックを実行（確実性を高めるため）
        driver.execute_script("arguments[0].click();", btn)
        
        # テキストが「解答：表示」から変化するまで待機
        WebDriverWait(driver, 5).until(lambda d: "解答" in btn.text and "表示" not in btn.text)
        
        answer_text = btn.text.strip()
        # 正規表現で「解答：」以降のテキストを抽出
        m = re.search(r"解答[:：]?\s*(.*)", answer_text)
        answer_only = m.group(1).strip() if m else answer_text
        
        print(f"問{i+1} の解答を取得: {answer_only}")
        answers.append(answer_only)
    except Exception as e:
        print(f"問{i+1} の解答取得に失敗: {e}")
        answers.append("") # 失敗した場合は空文字を追加

print("\nすべての解答の取得が完了しました。")

# Seleniumからページの最終的なHTMLソースを取得
html = driver.page_source
# WebDriverを終了してリソースを解放
driver.quit()

# --- 2. BeautifulSoupによる静的コンテンツの解析と統合 ---

print("HTMLの解析を開始します...")
soup = BeautifulSoup(html, "html.parser")

# 正規表現で問題ヘッダー（例: 118A1, 118A2...）をすべて見つける
problem_headers = soup.find_all('h4', string=re.compile(r'^118A\d+'))
print(f"{len(problem_headers)}個の問題を検出しました。")

questions = []
# 各問題ヘッダーをループ処理
for idx, header in enumerate(problem_headers):
    number = header.get_text(strip=True)
    question_text = ""
    choices = []
    image_url = None

    # h4タグの次の要素から走査を開始
    sib = header.find_next_sibling()
    # 次のh4タグが見つかるまで、その間の要素をすべて取得
    while sib and sib.name != 'h4':
        # 画像タグの場合
        if sib.name == 'img' and sib.has_attr('src'):
            image_url = sib.get('src')
        
        # テキストを持つ要素の場合
        if sib.get_text(strip=True):
            txt = sib.get_text(strip=True)
            # 選択肢の行を検出（全角の「ａ」で判定）
            if re.search(r'^[ａ-ｅ]', txt):
                # 問題文が選択肢と同じ行に含まれる場合を考慮
                pre_choice_text = re.split(r'^[ａ-ｅ]', txt)[0]
                if pre_choice_text:
                    question_text += pre_choice_text.strip() + "\n"
                
                # 選択肢（a,b,c,d,e）を抽出
                c_match = re.findall(r'[ａ-ｅ][.．）]?\s*([^ａ-ｅ]+)', txt)
                choices = [c.strip() for c in c_match if c.strip()]
            # 解答ボタンのテキストは無視
            elif "解答" not in txt:
                question_text += txt + "\n"

        # 次の兄弟要素へ移動
        sib = sib.find_next_sibling()

    # Seleniumで取得した解答をインデックスで紐付け
    # もし解答リストの数が足りなくてもエラーにならないように対処
    answer = answers[idx] if idx < len(answers) else "取得失敗"

    questions.append({
        "number": number,
        "question": question_text.strip(),
        "choices": choices,
        "image_url": image_url,
        "answer": answer
    })

print("\nJSONデータの作成が完了しました。")

# --- 3. JSONファイルへの保存 ---

# 作成したリストをJSON形式でファイルに書き出す
file_path = "dental_118A.json"
with open(file_path, "w", encoding="utf-8") as f:
    json.dump(questions, f, ensure_ascii=False, indent=2)

print(f"完了！ データが {file_path} に保存されました。")
# print(json.dumps(questions, indent=2, ensure_ascii=False)) # コンソールに出力したい場合