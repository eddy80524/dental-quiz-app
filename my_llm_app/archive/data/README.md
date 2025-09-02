# アーカイブされたデータファイル

このディレクトリには、現在のアプリでは使用されていないが、過去の開発やスクリプトで利用されていたデータファイルが保存されています。

## ファイル一覧

### guidelines_enriched.csv
- **説明**: 歯科国試ガイドラインの詳細分類データ
- **用途**: キーワード分類やファインチューニング用データセット作成
- **サイズ**: 約24KB
- **最終更新**: 2024年7月24日
- **参照スクリプト**: 
  - `scripts/create_finetune_dataset.py`
  - `scripts/run_mapping_v2.py`
  - `scripts/classify_keywords_v2.py`

### mapping_result_v2.json
- **説明**: 問題とガイドラインのマッピング結果（バージョン2）
- **用途**: 問題分類やファインチューニング用データセット作成
- **サイズ**: 約134KB
- **最終更新**: 2024年8月15日
- **参照スクリプト**:
  - `scripts/run_mapping_v2.py`
  - `scripts/create_finetune_dataset.py`

## 注意事項

- これらのファイルは現在のStreamlitアプリ（`my_llm_app/app.py`）では使用されていません
- 削除前に、関連スクリプトでの参照パスを更新する必要があります
- 将来的に機能拡張で必要になる可能性があるため、一時的にアーカイブとして保存しています

## 復元方法

必要に応じて以下のコマンドで元の場所に復元できます：

```bash
# guidelines_enriched.csvの復元
mv my_llm_app/archive/data/guidelines_enriched.csv my_llm_app/data/

# mapping_result_v2.jsonの復元
mv my_llm_app/archive/data/mapping_result_v2.json my_llm_app/data/
```
