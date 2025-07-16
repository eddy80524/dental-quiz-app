# api_server.py
from fastapi import FastAPI
from pydantic import BaseModel
from llama_cpp import Llama
import uvicorn
import os

# --- モデルの準備 (unsloth.Q4_K_M.gguf) ---
# プロジェクトルートからの絶対パスで指定
MODEL_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "llm_models", "unsloth.Q4_K_M.gguf")

# モデルが存在しない場合はエラーを出す
if not os.path.exists(MODEL_FILE):
    raise FileNotFoundError(f"モデルファイルが見つかりません: {MODEL_FILE}")

# --- モデルの読み込み ---
print("モデルを読み込んでいます...")
llm = Llama(model_path=MODEL_FILE, n_gpu_layers=-1, n_ctx=256)
print("モデルの読み込み完了。")

app = FastAPI()
class Query(BaseModel): prompt: str

@app.post("/generate")
def generate(query: Query):
    # テスト用に短いプロンプト・短い生成長
    output = llm(query.prompt, max_tokens=32, echo=False)
    return {"text": output['choices'][0]['text']}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)