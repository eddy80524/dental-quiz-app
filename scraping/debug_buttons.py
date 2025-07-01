import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import re

url = "https://dentalyouth.blog/archives/26526"

options = webdriver.ChromeOptions()
# options.add_argument('--headless')
options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36")
driver = webdriver.Chrome(options=options)
driver.get(url)
time.sleep(10)  # JSレンダリング待ち

buttons = driver.find_elements(By.CSS_SELECTOR, "div[id^='text-button']")
print(f"ボタン数: {len(buttons)}")
answers = []
for i, btn in enumerate(buttons):
    try:
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, f"(//div[starts-with(@id, 'text-button')])[{i+1}]")))
        btn.click()
        print(f"{i+1}番目クリック成功")
        # テキストが「解答：表示」から変化するまで待つ
        WebDriverWait(driver, 5).until(lambda d: btn.text.strip() != "解答：表示")
        answer_text = btn.text.strip()
        m = re.search(r"解答[:：]?\s*(.*)", answer_text)
        answer_only = m.group(1).strip() if m else answer_text
        print(f"{i+1}番目の解答: {answer_only}")
        answers.append(answer_only)
    except Exception as e:
        print(f"{i+1}番目クリック失敗: {e}")
        answers.append("")

input("Enterで終了")
driver.quit()