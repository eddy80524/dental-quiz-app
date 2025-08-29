from dotenv import load_dotenv
import os
from pyngrok import ngrok, conf
import subprocess
import time

# .envファイルのパスを明示
load_dotenv(dotenv_path="./.env")
NGROK_TOKEN = os.getenv("NGROK_TOKEN")
print(f"NGROK_TOKEN={NGROK_TOKEN}")  # ←追加

# ngrok認証
conf.get_default().auth_token = NGROK_TOKEN

# Streamlitをサブプロセスで起動（出力をそのまま表示）
streamlit_proc = subprocess.Popen(
    ["streamlit", "run", "app.py"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True
)

# Streamlitの起動を少し待つ
time.sleep(3)

# ngrokで8501ポートを公開
public_url = ngrok.connect(8501).public_url
print(f"公開URL: {public_url}")

# Streamlitの出力をリアルタイムで表示
try:
    for line in streamlit_proc.stdout:
        print(line, end="")
except KeyboardInterrupt:
    print("終了します")
finally:
    streamlit_proc.terminate()