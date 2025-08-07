import pandas as pd
from sentence_transformers import SentenceTransformer, InputExample, losses
from torch.utils.data import DataLoader
import os

print("--- AIモデルのファインチューニングを開始します ---")

# --- ファイルパスとパラメータ設定 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATASET_PATH = os.path.join(BASE_DIR, '..', 'my_llm_app', 'data', 'finetune_dataset.csv')
BASE_MODEL = 'cl-tohoku/bert-base-japanese-whole-word-masking'
OUTPUT_MODEL_PATH = os.path.join(BASE_DIR, '..', 'models', 'dental-bert-v1') # モデルの保存先

# 学習パラメータ
EPOCHS = 1
BATCH_SIZE = 16

# --- データの読み込みと準備 ---
print(f"--- 学習データ '{DATASET_PATH}' を読み込み中 ---")
df = pd.read_csv(DATASET_PATH)
train_examples = []
for index, row in df.iterrows():
    train_examples.append(InputExample(texts=[row['anchor'], row['positive']]))

# --- モデルの読み込みと学習設定 ---
print(f"--- ベースモデル '{BASE_MODEL}' を読み込み中 ---")
model = SentenceTransformer(BASE_MODEL)
train_dataloader = DataLoader(train_examples, shuffle=True, batch_size=BATCH_SIZE)
train_loss = losses.MultipleNegativesRankingLoss(model=model)

# --- 学習の実行 ---
print(f"--- {EPOCHS}エポックの学習を開始します（時間がかかります） ---")
model.fit(train_objectives=[(train_dataloader, train_loss)],
          epochs=EPOCHS,
          warmup_steps=100,
          output_path=OUTPUT_MODEL_PATH,
          show_progress_bar=True)

print(f"🎉 ファインチューニング完了！ 賢くなったモデルを'{OUTPUT_MODEL_PATH}'に保存しました。")